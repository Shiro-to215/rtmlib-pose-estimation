import { useEffect, useMemo, useState } from 'react';
import { getBackendApi } from '../../../api/pywebview';

export interface UseSettingsFormReturn {
  values: Record<string, any>;
  setFieldValue: (key: string, value: any) => void;
  resetToDefaults: (defaults: Record<string, any>) => void;
  errors: Record<string, string>;
  rtmlibWarning: string | null;
  isDirty: boolean;
  isValid: boolean;
}

export function useSettingsForm(
  initialSettings: Record<string, any>,
  _mode: 'default' | 'job'
): UseSettingsFormReturn {
  const [values, setValues] = useState<Record<string, any>>({ ...initialSettings });
  const [initialSnapshot, setInitialSnapshot] = useState<Record<string, any>>({ ...initialSettings });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [rtmlibWarning, setRtmlibWarning] = useState<string | null>(null);

  // Sync snapshot if initialSettings ID/reference resets
  useEffect(() => {
    setValues({ ...initialSettings });
    setInitialSnapshot({ ...initialSettings });
    setErrors({});
    setRtmlibWarning(null);
  }, [initialSettings]);

  // Dirty detection
  const isDirty = useMemo(() => {
    return Object.keys(values).some((k) => {
      const v1 = values[k];
      const v2 = initialSnapshot[k];
      if (Array.isArray(v1) && Array.isArray(v2)) {
        return JSON.stringify(v1) !== JSON.stringify(v2);
      }
      if ((v1 === null || v1 === undefined) && (v2 === null || v2 === undefined)) {
        return false;
      }
      return v1 !== v2;
    });
  }, [values, initialSnapshot]);

  // Live validation
  const validateField = (key: string, val: any): string | null => {
    if (key === 'YOLO_IMAGE_SIZE' && (val < 320 || val > 2560)) {
      return '解像度は 320 〜 2560 の範囲で指定してください。';
    }
    if ((key === 'YOLO_CONFIDENCE' || key === 'YOLO_IOU') && (val < 0.01 || val > 1.0)) {
      return '0.01 〜 1.00 の範囲で指定してください。';
    }
    if (key === 'CAPTURE_FPS') {
      if (val !== null && val !== undefined && val !== '') {
        if (typeof val !== 'number' || !Number.isFinite(val) || val <= 0) {
          return '撮影フレームレートは 0 より大きい数値で指定してください。';
        }
      }
    }
    if (
      (key === 'YOLO_BATCH_SIZE' || key === 'RTMPOSE_BATCH_SIZE') &&
      (!Number.isInteger(val) || val < 1 || val > 512)
    ) {
      return 'バッチサイズは 1 〜 512 の整数で指定してください。';
    }
    if (
      key === 'VITPOSE_BATCH_SIZE' &&
      (!Number.isInteger(val) || val < 1 || val > 64)
    ) {
      return 'ViTPose++ のバッチサイズは 1 〜 64 の整数で指定してください。';
    }
    if (key === 'YOLO_CLASSES') {
      if (
        !Array.isArray(val) ||
        val.length === 0 ||
        val.some((n) => !Number.isInteger(n) || n < 0)
      ) {
        return '検出対象クラスIDは0以上の整数を1つ以上入力してください。';
      }
    }
    return null;
  };

  // Debounced pose engine compatibility check
  useEffect(() => {
    const poseEngine = String(values['POSE_ENGINE'] || 'rtmpose').toLowerCase();
    const timer = setTimeout(async () => {
      if (poseEngine === 'vitpose') {
        const vitModel = String(values['VITPOSE_MODEL'] || 'h').toLowerCase();
        const vitInput = String(values['VITPOSE_INPUT_SIZE'] || '256x192').toLowerCase();
        const vitPrecision = String(values['VITPOSE_PRECISION'] || 'fp16').toLowerCase();
        if (!['s', 'b', 'l', 'h'].includes(vitModel) || vitInput !== '256x192') {
          setRtmlibWarning('ViTPose++ は S/B/L/H かつ 256x192 のみ対応しています。');
          return;
        }
        const api = getBackendApi();
        if (api && api.validate_pose_settings) {
          try {
            const res = await api.validate_pose_settings({
              POSE_ENGINE: 'vitpose',
              VITPOSE_MODEL: vitModel,
              VITPOSE_INPUT_SIZE: vitInput,
              VITPOSE_PRECISION: vitPrecision,
            });
            if (!res.valid) {
              setRtmlibWarning(res.error || '無効なViTPose++設定です');
              return;
            }
          } catch {
            // ignore
          }
        }
        setRtmlibWarning(null);
        return;
      }

      const poseModel = values['RTMLIB_POSE_MODEL'] || 'x';
      const inputSize = values['RTMLIB_POSE_INPUT_SIZE'] || '384x288';

      // Local pre-check matrix:
      if (['t', 's', 'm'].includes(poseModel) && inputSize === '384x288') {
        setRtmlibWarning(`RTMPose-${poseModel.toUpperCase()} は 384x288 に対応していません。使用可能: 256x192`);
        return;
      }
      if (poseModel === 'x' && inputSize === '256x192') {
        setRtmlibWarning('RTMPose-X は 256x192 に対応していません。使用可能: 384x288');
        return;
      }

      // Backend verification if connected
      const api = getBackendApi();
      if (api && api.validate_rtmlib_settings) {
        try {
          const res = await api.validate_rtmlib_settings(poseModel, inputSize);
          if (!res.valid) {
            setRtmlibWarning(res.error || '無効なRTMLibモデルの組み合わせです');
            return;
          }
        } catch {
          // ignore
        }
      }
      setRtmlibWarning(null);
    }, 200);

    return () => clearTimeout(timer);
  }, [
    values['POSE_ENGINE'],
    values['RTMLIB_POSE_MODEL'],
    values['RTMLIB_POSE_INPUT_SIZE'],
    values['VITPOSE_MODEL'],
    values['VITPOSE_INPUT_SIZE'],
    values['VITPOSE_PRECISION'],
  ]);

  const setFieldValue = (k: string, v: any) => {
    setValues((prev) => ({ ...prev, [k]: v }));
    const err = validateField(k, v);
    setErrors((prev) => ({ ...prev, [k]: err || '' }));
  };

  const resetToDefaults = (defaults: Record<string, any>) => {
    setValues((prev) => ({ ...prev, ...defaults }));
    setErrors({});
    setRtmlibWarning(null);
  };

  const hasErrors = Object.values(errors).some((e) => Boolean(e));
  const isValid = !hasErrors && !rtmlibWarning;

  return {
    values,
    setFieldValue,
    resetToDefaults,
    errors,
    rtmlibWarning,
    isDirty,
    isValid,
  };
}
