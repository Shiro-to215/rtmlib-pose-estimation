import React, { useState } from 'react';
import { ChevronLeft, RotateCcw, Save } from 'lucide-react';
import { JobSettings, ReservationJob } from '../../types/models';
import { useSettingsForm } from './hooks/useSettingsForm';
import { DefaultIoCard } from './cards/DefaultIoCard';
import { JobIoCard } from './cards/JobIoCard';
import { GeneralOutputTab } from './cards/GeneralOutputTab';
import { TrackingWeightsTab } from './cards/TrackingWeightsTab';
import { VisualizationTab } from './cards/VisualizationTab';

export interface SettingsViewProps {
  mode: 'default' | 'job';
  job?: ReservationJob;
  defaultSettings: Partial<JobSettings>;
  systemInfo: {
    output_root: string;
    choices: Record<string, string[]>;
    labels?: Record<string, string>;
  };
  onBack: () => void;
  onSaveDefault: (settings: Partial<JobSettings>, defaultRoot: string) => Promise<boolean>;
  onSaveJob: (
    jobId: string,
    settings: Partial<JobSettings>,
    resetFailed: boolean,
    destination?: string
  ) => Promise<boolean>;
}

type TabType = 'general' | 'tracking' | 'visualization';

const JOB_SCOPED_SETTING_KEYS = new Set([
  'INPUT_ROOT',
  'INPUT_VIDEO_NAME',
  'OUTPUT_DIRECTORY',
  'OUTPUT_ROOT',
  'OUTPUT_FOLDER_NAME',
  'OUTPUT_VIDEO_NAME',
  'OUTPUT_CROP_VIDEO_NAME',
  'OUTPUT_CROP_SKELETON_VIDEO_NAME',
  'OUTPUT_CSV_NAME',
  'OUTPUT_METADATA_NAME',
  'OUTPUT_METADATA_JSON_NAME',
  'OUTPUT_NPZ_NAME',
]);

function extractEngineParams(source: Record<string, any>): Record<string, any> {
  const result: Record<string, any> = {};
  for (const [k, v] of Object.entries(source || {})) {
    if (!JOB_SCOPED_SETTING_KEYS.has(k)) {
      result[k] = v;
    }
  }
  return result;
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  mode,
  job,
  defaultSettings,
  systemInfo,
  onBack,
  onSaveDefault,
  onSaveJob,
}) => {
  const initialData = mode === 'job' && job ? job.settings : defaultSettings;
  const { values, setFieldValue, resetToDefaults, errors, rtmlibWarning, isDirty, isValid } =
    useSettingsForm(initialData, mode);

  const [activeTab, setActiveTab] = useState<TabType>('general');
  const [defaultRoot, setDefaultRoot] = useState<string>(systemInfo.output_root || '');
  const [destination, setDestination] = useState<string>(job?.output_path || '');
  const [resetFailed, setResetFailed] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);

  React.useEffect(() => {
    setDefaultRoot(systemInfo.output_root || '');
  }, [systemInfo.output_root]);

  React.useEffect(() => {
    setDestination(job?.output_path || '');
    setResetFailed(true);
  }, [job]);

  const hasIoPathChanges =
    mode === 'default'
      ? defaultRoot.trim() !== (systemInfo.output_root || '').trim()
      : destination.trim() !== (job?.output_path || '').trim();

  const canSave =
    isValid &&
    !isSaving &&
    (isDirty || hasIoPathChanges || (mode === 'job' && job?.state === 'failed' && resetFailed));

  const handleBack = () => {
    if (isDirty || hasIoPathChanges) {
      const confirmDiscard = window.confirm('変更が保存されていません。破棄して戻りますか？');
      if (!confirmDiscard) return;
    }
    onBack();
  };

  const handleSecondaryAction = () => {
    if (mode === 'default') {
      resetToDefaults({
        DEVICE: 'auto',
        CAPTURE_FPS: null,
        YOLO_MODEL: 'yolo11m.pt',
        BACKEND: 'onnxruntime',
        YOLO_IMAGE_SIZE: 1280,
        YOLO_CONFIDENCE: 0.2,
        YOLO_IOU: 0.5,
        YOLO_CLASSES: [0],
        YOLO_BATCH_SIZE: 1,
        KEYPOINT_THRESHOLD: 0.45,
        POSE_ENGINE: 'rtmpose',
        RTMLIB_POSE_MODEL: 'x',
        RTMLIB_POSE_INPUT_SIZE: '384x288',
        RTMPOSE_BATCH_SIZE: 1,
        VITPOSE_MODEL: 'h',
        VITPOSE_INPUT_SIZE: '256x192',
        VITPOSE_PRECISION: 'fp16',
        VITPOSE_BATCH_SIZE: 4,
        VITPOSE_FLIP_TEST: true,
        YOLO_TRACKER: 'bytetrack.yaml',
        TARGET_SELECTION_MIN_FRAMES: 15,
        TARGET_SELECTION_COVERAGE_WEIGHT: 0.5,
        TARGET_BOX_FILL_MAX_FRAMES: 60,
        TRACK_MAX_MISSED_FRAMES: 8,
        TRACK_MATCH_THRESHOLD: 2.0,
        TRACK_VELOCITY_SMOOTHING: 0.35,
        TRACK_RAW_ID_BONUS: 2.0,
        TRACK_PREDICTED_BOX_WEIGHT: 0.35,
        TRACK_PREDICTION_MAX_FRAMES: 2,
        SKELETON_LINE_WIDTH: 2,
        KEYPOINT_RADIUS: 4,
        LABEL_FONT_SCALE: 1.0,
      });
    } else {
      resetToDefaults(extractEngineParams(defaultSettings));
    }
  };

  const handleSave = async () => {
    if (!canSave) return;
    setIsSaving(true);
    let success = false;
    if (mode === 'default') {
      success = await onSaveDefault(extractEngineParams(values), defaultRoot);
    } else if (job) {
      const savePayload: Partial<JobSettings> = { ...extractEngineParams(values) };
      success = await onSaveJob(job.id, savePayload, resetFailed, destination);
    }
    setIsSaving(false);
    if (success) {
      onBack();
    }
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden select-none">
      {/* Top Header Strip directly on #ECEEEF */}
      <div className="pb-3 flex items-center justify-between gap-3 flex-shrink-0">
        <div className="flex items-center gap-2.5 min-w-0">
          {mode === 'job' ? (
            <div className="flex items-center gap-2 min-w-0">
              <button
                type="button"
                onClick={handleBack}
                className="inline-flex items-center gap-1 text-xs font-medium text-[#71717A] hover:text-[#111111] transition-colors cursor-pointer flex-shrink-0"
              >
                <ChevronLeft className="w-3.5 h-3.5" strokeWidth={1.6} />
                <span>予約リスト</span>
              </button>
              <span className="text-xs text-[#A1A1AA]">/</span>
              <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-[#111111] truncate max-w-md">
                個別設定 — {job?.video_name || ''}
              </h2>
            </div>
          ) : (
            <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-[#111111]">
              基本設定（全体の初期値）
            </h2>
          )}

          {(isDirty || hasIoPathChanges) && (
            <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#111111] bg-white border border-black/[0.08] px-2.5 py-0.5 rounded-[6px] flex-shrink-0">
              <span className="w-1.5 h-1.5 rounded-full bg-[#111111]" />
              <span>未保存の変更あり</span>
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={handleSecondaryAction}
            className="h-8 px-3 rounded-[6px] bg-white border border-black/[0.08] hover:bg-[#F4F5F6] text-xs font-medium text-[#111111] inline-flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <RotateCcw className="w-3.5 h-3.5 text-[#71717A]" strokeWidth={1.6} />
            <span>{mode === 'default' ? '初期値に戻す' : '基本設定を反映'}</span>
          </button>

          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave}
            className={`h-8 px-4 rounded-[6px] text-xs font-semibold inline-flex items-center gap-1.5 transition-colors ${
              canSave
                ? 'bg-[#111111] hover:bg-[#27272A] text-white cursor-pointer'
                : 'bg-[#D9DCE0] text-[#8E8E98] cursor-not-allowed'
            }`}
          >
            <Save className="w-3.5 h-3.5" strokeWidth={1.6} />
            <span>
              {isSaving
                ? '保存中...'
                : mode === 'default'
                ? '基本設定を保存'
                : 'この予約に保存'}
            </span>
          </button>
        </div>
      </div>

      {/* Monochrome Underline Sub-Tab Navigation */}
      <div className="flex items-center gap-6 border-b border-black/[0.08] flex-shrink-0">
        <button
          type="button"
          onClick={() => setActiveTab('general')}
          className={`pb-2.5 text-xs border-b-2 -mb-px transition-colors cursor-pointer inline-flex items-center gap-1.5 ${
            activeTab === 'general'
              ? 'border-[#111111] text-[#111111] font-semibold'
              : 'border-transparent text-[#71717A] hover:text-[#111111] font-medium'
          }`}
        >
          <span>基本・出力設定</span>
          {rtmlibWarning && <span className="w-1.5 h-1.5 rounded-full bg-[#B91C1C]" />}
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('tracking')}
          className={`pb-2.5 text-xs border-b-2 -mb-px transition-colors cursor-pointer ${
            activeTab === 'tracking'
              ? 'border-[#111111] text-[#111111] font-semibold'
              : 'border-transparent text-[#71717A] hover:text-[#111111] font-medium'
          }`}
        >
          トラッキング・重み設定
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('visualization')}
          className={`pb-2.5 text-xs border-b-2 -mb-px transition-colors cursor-pointer ${
            activeTab === 'visualization'
              ? 'border-[#111111] text-[#111111] font-semibold'
              : 'border-transparent text-[#71717A] hover:text-[#111111] font-medium'
          }`}
        >
          可視化・オーバーレイ設定
        </button>
      </div>

      {/* Scrollable Bento Cards Area */}
      <div className="flex-1 min-h-0 overflow-y-auto pt-3 pr-1 pb-2 space-y-3">
        {mode === 'default' ? (
          <DefaultIoCard
            defaultRoot={defaultRoot}
            onChangeDefaultRoot={setDefaultRoot}
          />
        ) : (
          job && (
            <JobIoCard
              job={job}
              destination={destination}
              onChangeDestination={setDestination}
              resetFailed={resetFailed}
              onChangeResetFailed={setResetFailed}
            />
          )
        )}

        <div key={activeTab} className="view-fade-in">
          {activeTab === 'general' && (
            <GeneralOutputTab
              values={values}
              setFieldValue={setFieldValue}
              choices={systemInfo.choices}
              errors={errors}
              rtmlibWarning={rtmlibWarning}
            />
          )}
          {activeTab === 'tracking' && (
            <TrackingWeightsTab
              values={values}
              setFieldValue={setFieldValue}
              choices={systemInfo.choices}
            />
          )}
          {activeTab === 'visualization' && (
            <VisualizationTab values={values} setFieldValue={setFieldValue} />
          )}
        </div>
      </div>
    </div>
  );
};
