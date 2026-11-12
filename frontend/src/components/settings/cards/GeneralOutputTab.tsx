import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { DropdownSelect } from '../widgets/DropdownSelect';
import { SliderWithInput } from '../widgets/SliderWithInput';
import { TagListInput } from '../widgets/TagListInput';
import { NullableNumberInput } from '../widgets/NullableNumberInput';

export interface GeneralOutputTabProps {
  values: Record<string, any>;
  setFieldValue: (k: string, v: any) => void;
  choices: Record<string, string[]>;
  errors: Record<string, string>;
  rtmlibWarning: string | null;
}

export const GeneralOutputTab: React.FC<GeneralOutputTabProps> = ({
  values,
  setFieldValue,
  choices,
  errors,
  rtmlibWarning,
}) => {
  const deviceOptions = choices.DEVICE || ['auto', 'cpu', 'cuda'];
  const yoloModelOptions = choices.YOLO_MODEL || ['yolo11n.pt', 'yolo11s.pt', 'yolo11m.pt', 'yolo11l.pt', 'yolo11x.pt'];
  const backendOptions = choices.BACKEND || ['onnxruntime', 'opencv'];
  const poseModelChoices = choices.RTMLIB_POSE_MODEL || ['t', 's', 'm', 'l', 'x'];
  const poseInputChoices = choices.RTMLIB_POSE_INPUT_SIZE || ['256x192', '384x288'];

  return (
    <div className="space-y-4">
      {/* RTMLib Resolution Incompatibility Warning Banner */}
      {rtmlibWarning && (
        <div className="flex items-center gap-2 p-3 bg-[#FEF2F2] border border-[#F5C2C0] rounded-lg text-xs text-[#C8332B] font-medium">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 text-[#C8332B]" />
          <span>{rtmlibWarning}</span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {/* DEVICE */}
        <DropdownSelect
          label="推論実行デバイス"
          description="YOLOおよび姿勢推定モデルを実行するハードウェア（auto: 自動判定, cuda: GPU, cpu: CPU）"
          value={values.DEVICE || 'auto'}
          options={deviceOptions}
          onChange={(v) => setFieldValue('DEVICE', v)}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* BACKEND */}
        <DropdownSelect
          label="推論バックエンド"
          description="モデルの推論実行エンジン（onnxruntime 推奨）"
          value={values.BACKEND || 'onnxruntime'}
          options={backendOptions}
          onChange={(v) => setFieldValue('BACKEND', v)}
        />

        {/* CSV_MAX_PERSONS */}
        <SliderWithInput
          label="CSV出力の最大人数列数"
          description="CSVファイルに関節座標を記録する被写体の最大追跡枠数"
          value={values.CSV_MAX_PERSONS ?? 3}
          min={1}
          max={20}
          step={1}
          unit="人"
          onChange={(v) => setFieldValue('CSV_MAX_PERSONS', Math.round(v))}
          error={errors.CSV_MAX_PERSONS}
        />
      </div>

      {/* Group: YOLO 検出・しきい値設定 */}
      <div className="border border-[#D4DFDC] rounded-lg p-3.5 bg-white">
        <h4 className="text-xs font-bold text-[#0F766E] mb-2">YOLO 検出・しきい値設定</h4>

        <div className="grid grid-cols-2 gap-4">
          <DropdownSelect
            label="YOLOモデル"
            description="人物検出を行うYOLO11モデルのサイズ（n:最速 ～ x:最高精度）"
            value={values.YOLO_MODEL || 'yolo11m.pt'}
            options={yoloModelOptions}
            onChange={(v) => setFieldValue('YOLO_MODEL', v)}
          />

          <SliderWithInput
            label="YOLO バッチサイズ"
            description="一度にGPUへ送るフレーム数（1〜512。CPU時は1固定、VRAM不足時は1へフォールバック）"
            value={values.YOLO_BATCH_SIZE ?? 1}
            min={1}
            max={512}
            step={1}
            unit="枚"
            onChange={(v) => setFieldValue('YOLO_BATCH_SIZE', Math.round(v))}
            error={errors.YOLO_BATCH_SIZE}
          />
        </div>

        <div className="grid grid-cols-2 gap-4 mt-2">
          <SliderWithInput
            label="YOLO 入力解像度"
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
            label="YOLO 検出信頼度"
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
            label="YOLO NMS IoU しきい値"
            description="同一人物に対する重複バウンディングボックスの除外しきい値"
            value={values.YOLO_IOU ?? 0.5}
            min={0.01}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('YOLO_IOU', parseFloat(v.toFixed(2)))}
            error={errors.YOLO_IOU}
          />

          <SliderWithInput
            label="人物クロップ余白率"
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
            label="検出対象クラスID"
            description="0=人物 (person)。複数指定はカンマ区切り"
            value={values.YOLO_CLASSES || [0]}
            onChange={(v) => setFieldValue('YOLO_CLASSES', v)}
            error={errors.YOLO_CLASSES}
          />

          <NullableNumberInput
            label="固定追跡ID"
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
            label="RTMPose モデル"
            description="使用するRTMPoseモデルサイズ（t:最軽量 ～ x:最高精度）"
            value={values.RTMLIB_POSE_MODEL || 'x'}
            options={poseModelChoices}
            onChange={(v) => setFieldValue('RTMLIB_POSE_MODEL', v)}
          />

          <DropdownSelect
            label="入力解像度"
            description="入力解像度（モデル互換性検査あり）"
            value={values.RTMLIB_POSE_INPUT_SIZE || '384x288'}
            options={poseInputChoices}
            onChange={(v) => setFieldValue('RTMLIB_POSE_INPUT_SIZE', v)}
          />
        </div>

        <div className="grid grid-cols-2 gap-4 mt-3">
          <SliderWithInput
            label="RTMPose バッチサイズ"
            description="一度に姿勢推定するフレーム数（1〜512。非対応ONNX/CPU/VRAM不足時は1へフォールバック）"
            value={values.RTMPOSE_BATCH_SIZE ?? 1}
            min={1}
            max={512}
            step={1}
            unit="枚"
            onChange={(v) => setFieldValue('RTMPOSE_BATCH_SIZE', Math.round(v))}
            error={errors.RTMPOSE_BATCH_SIZE}
          />

          <SliderWithInput
            label="関節スコアしきい値"
            description="このスコア未満の関節は未検出として扱います"
            value={values.KEYPOINT_THRESHOLD ?? 0.45}
            min={0.05}
            max={0.95}
            step={0.05}
            onChange={(v) => setFieldValue('KEYPOINT_THRESHOLD', parseFloat(v.toFixed(2)))}
          />
        </div>
      </div>
    </div>
  );
};
