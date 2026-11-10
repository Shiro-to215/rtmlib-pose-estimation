import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { SliderWithInput } from '../widgets/SliderWithInput';
import { DropdownSelect } from '../widgets/DropdownSelect';
import { TagListInput } from '../widgets/TagListInput';
import { NullableNumberInput } from '../widgets/NullableNumberInput';

export interface DetectionConfidenceTabProps {
  values: Record<string, any>;
  setFieldValue: (k: string, v: any) => void;
  choices: Record<string, string[]>;
  errors: Record<string, string>;
  rtmlibWarning: string | null;
}

export const DetectionConfidenceTab: React.FC<DetectionConfidenceTabProps> = ({
  values,
  setFieldValue,
  choices,
  errors,
  rtmlibWarning,
}) => {
  const poseModelChoices = choices.RTMLIB_POSE_MODEL || ['mode', 't', 's', 'm', 'l', 'x'];
  const poseInputChoices = choices.RTMLIB_POSE_INPUT_SIZE || ['mode', '256x192', '384x288'];
  const detectorChoices = choices.RTMLIB_PERSON_DETECTOR || ['mode', 'nano', 'tiny', 's', 'm', 'l', 'x'];

  return (
    <div className="space-y-4">
      {/* RTMLib Resolution Incompatibility Warning Banner */}
      {rtmlibWarning && (
        <div className="flex items-center gap-2 p-3 bg-[#FEF2F2] border border-[#F5C2C0] rounded-lg text-xs text-[#C8332B] font-medium">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 text-[#C8332B]" />
          <span>{rtmlibWarning}</span>
        </div>
      )}

      {/* Group: YOLO検出設定 */}
      <div className="border border-[#D4DFDC] rounded-lg p-3.5 bg-white">
        <h4 className="text-xs font-bold text-[#0F766E] mb-2">YOLO 検出・しきい値設定</h4>
        <div className="grid grid-cols-2 gap-4">
          <SliderWithInput
            label="YOLO 入力解像度 (YOLO_IMAGE_SIZE)"
            description="検出時の画像サイズ（320〜2560、大きいほど遠景・小人物検出精度向上）"
            value={values.YOLO_IMAGE_SIZE ?? 1280}
            min={320}
            max={2560}
            step={32}
            unit="px"
            onChange={(v) => setFieldValue('YOLO_IMAGE_SIZE', Math.round(v))}
            error={errors.YOLO_IMAGE_SIZE}
          />

          <SliderWithInput
            label="YOLO 検出信頼度 (YOLO_CONFIDENCE)"
            description="人物検出とみなす最低スコアしきい値"
            value={values.YOLO_CONFIDENCE ?? 0.2}
            min={0.01}
            max={1.0}
            step={0.01}
            onChange={(v) => setFieldValue('YOLO_CONFIDENCE', parseFloat(v.toFixed(2)))}
            error={errors.YOLO_CONFIDENCE}
          />
        </div>

        <div className="grid grid-cols-2 gap-4 mt-2">
          <SliderWithInput
            label="YOLO NMS IoU しきい値 (YOLO_IOU)"
            description="同一人物に対する重複バウンディングボックスの除外しきい値"
            value={values.YOLO_IOU ?? 0.5}
            min={0.01}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('YOLO_IOU', parseFloat(v.toFixed(2)))}
            error={errors.YOLO_IOU}
          />

          <SliderWithInput
            label="人物クロップ余白率 (CROP_PADDING_RATIO)"
            description="姿勢推定モデルへ送る前のバウンディングボックス拡張余白率"
            value={values.CROP_PADDING_RATIO ?? 0.25}
            min={0.0}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('CROP_PADDING_RATIO', parseFloat(v.toFixed(2)))}
          />
        </div>

        <div className="grid grid-cols-2 gap-4 mt-2">
          <TagListInput
            label="検出対象クラスID (YOLO_CLASSES)"
            description="0=人物 (person)。複数指定はカンマ区切り"
            value={values.YOLO_CLASSES || [0]}
            onChange={(v) => setFieldValue('YOLO_CLASSES', v)}
            error={errors.YOLO_CLASSES}
          />

          <NullableNumberInput
            label="固定追跡ID (YOLO_TRACK_ID)"
            description="空欄時は動画全体の移動量から主要被写体を自動選択"
            value={values.YOLO_TRACK_ID ?? null}
            onChange={(v) => setFieldValue('YOLO_TRACK_ID', v)}
          />
        </div>
      </div>

      {/* Group: RTMPose 設定 */}
      <div className="border border-[#D4DFDC] rounded-lg p-3.5 bg-white">
        <h4 className="text-xs font-bold text-[#0369A1] mb-2">RTMPose 骨格推定設定</h4>

        <div className="grid grid-cols-3 gap-3">
          <DropdownSelect
            label="RTMPose モデル (RTMLIB_POSE_MODEL)"
            description="個別モデル（mode＝プリセット連動）"
            value={values.RTMLIB_POSE_MODEL || 'mode'}
            options={poseModelChoices}
            onChange={(v) => setFieldValue('RTMLIB_POSE_MODEL', v)}
          />

          <DropdownSelect
            label="入力解像度 (RTMLIB_POSE_INPUT_SIZE)"
            description="解像度（mode＝自動、モデル互換性検査あり）"
            value={values.RTMLIB_POSE_INPUT_SIZE || 'mode'}
            options={poseInputChoices}
            onChange={(v) => setFieldValue('RTMLIB_POSE_INPUT_SIZE', v)}
          />

          <DropdownSelect
            label="RTMLib人物検出器 (RTMLIB_PERSON_DETECTOR)"
            description="YOLOX検出器（mode＝連動）"
            value={values.RTMLIB_PERSON_DETECTOR || 'mode'}
            options={detectorChoices}
            onChange={(v) => setFieldValue('RTMLIB_PERSON_DETECTOR', v)}
          />
        </div>

        <div className="grid grid-cols-3 gap-3 mt-3">
          <SliderWithInput
            label="関節スコアしきい値 (KEYPOINT_THRESHOLD)"
            description="このスコア未満の関節は未検出として扱います"
            value={values.KEYPOINT_THRESHOLD ?? 0.45}
            min={0.05}
            max={0.95}
            step={0.05}
            onChange={(v) => setFieldValue('KEYPOINT_THRESHOLD', parseFloat(v.toFixed(2)))}
          />

          <SliderWithInput
            label="内部検出器スコア (RTMLIB_DETECTOR_SCORE_THRESHOLD)"
            description="RTMLib内部人物検出スコアしきい値"
            value={values.RTMLIB_DETECTOR_SCORE_THRESHOLD ?? 0.7}
            min={0.1}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('RTMLIB_DETECTOR_SCORE_THRESHOLD', parseFloat(v.toFixed(2)))}
          />

          <SliderWithInput
            label="内部検出器NMS (RTMLIB_DETECTOR_NMS_THRESHOLD)"
            description="RTMLib内部人物検出NMS IoUしきい値"
            value={values.RTMLIB_DETECTOR_NMS_THRESHOLD ?? 0.45}
            min={0.1}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('RTMLIB_DETECTOR_NMS_THRESHOLD', parseFloat(v.toFixed(2)))}
          />
        </div>
      </div>
    </div>
  );
};
