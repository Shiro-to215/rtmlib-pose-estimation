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
  'THUMBNAIL_ROOT',
  'THUMBNAIL_IMAGE_NAME',
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
  const initialThumbPath = React.useMemo(() => {
    const tRoot = job?.settings?.THUMBNAIL_ROOT ? String(job.settings.THUMBNAIL_ROOT) : '';
    const tName = job?.settings?.THUMBNAIL_IMAGE_NAME ? String(job.settings.THUMBNAIL_IMAGE_NAME) : '';
    if (tRoot && tName) {
      const sep = tRoot.includes('/') && !tRoot.includes('\\') ? '/' : '\\';
      return `${tRoot.replace(/[\\/]+$/, '')}${sep}${tName}`;
    }
    return '';
  }, [job]);

  const initialData = mode === 'job' && job ? job.settings : defaultSettings;
  const { values, setFieldValue, resetToDefaults, errors, rtmlibWarning, isDirty, isValid } =
    useSettingsForm(initialData, mode);

  const [activeTab, setActiveTab] = useState<TabType>('general');
  const [defaultRoot, setDefaultRoot] = useState<string>(systemInfo.output_root || '');
  const [destination, setDestination] = useState<string>(job?.output_path || '');
  const [thumbnail, setThumbnail] = useState<string>(initialThumbPath);
  const [resetFailed, setResetFailed] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);

  React.useEffect(() => {
    setDefaultRoot(systemInfo.output_root || '');
  }, [systemInfo.output_root]);

  React.useEffect(() => {
    setDestination(job?.output_path || '');
    setThumbnail(initialThumbPath);
    setResetFailed(true);
  }, [job, initialThumbPath]);

  const hasIoPathChanges =
    mode === 'default'
      ? defaultRoot.trim() !== (systemInfo.output_root || '').trim()
      : destination.trim() !== (job?.output_path || '').trim() ||
        thumbnail.trim() !== initialThumbPath;

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
      // Restore hardcoded engine defaults
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
      // Reflect only analysis parameters from global defaults; preserve job input video & destination (Plan A)
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
      const trimmedThumb = thumbnail.trim();
      const savePayload: Partial<JobSettings> = { ...extractEngineParams(values) };
      if (trimmedThumb) {
        const sepIdx = Math.max(trimmedThumb.lastIndexOf('\\'), trimmedThumb.lastIndexOf('/'));
        savePayload.THUMBNAIL_ROOT = sepIdx >= 0 ? trimmedThumb.slice(0, sepIdx) : '';
        savePayload.THUMBNAIL_IMAGE_NAME = sepIdx >= 0 ? trimmedThumb.slice(sepIdx + 1) : trimmedThumb;
      } else {
        savePayload.THUMBNAIL_ROOT = '';
        savePayload.THUMBNAIL_IMAGE_NAME = '';
      }
      success = await onSaveJob(job.id, savePayload, resetFailed, destination);
    }
    setIsSaving(false);
    if (success) {
      onBack();
    }
  };

  // Title text
  const titleText =
    mode === 'default'
      ? '基本設定（全体の初期値）'
      : `個別設定 — ${job?.video_name || ''}`;

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-white select-none">
      {/* Header Bar */}
      <div className="h-14 px-5 border-b border-[#D4DFDC] flex items-center justify-between bg-[#F8FAFA] flex-shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={handleBack}
            className="flex items-center gap-1 px-3 py-1.5 text-xs font-bold rounded-lg border border-[#B2C4BE] text-[#1E293B] hover:bg-[#EBF0EE] bg-white transition-colors cursor-pointer"
          >
            <ChevronLeft className="w-4 h-4" />
            <span>戻る</span>
          </button>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-[#1E293B] truncate max-w-md">{titleText}</h2>
            { (isDirty || hasIoPathChanges) && (
              <span className="text-[11px] font-bold text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">
                ● 未保存の変更あり
              </span>
            )}
          </div>
        </div>

        {/* Action Button Group */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleSecondaryAction}
            className="flex items-center gap-1 px-3 py-1.5 text-xs font-bold rounded-lg border border-[#B2C4BE] text-[#475569] hover:bg-[#EBF0EE] bg-white transition-colors cursor-pointer"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>{mode === 'default' ? '初期値に戻す' : '基本設定を反映'}</span>
          </button>

          <button
            onClick={handleSave}
            disabled={!canSave}
            className={`flex items-center gap-1.5 px-4 py-1.5 text-xs font-bold rounded-lg transition-all ${
              canSave
                ? 'bg-[#0F766E] hover:bg-[#115E59] text-white shadow-sm cursor-pointer'
                : 'bg-[#E2E8F0] text-[#94A3B8] cursor-not-allowed shadow-none'
            }`}
          >
            <Save className="w-3.5 h-3.5" />
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

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-5 flex flex-col">
        {/* Top I/O Card */}
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
              thumbnail={thumbnail}
              onChangeThumbnail={setThumbnail}
              resetFailed={resetFailed}
              onChangeResetFailed={setResetFailed}
            />
          )
        )}

        {/* 3-Tab Navigation */}
        <div className="flex border-b border-[#CBD5E1] mb-4 flex-shrink-0">
          <button
            onClick={() => setActiveTab('general')}
            className={`px-4 py-2 text-xs font-bold border-b-2 transition-colors cursor-pointer ${
              activeTab === 'general'
                ? 'border-[#0F766E] text-[#0F766E] bg-[#E4F3F0]/30'
                : 'border-transparent text-[#64748B] hover:text-[#1E293B]'
            }`}
          >
            基本・出力設定
            {rtmlibWarning && (
              <span className="ml-1.5 w-2 h-2 inline-block rounded-full bg-[#C8332B]" />
            )}
          </button>
          <button
            onClick={() => setActiveTab('tracking')}
            className={`px-4 py-2 text-xs font-bold border-b-2 transition-colors cursor-pointer ${
              activeTab === 'tracking'
                ? 'border-[#0F766E] text-[#0F766E] bg-[#E4F3F0]/30'
                : 'border-transparent text-[#64748B] hover:text-[#1E293B]'
            }`}
          >
            トラッキング・重み設定
          </button>
          <button
            onClick={() => setActiveTab('visualization')}
            className={`px-4 py-2 text-xs font-bold border-b-2 transition-colors cursor-pointer ${
              activeTab === 'visualization'
                ? 'border-[#0F766E] text-[#0F766E] bg-[#E4F3F0]/30'
                : 'border-transparent text-[#64748B] hover:text-[#1E293B]'
            }`}
          >
            可視化・オーバーレイ設定
          </button>
        </div>

        {/* Tab Body */}
        <div className="flex-1 pb-4">
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
