import React from 'react';
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
    <div className="space-y-3">
      <div className="bg-white rounded-[14px] p-5">
        <h4 className="text-xs font-semibold text-[#111111] mb-2">描画スタイル・サイズ調整</h4>
        <div className="grid grid-cols-3 gap-4">
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
            description="フレーム番号テキストのフォント倍率"
            value={values.LABEL_FONT_SCALE ?? 1.0}
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
