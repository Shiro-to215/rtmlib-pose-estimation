import React from 'react';
import { ToggleSwitch } from '../widgets/ToggleSwitch';
import { SliderWithInput } from '../widgets/SliderWithInput';

export interface VisualizationTabProps {
  values: Record<string, any>;
  setFieldValue: (k: string, v: any) => void;
}

export const VisualizationTab: React.FC<VisualizationTabProps> = ({
  values,
  setFieldValue,
}) => {
  return (
    <div className="space-y-4">
      <div className="border border-[#D4DFDC] rounded-lg p-3.5 bg-white">
        <h4 className="text-xs font-bold text-[#1E293B] mb-2">描画要素の表示・非表示</h4>
        <div className="grid grid-cols-2 gap-4">
          <ToggleSwitch
            label="骨格ライン・関節描画"
            description="出力動画に人物骨格ラインと関節点を描画します"
            checked={values.DRAW_SKELETON !== false}
            onChange={(v) => setFieldValue('DRAW_SKELETON', v)}
          />

          <ToggleSwitch
            label="バウンディングボックス描画"
            description="出力動画に人物の検出枠および追跡IDを描画します"
            checked={values.DRAW_BBOX !== false}
            onChange={(v) => setFieldValue('DRAW_BBOX', v)}
          />
        </div>
      </div>

      <div className="border border-[#D4DFDC] rounded-lg p-3.5 bg-white">
        <h4 className="text-xs font-bold text-[#1E293B] mb-2">描画スタイル・サイズ調整</h4>
        <div className="grid grid-cols-3 gap-3">
          <SliderWithInput
            label="骨格ライン線幅"
            description="骨格ボーンの描画太さ"
            value={values.SKELETON_LINE_WIDTH ?? 2}
            min={1}
            max={8}
            step={1}
            unit="px"
            onChange={(v) => setFieldValue('SKELETON_LINE_WIDTH', Math.round(v))}
          />

          <SliderWithInput
            label="関節点サークル半径"
            description="各関節キーポイントの円半径"
            value={values.KEYPOINT_RADIUS ?? 4}
            min={1}
            max={12}
            step={1}
            unit="px"
            onChange={(v) => setFieldValue('KEYPOINT_RADIUS', Math.round(v))}
          />

          <SliderWithInput
            label="ラベル文字倍率"
            description="追跡IDやフレーム番号テキストのフォント倍率"
            value={values.LABEL_FONT_SCALE ?? 0.7}
            min={0.3}
            max={2.0}
            step={0.05}
            onChange={(v) => setFieldValue('LABEL_FONT_SCALE', parseFloat(v.toFixed(2)))}
          />
        </div>
      </div>
    </div>
  );
};
