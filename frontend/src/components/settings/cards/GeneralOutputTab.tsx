import React from 'react';
import { AlertTriangle, Cpu, Sparkles } from 'lucide-react';
import { DropdownSelect } from '../widgets/DropdownSelect';
import { SliderWithInput } from '../widgets/SliderWithInput';
import { TagListInput } from '../widgets/TagListInput';
import { NullableNumberInput } from '../widgets/NullableNumberInput';
import { ToggleSwitch } from '../widgets/ToggleSwitch';

export interface GeneralOutputTabProps {
  values: Record<string, any>;
  setFieldValue: (k: string, v: any) => void;
  choices: Record<string, string[]>;
  errors: Record<string, string>;
  rtmlibWarning: string | null;
}

const VITPOSE_MODEL_LABELS: Record<string, string> = {
  s: 'S (Small / 最軽量)',
  b: 'B (Base / バランス)',
  l: 'L (Large / 高精度)',
  h: 'H (Huge / 最高精度)',
};

export const GeneralOutputTab: React.FC<GeneralOutputTabProps> = ({
  values,
  setFieldValue,
  choices,
  errors,
  rtmlibWarning,
}) => {
  const poseEngine = String(values.POSE_ENGINE || 'rtmpose').toLowerCase() === 'vitpose'
    ? 'vitpose'
    : 'rtmpose';
  const deviceOptions = choices.DEVICE || ['auto', 'cpu', 'cuda'];
  const toYoloFile = (opt: string) =>
    opt.startsWith('yolo11') && opt.endsWith('.pt') ? opt : `yolo11${opt}.pt`;
  const toYoloShort = (opt: string) => opt.replace(/^yolo11|\.pt$/g, '');
  const yoloModelOptions = (choices.YOLO_MODEL || ['n', 's', 'm', 'l', 'x']).map((opt) => ({
    value: toYoloFile(opt),
    label: toYoloShort(opt),
  }));
  const currentYoloModel = toYoloFile(values.YOLO_MODEL || 'yolo11m.pt');
  const backendOptions = choices.BACKEND || ['onnxruntime', 'opencv'];
  const poseModelChoices = choices.RTMLIB_POSE_MODEL || ['t', 's', 'm', 'l', 'x'];
  const poseInputChoices = choices.RTMLIB_POSE_INPUT_SIZE || ['256x192', '384x288'];
  const vitposeModelOptions = (choices.VITPOSE_MODEL || ['s', 'b', 'l', 'h']).map((opt) => ({
    value: opt,
    label: VITPOSE_MODEL_LABELS[opt] || opt.toUpperCase(),
  }));

  return (
    <div className="space-y-4">
      {/* Pose Model Compatibility Warning Banner */}
      {rtmlibWarning && (
        <div className="flex items-center gap-2 p-3 bg-[#FEF2F2] border border-[#F5C2C0] rounded-lg text-xs text-[#C8332B] font-medium">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 text-[#C8332B]" />
          <span>{rtmlibWarning}</span>
        </div>
      )}

      {/* 姿勢推定エンジン切り替え */}
      <div className="border border-[#D4DFDC] rounded-lg p-3.5 bg-white">
        <div className="flex items-center justify-between mb-2">
          <div>
            <h4 className="text-xs font-bold text-[#1E293B]">姿勢推定エンジン</h4>
            <p className="text-[11px] text-[#64748B]">
              ジョブで使用する骨格推定エンジンを選択します（非選択側の設定も保持されます）
            </p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          <button
            type="button"
            onClick={() => setFieldValue('POSE_ENGINE', 'rtmpose')}
            className={`flex items-start gap-2.5 p-3 rounded-lg border text-left transition-all cursor-pointer ${
              poseEngine === 'rtmpose'
                ? 'border-[#0369A1] bg-[#F0F9FF] ring-1 ring-[#0369A1]'
                : 'border-[#D4DFDC] bg-white hover:bg-[#F8FAFA]'
            }`}
          >
            <Cpu className={`w-4 h-4 mt-0.5 flex-shrink-0 ${poseEngine === 'rtmpose' ? 'text-[#0369A1]' : 'text-[#64748B]'}`} />
            <div>
              <div className={`text-xs font-bold ${poseEngine === 'rtmpose' ? 'text-[#0369A1]' : 'text-[#1E293B]'}`}>
                RTMPose（高速・省メモリ / ONNX）
              </div>
              <div className="text-[11px] text-[#64748B] mt-0.5">
                軽量で高速。動作確認や長尺動画の迅速な処理に最適
              </div>
            </div>
          </button>

          <button
            type="button"
            onClick={() => setFieldValue('POSE_ENGINE', 'vitpose')}
            className={`flex items-start gap-2.5 p-3 rounded-lg border text-left transition-all cursor-pointer ${
              poseEngine === 'vitpose'
                ? 'border-[#7C3AED] bg-[#F5F3FF] ring-1 ring-[#7C3AED]'
                : 'border-[#D4DFDC] bg-white hover:bg-[#F8FAFA]'
            }`}
          >
            <Sparkles className={`w-4 h-4 mt-0.5 flex-shrink-0 ${poseEngine === 'vitpose' ? 'text-[#7C3AED]' : 'text-[#64748B]'}`} />
            <div>
              <div className={`text-xs font-bold ${poseEngine === 'vitpose' ? 'text-[#7C3AED]' : 'text-[#1E293B]'}`}>
                ViTPose++（研究用・最高精度 / PyTorch）
              </div>
              <div className="text-[11px] text-[#64748B] mt-0.5">
                Classic デコーダ・UDP後処理・FP16・Flip Test 対応の高精度パイプライン
              </div>
            </div>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* DEVICE */}
        <DropdownSelect
          label="推論実行デバイス"
          description="YOLOおよび姿勢推定モデルを実行するハードウェア（auto: 自動判定, cuda: GPU, cpu: CPU）"
          value={values.DEVICE || 'auto'}
          options={deviceOptions}
          onChange={(v) => setFieldValue('DEVICE', v)}
        />

        {/* CAPTURE_FPS */}
        <NullableNumberInput
          label="元動画の撮影フレームレート (FPS)"
          description="スローモーション再生動画などの実際の撮影fps（例: 240, 119.88）。空欄時はメタデータまたは動画再生FPSから自動取得"
          value={values.CAPTURE_FPS ?? null}
          allowFloat
          min={0.1}
          step="any"
          placeholder="空欄（自動取得）"
          onChange={(v) => setFieldValue('CAPTURE_FPS', v)}
          error={errors.CAPTURE_FPS}
        />
      </div>

      {/* Group: YOLO 検出・しきい値設定 */}
      <div className="border border-[#D4DFDC] rounded-lg p-3.5 bg-white">
        <h4 className="text-xs font-bold text-[#0F766E] mb-2">YOLO 検出・しきい値設定</h4>

        <div className="grid grid-cols-2 gap-4">
          <DropdownSelect
            label="YOLOモデル"
            description="人物検出を行うYOLO11モデルのサイズ（n:最速 ～ x:最高精度）"
            value={currentYoloModel}
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

          <TagListInput
            label="検出対象クラスID"
            description="0=人物 (person)。複数指定はカンマ区切り"
            value={values.YOLO_CLASSES || [0]}
            onChange={(v) => setFieldValue('YOLO_CLASSES', v)}
            error={errors.YOLO_CLASSES}
          />
        </div>
      </div>

      {/* 選択中の推論エンジン専用設定 */}
      {poseEngine === 'rtmpose' ? (
        <div className="border border-[#D4DFDC] rounded-lg p-3.5 bg-white">
          <h4 className="text-xs font-bold text-[#0369A1] mb-2">RTMPose 骨格推定設定（ONNX / OpenCV）</h4>

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

            <DropdownSelect
              label="推論バックエンド"
              description="RTMPoseの実行バックエンド（onnxruntime 推奨）"
              value={values.BACKEND || 'onnxruntime'}
              options={backendOptions}
              onChange={(v) => setFieldValue('BACKEND', v)}
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
      ) : (
        <div className="border border-[#DDD6FE] rounded-lg p-3.5 bg-white">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-bold text-[#7C3AED]">ViTPose++ 骨格推定設定（ONNX Runtime / PyTorch）</h4>
            <span className="text-[11px] font-mono font-bold text-[#6D28D9] bg-[#F5F3FF] border border-[#DDD6FE] px-2 py-0.5 rounded">
              解像度: 256×192 (4:3 標準固定) / UDP デコーダ
            </span>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <DropdownSelect
              label="ViTPose++ モデルサイズ"
              description="研究本番は H、動作確認は B/L など（usyd-community/vitpose-plus-*）"
              value={String(values.VITPOSE_MODEL || 'h').toLowerCase()}
              options={vitposeModelOptions}
              onChange={(v) => setFieldValue('VITPOSE_MODEL', v)}
            />

            <DropdownSelect
              label="計算精度 (CUDA)"
              description="FP16 は高速・省VRAM、FP32 は単精度（CPU時は自動で FP32 動作）"
              value={String(values.VITPOSE_PRECISION || 'fp16').toLowerCase()}
              options={[
                { value: 'fp16', label: 'FP16 (半精度・高速)' },
                { value: 'fp32', label: 'FP32 (単精度・高精度)' },
              ]}
              onChange={(v) => setFieldValue('VITPOSE_PRECISION', v)}
            />

            <ToggleSwitch
              label="Flip Test（左右反転 TTA）"
              description="反転画像のヒートマップを平均化し精度・安定性を向上（OFFで速度約2倍）"
              checked={values.VITPOSE_FLIP_TEST !== false}
              onChange={(v) => setFieldValue('VITPOSE_FLIP_TEST', v)}
            />
          </div>

          <div className="grid grid-cols-2 gap-4 mt-3">
            <SliderWithInput
              label="ViTPose++ バッチサイズ"
              description="1〜64 の範囲で指定（推奨: 4〜8、高VRAM GPU / Colab利用時は拡大可。VRAM不足時は自動調整）"
              value={values.VITPOSE_BATCH_SIZE ?? 4}
              min={1}
              max={64}
              step={1}
              unit="枚"
              onChange={(v) => setFieldValue('VITPOSE_BATCH_SIZE', Math.round(v))}
              error={errors.VITPOSE_BATCH_SIZE}
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

          <div className="mt-3 p-2.5 rounded-md bg-[#F5F3FF] border border-[#EDE9FE] text-[11px] text-[#5B21B6] leading-relaxed">
            <strong>内部最適化仕様（固定）:</strong> Pass 1（YOLO）の VRAM 解放後に ONNX Runtime（不可時は PyTorch）で推論を実行し、CUDA時は指定精度（FP16/FP32）、UDP サブピクセル座標算出は FP32 で行ってジッターを抑制します。
          </div>
        </div>
      )}
    </div>
  );
};
