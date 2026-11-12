import React from 'react';
import { DropdownSelect } from '../widgets/DropdownSelect';
import { SliderWithInput } from '../widgets/SliderWithInput';

export interface GeneralOutputTabProps {
  values: Record<string, any>;
  setFieldValue: (k: string, v: any) => void;
  choices: Record<string, string[]>;
  errors: Record<string, string>;
}

export const GeneralOutputTab: React.FC<GeneralOutputTabProps> = ({
  values,
  setFieldValue,
  choices,
  errors,
}) => {
  const deviceOptions = choices.DEVICE || ['auto', 'cpu', 'cuda'];
  const yoloModelOptions = choices.YOLO_MODEL || ['yolo11n.pt', 'yolo11s.pt', 'yolo11m.pt', 'yolo11l.pt', 'yolo11x.pt'];
  const backendOptions = choices.BACKEND || ['onnxruntime', 'opencv'];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        {/* DEVICE */}
        <DropdownSelect
          label="推論実行デバイス (DEVICE)"
          description="YOLOおよび姿勢推定モデルを実行するハードウェア（auto: 自動判定, cuda: GPU, cpu: CPU）"
          value={values.DEVICE || 'auto'}
          options={deviceOptions}
          onChange={(v) => setFieldValue('DEVICE', v)}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* YOLO_MODEL */}
        <DropdownSelect
          label="YOLOモデル (YOLO_MODEL)"
          description="人物検出を行うYOLO11モデルのサイズ（n:最速 ～ x:最高精度）"
          value={values.YOLO_MODEL || 'yolo11m.pt'}
          options={yoloModelOptions}
          onChange={(v) => setFieldValue('YOLO_MODEL', v)}
        />

        {/* BACKEND */}
        <DropdownSelect
          label="推論バックエンド (BACKEND)"
          description="モデルの推論実行エンジン（onnxruntime 推奨）"
          value={values.BACKEND || 'onnxruntime'}
          options={backendOptions}
          onChange={(v) => setFieldValue('BACKEND', v)}
        />
      </div>

      {/* CSV_MAX_PERSONS */}
      <SliderWithInput
        label="CSV出力の最大人数列数 (CSV_MAX_PERSONS)"
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
  );
};
