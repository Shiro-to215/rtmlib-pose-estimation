import React from 'react';
import { ToggleSwitch } from '../widgets/ToggleSwitch';
import { SliderWithInput } from '../widgets/SliderWithInput';
import { DropdownSelect } from '../widgets/DropdownSelect';

export interface TrackingWeightsTabProps {
  values: Record<string, any>;
  setFieldValue: (k: string, v: any) => void;
  choices: Record<string, string[]>;
}

export const TrackingWeightsTab: React.FC<TrackingWeightsTabProps> = ({
  values,
  setFieldValue,
  choices,
}) => {
  const trackerChoices = choices.YOLO_TRACKER || ['bytetrack.yaml', 'botsort.yaml'];

  return (
    <div className="space-y-4">
      {/* 1. トラッカー・対象ロック設定 */}
      <div className="border border-[#D4DFDC] rounded-lg p-3.5 bg-white">
        <h4 className="text-xs font-bold text-[#1E293B] mb-2">トラッカー・対象ロック設定</h4>

        <div className="grid grid-cols-2 gap-4">
          <DropdownSelect
            label="トラッカー設定 (YOLO_TRACKER)"
            description="トラッキングアルゴリズム定義ファイル"
            value={values.YOLO_TRACKER || 'bytetrack.yaml'}
            options={trackerChoices}
            onChange={(v) => setFieldValue('YOLO_TRACKER', v)}
          />

          <SliderWithInput
            label="補間上限フレーム (TARGET_BOX_FILL_MAX_FRAMES)"
            description="対象消失時の線形補間を行う上限フレーム数"
            value={values.TARGET_BOX_FILL_MAX_FRAMES ?? 60}
            min={0}
            max={300}
            step={5}
            unit="f"
            onChange={(v) => setFieldValue('TARGET_BOX_FILL_MAX_FRAMES', Math.round(v))}
          />
        </div>

        <div className="grid grid-cols-2 gap-4 mt-2">
          <ToggleSwitch
            label="生IDの優先維持 (TARGET_LOCK_RAW_ID)"
            description="YOLOが割り当てた元の追跡IDを優先的に固定します"
            checked={Boolean(values.TARGET_LOCK_RAW_ID)}
            onChange={(v) => setFieldValue('TARGET_LOCK_RAW_ID', v)}
          />

          <ToggleSwitch
            label="消失時の同ID必須 (TARGET_REQUIRE_SAME_RAW_ID_WHEN_MISSING)"
            description="対象が一度消失した際、同じ生IDが検出されるまで再捕捉を保留"
            checked={Boolean(values.TARGET_REQUIRE_SAME_RAW_ID_WHEN_MISSING)}
            onChange={(v) => setFieldValue('TARGET_REQUIRE_SAME_RAW_ID_WHEN_MISSING', v)}
          />
        </div>

        <div className="grid grid-cols-2 gap-4 mt-2">
          <SliderWithInput
            label="自動選択最低フレーム (TARGET_SELECTION_MIN_FRAMES)"
            description="主要被写体として自動候補に挙がる最低検出フレーム数"
            value={values.TARGET_SELECTION_MIN_FRAMES ?? 15}
            min={1}
            max={300}
            step={1}
            unit="f"
            onChange={(v) => setFieldValue('TARGET_SELECTION_MIN_FRAMES', Math.round(v))}
          />

          <SliderWithInput
            label="自動選択出現率重み (TARGET_SELECTION_COVERAGE_WEIGHT)"
            description="自動選択における全フレームに対する出現割合の考慮度"
            value={values.TARGET_SELECTION_COVERAGE_WEIGHT ?? 0.5}
            min={0.0}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('TARGET_SELECTION_COVERAGE_WEIGHT', parseFloat(v.toFixed(2)))}
          />
        </div>
      </div>

      {/* 2. 再捕捉・距離しきい値 */}
      <div className="border border-[#D4DFDC] rounded-lg p-3.5 bg-white">
        <h4 className="text-xs font-bold text-[#1E293B] mb-2">再捕捉・距離しきい値</h4>
        <div className="grid grid-cols-2 gap-4">
          <SliderWithInput
            label="対象再捕捉最大距離 (TARGET_REACQUIRE_MAX_DISTANCE)"
            description="対象被写体の再捕捉を許容する最大移動距離"
            value={values.TARGET_REACQUIRE_MAX_DISTANCE ?? 300.0}
            min={10.0}
            max={2000.0}
            step={10.0}
            unit="px"
            onChange={(v) => setFieldValue('TARGET_REACQUIRE_MAX_DISTANCE', parseFloat(v.toFixed(1)))}
          />

          <SliderWithInput
            label="対象再捕捉最小IoU (TARGET_REACQUIRE_MIN_IOU)"
            description="対象再捕捉時の最低要求IoU"
            value={values.TARGET_REACQUIRE_MIN_IOU ?? 0.05}
            min={0.0}
            max={1.0}
            step={0.01}
            onChange={(v) => setFieldValue('TARGET_REACQUIRE_MIN_IOU', parseFloat(v.toFixed(2)))}
          />
        </div>

        <div className="grid grid-cols-3 gap-3 mt-2">
          <SliderWithInput
            label="対象マッチングしきい値 (TARGET_TRACK_MATCH_THRESHOLD)"
            value={values.TARGET_TRACK_MATCH_THRESHOLD ?? 0.75}
            min={0.05}
            max={5.0}
            step={0.05}
            onChange={(v) => setFieldValue('TARGET_TRACK_MATCH_THRESHOLD', parseFloat(v.toFixed(2)))}
          />

          <SliderWithInput
            label="対象追跡最小IoU (TARGET_TRACK_MIN_IOU)"
            value={values.TARGET_TRACK_MIN_IOU ?? 0.15}
            min={0.0}
            max={1.0}
            step={0.01}
            onChange={(v) => setFieldValue('TARGET_TRACK_MIN_IOU', parseFloat(v.toFixed(2)))}
          />

          <SliderWithInput
            label="トラック最大マッチ距離 (TRACK_MAX_DISTANCE)"
            value={values.TRACK_MAX_DISTANCE ?? 250.0}
            min={10.0}
            max={1000.0}
            step={10.0}
            unit="px"
            onChange={(v) => setFieldValue('TRACK_MAX_DISTANCE', parseFloat(v.toFixed(1)))}
          />
        </div>

        <div className="grid grid-cols-2 gap-4 mt-2">
          <SliderWithInput
            label="トラック消失許容フレーム (TRACK_MAX_MISSED_FRAMES)"
            description="検出が途絶えてからトラックを終了するまでのフレーム数"
            value={values.TRACK_MAX_MISSED_FRAMES ?? 8}
            min={1}
            max={120}
            step={1}
            unit="f"
            onChange={(v) => setFieldValue('TRACK_MAX_MISSED_FRAMES', Math.round(v))}
          />

          <SliderWithInput
            label="全般マッチコストしきい値 (TRACK_MATCH_THRESHOLD)"
            description="トラック関連付け時の最大許容コスト"
            value={values.TRACK_MATCH_THRESHOLD ?? 2.0}
            min={0.1}
            max={10.0}
            step={0.1}
            onChange={(v) => setFieldValue('TRACK_MATCH_THRESHOLD', parseFloat(v.toFixed(2)))}
          />
        </div>
      </div>

      {/* 3. トラッキングコスト重み */}
      <div className="border border-[#D4DFDC] rounded-lg p-3.5 bg-white">
        <h4 className="text-xs font-bold text-[#1E293B] mb-2">トラックマッチング コスト重み</h4>
        <div className="grid grid-cols-4 gap-3">
          <SliderWithInput
            label="中心距離 (TRACK_CENTER_WEIGHT)"
            value={values.TRACK_CENTER_WEIGHT ?? 0.35}
            min={0.0}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('TRACK_CENTER_WEIGHT', parseFloat(v.toFixed(2)))}
          />
          <SliderWithInput
            label="関節点距離 (TRACK_KEYPOINT_WEIGHT)"
            value={values.TRACK_KEYPOINT_WEIGHT ?? 0.35}
            min={0.0}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('TRACK_KEYPOINT_WEIGHT', parseFloat(v.toFixed(2)))}
          />
          <SliderWithInput
            label="ポーズ姿勢 (TRACK_POSE_WEIGHT)"
            value={values.TRACK_POSE_WEIGHT ?? 0.2}
            min={0.0}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('TRACK_POSE_WEIGHT', parseFloat(v.toFixed(2)))}
          />
          <SliderWithInput
            label="ボックス形状 (TRACK_BBOX_WEIGHT)"
            value={values.TRACK_BBOX_WEIGHT ?? 0.1}
            min={0.0}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('TRACK_BBOX_WEIGHT', parseFloat(v.toFixed(2)))}
          />
        </div>

        <div className="grid grid-cols-4 gap-3 mt-2">
          <SliderWithInput
            label="速度平滑化 (TRACK_VELOCITY_SMOOTHING)"
            value={values.TRACK_VELOCITY_SMOOTHING ?? 0.35}
            min={0.0}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('TRACK_VELOCITY_SMOOTHING', parseFloat(v.toFixed(2)))}
          />
          <SliderWithInput
            label="生ID一致ボーナス (TRACK_RAW_ID_BONUS)"
            value={values.TRACK_RAW_ID_BONUS ?? 2.0}
            min={0.0}
            max={10.0}
            step={0.2}
            onChange={(v) => setFieldValue('TRACK_RAW_ID_BONUS', parseFloat(v.toFixed(2)))}
          />
          <SliderWithInput
            label="移動予測重み (TRACK_PREDICTED_BOX_WEIGHT)"
            value={values.TRACK_PREDICTED_BOX_WEIGHT ?? 0.35}
            min={0.0}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('TRACK_PREDICTED_BOX_WEIGHT', parseFloat(v.toFixed(2)))}
          />
          <SliderWithInput
            label="先読み最大フレーム (TRACK_PREDICTION_MAX_FRAMES)"
            value={values.TRACK_PREDICTION_MAX_FRAMES ?? 2}
            min={0}
            max={10}
            step={1}
            unit="f"
            onChange={(v) => setFieldValue('TRACK_PREDICTION_MAX_FRAMES', Math.round(v))}
          />
        </div>
      </div>

      {/* 4. 骨格追跡重み */}
      <div className="border border-[#D4DFDC] rounded-lg p-3.5 bg-white">
        <h4 className="text-xs font-bold text-[#1E293B] mb-2">骨格追跡・時系列関連付け重み</h4>
        <div className="grid grid-cols-3 gap-3">
          <SliderWithInput
            label="関節点重み (POSE_TRACK_KEYPOINT_WEIGHT)"
            value={values.POSE_TRACK_KEYPOINT_WEIGHT ?? 0.65}
            min={0.0}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('POSE_TRACK_KEYPOINT_WEIGHT', parseFloat(v.toFixed(2)))}
          />
          <SliderWithInput
            label="中心座標重み (POSE_TRACK_CENTER_WEIGHT)"
            value={values.POSE_TRACK_CENTER_WEIGHT ?? 0.25}
            min={0.0}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('POSE_TRACK_CENTER_WEIGHT', parseFloat(v.toFixed(2)))}
          />
          <SliderWithInput
            label="身体形状重み (POSE_TRACK_SHAPE_WEIGHT)"
            value={values.POSE_TRACK_SHAPE_WEIGHT ?? 0.1}
            min={0.0}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('POSE_TRACK_SHAPE_WEIGHT', parseFloat(v.toFixed(2)))}
          />
        </div>

        <div className="grid grid-cols-3 gap-3 mt-2">
          <SliderWithInput
            label="クロップIoU重み (POSE_BOX_IOU_WEIGHT)"
            value={values.POSE_BOX_IOU_WEIGHT ?? 2.0}
            min={0.0}
            max={10.0}
            step={0.2}
            onChange={(v) => setFieldValue('POSE_BOX_IOU_WEIGHT', parseFloat(v.toFixed(2)))}
          />
          <SliderWithInput
            label="クロップ中心重み (POSE_BOX_CENTER_WEIGHT)"
            value={values.POSE_BOX_CENTER_WEIGHT ?? 0.5}
            min={0.0}
            max={5.0}
            step={0.1}
            onChange={(v) => setFieldValue('POSE_BOX_CENTER_WEIGHT', parseFloat(v.toFixed(2)))}
          />
          <SliderWithInput
            label="時間的連続性重み (POSE_TEMPORAL_WEIGHT)"
            value={values.POSE_TEMPORAL_WEIGHT ?? 0.5}
            min={0.0}
            max={5.0}
            step={0.1}
            onChange={(v) => setFieldValue('POSE_TEMPORAL_WEIGHT', parseFloat(v.toFixed(2)))}
          />
        </div>
      </div>
    </div>
  );
};
