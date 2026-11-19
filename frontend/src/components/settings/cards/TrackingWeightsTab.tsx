import React from 'react';
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
    <div className="space-y-3">
      {/* 1. トラッカー・主要人物選択設定 */}
      <div className="bg-white rounded-[14px] p-5">
        <h4 className="text-xs font-semibold text-[#111111] mb-2">トラッカー・主要被写体選択設定</h4>

        <div className="grid grid-cols-2 gap-4">
          <DropdownSelect
            label="トラッカー設定"
            description="トラッキングアルゴリズム定義ファイル"
            value={values.YOLO_TRACKER || 'bytetrack.yaml'}
            options={trackerChoices}
            onChange={(v) => setFieldValue('YOLO_TRACKER', v)}
          />

          <SliderWithInput
            label="補間上限フレーム"
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
          <SliderWithInput
            label="自動選択最低フレーム"
            description="主要被写体として自動候補に挙がる最低検出フレーム数"
            value={values.TARGET_SELECTION_MIN_FRAMES ?? 15}
            min={1}
            max={300}
            step={1}
            unit="f"
            onChange={(v) => setFieldValue('TARGET_SELECTION_MIN_FRAMES', Math.round(v))}
          />

          <SliderWithInput
            label="自動選択出現率重み"
            description="自動選択における全フレームに対する出現割合の考慮度"
            value={values.TARGET_SELECTION_COVERAGE_WEIGHT ?? 0.5}
            min={0.0}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('TARGET_SELECTION_COVERAGE_WEIGHT', parseFloat(v.toFixed(2)))}
          />
        </div>
      </div>

      {/* 2. トラック安定化・再関連付け設定 */}
      <div className="bg-white rounded-[14px] p-5">
        <h4 className="text-xs font-semibold text-[#111111] mb-2">トラック安定化・再関連付け設定</h4>

        <div className="grid grid-cols-2 gap-4">
          <SliderWithInput
            label="トラック消失許容フレーム"
            description="検出が途絶えてからトラックを終了するまでのフレーム数"
            value={values.TRACK_MAX_MISSED_FRAMES ?? 8}
            min={1}
            max={120}
            step={1}
            unit="f"
            onChange={(v) => setFieldValue('TRACK_MAX_MISSED_FRAMES', Math.round(v))}
          />

          <SliderWithInput
            label="マッチコストしきい値"
            description="トラック関連付け時の最大許容コスト"
            value={values.TRACK_MATCH_THRESHOLD ?? 2.0}
            min={0.1}
            max={10.0}
            step={0.1}
            onChange={(v) => setFieldValue('TRACK_MATCH_THRESHOLD', parseFloat(v.toFixed(2)))}
          />
        </div>

        <div className="grid grid-cols-2 gap-4 mt-2">
          <SliderWithInput
            label="速度平滑化"
            description="移動速度推定の指数平滑化係数"
            value={values.TRACK_VELOCITY_SMOOTHING ?? 0.35}
            min={0.0}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('TRACK_VELOCITY_SMOOTHING', parseFloat(v.toFixed(2)))}
          />

          <SliderWithInput
            label="生ID一致ボーナス"
            description="YOLOの生IDが一致した場合のコスト低減ボーナス"
            value={values.TRACK_RAW_ID_BONUS ?? 2.0}
            min={0.0}
            max={10.0}
            step={0.2}
            onChange={(v) => setFieldValue('TRACK_RAW_ID_BONUS', parseFloat(v.toFixed(2)))}
          />
        </div>

        <div className="grid grid-cols-2 gap-4 mt-2">
          <SliderWithInput
            label="移動予測重み"
            description="速度予測ボックスと検出ボックスのIoUコスト重み"
            value={values.TRACK_PREDICTED_BOX_WEIGHT ?? 0.35}
            min={0.0}
            max={1.0}
            step={0.05}
            onChange={(v) => setFieldValue('TRACK_PREDICTED_BOX_WEIGHT', parseFloat(v.toFixed(2)))}
          />

          <SliderWithInput
            label="先読み最大フレーム"
            description="位置予測に用いる欠損フレーム数の上限"
            value={values.TRACK_PREDICTION_MAX_FRAMES ?? 2}
            min={0}
            max={10}
            step={1}
            unit="f"
            onChange={(v) => setFieldValue('TRACK_PREDICTION_MAX_FRAMES', Math.round(v))}
          />
        </div>
      </div>
    </div>
  );
};
