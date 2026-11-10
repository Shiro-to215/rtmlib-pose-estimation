import React, { useState } from 'react';
import { ChevronLeft, RotateCcw, Save, Search, X } from 'lucide-react';
import { JobSettings, ReservationJob } from '../../types/models';
import { useSettingsForm } from './hooks/useSettingsForm';
import { DefaultIoCard } from './cards/DefaultIoCard';
import { JobIoCard } from './cards/JobIoCard';
import { GeneralOutputTab } from './cards/GeneralOutputTab';
import { DetectionConfidenceTab } from './cards/DetectionConfidenceTab';
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

type TabType = 'general' | 'detection' | 'tracking' | 'visualization';

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
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [defaultRoot, setDefaultRoot] = useState<string>(systemInfo.output_root || '');
  const [destination, setDestination] = useState<string>(job?.output_path || '');
  const [thumbnail, setThumbnail] = useState<string>(job?.thumbnail || '');
  const [resetFailed, setResetFailed] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);

  const handleBack = () => {
    if (isDirty) {
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
        MODEL_MODE: 'performance',
        YOLO_MODEL: 'yolo11m.pt',
        BACKEND: 'onnxruntime',
        CSV_MAX_PERSONS: 3,
        YOLO_IMAGE_SIZE: 1280,
        YOLO_CONFIDENCE: 0.2,
        YOLO_IOU: 0.5,
        CROP_PADDING_RATIO: 0.25,
        KEYPOINT_THRESHOLD: 0.45,
        RTMLIB_POSE_MODEL: 'mode',
        RTMLIB_POSE_INPUT_SIZE: 'mode',
        RTMLIB_PERSON_DETECTOR: 'mode',
        RTMLIB_DETECTOR_SCORE_THRESHOLD: 0.7,
        RTMLIB_DETECTOR_NMS_THRESHOLD: 0.45,
        YOLO_TRACKER: 'bytetrack.yaml',
        TARGET_LOCK_RAW_ID: true,
        TARGET_REQUIRE_SAME_RAW_ID_WHEN_MISSING: true,
        TARGET_SELECTION_MIN_FRAMES: 15,
        TARGET_SELECTION_COVERAGE_WEIGHT: 0.5,
        TARGET_BOX_FILL_MAX_FRAMES: 60,
        TARGET_REACQUIRE_MAX_DISTANCE: 300.0,
        TARGET_REACQUIRE_MIN_IOU: 0.05,
        TARGET_TRACK_MATCH_THRESHOLD: 0.75,
        TARGET_TRACK_MIN_IOU: 0.15,
        TRACK_MAX_DISTANCE: 250.0,
        TRACK_MAX_MISSED_FRAMES: 8,
        TRACK_MATCH_THRESHOLD: 2.0,
        TRACK_CENTER_WEIGHT: 0.35,
        TRACK_KEYPOINT_WEIGHT: 0.35,
        TRACK_POSE_WEIGHT: 0.2,
        TRACK_BBOX_WEIGHT: 0.1,
        TRACK_VELOCITY_SMOOTHING: 0.35,
        TRACK_RAW_ID_BONUS: 2.0,
        TRACK_PREDICTED_BOX_WEIGHT: 0.35,
        TRACK_PREDICTION_MAX_FRAMES: 2,
        POSE_TRACK_KEYPOINT_WEIGHT: 0.65,
        POSE_TRACK_CENTER_WEIGHT: 0.25,
        POSE_TRACK_SHAPE_WEIGHT: 0.1,
        POSE_BOX_IOU_WEIGHT: 2.0,
        POSE_BOX_CENTER_WEIGHT: 0.5,
        POSE_TEMPORAL_WEIGHT: 0.5,
        DRAW_SKELETON: true,
        DRAW_BBOX: true,
        SKELETON_LINE_WIDTH: 2,
        KEYPOINT_RADIUS: 4,
        LABEL_FONT_SCALE: 0.7,
      });
    } else {
      // Reflect default settings into this job
      resetToDefaults(defaultSettings);
    }
  };

  const handleSave = async () => {
    if (!isValid || isSaving) return;
    setIsSaving(true);
    let success = false;
    if (mode === 'default') {
      success = await onSaveDefault(values, defaultRoot);
    } else if (job) {
      success = await onSaveJob(job.id, values, resetFailed, destination);
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
            <span>← 戻る</span>
          </button>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-[#1E293B] truncate max-w-md">{titleText}</h2>
            {isDirty && (
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
            disabled={!isValid || !isDirty || isSaving}
            className={`flex items-center gap-1.5 px-4 py-1.5 text-xs font-bold rounded-lg transition-all ${
              isValid && isDirty && !isSaving
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

        {/* Search & Filter Bar */}
        <div className="relative mb-4 flex-shrink-0">
          <Search className="w-4 h-4 text-[#94A3B8] absolute left-3 top-2.5" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="設定項目をキーワードで検索（例: YOLO, 信頼度, 重み, 解像度, デバイス…）"
            className="w-full h-9 pl-9 pr-8 text-xs border border-[#CBD5E1] rounded-lg bg-white text-[#1E293B] focus:border-[#0F766E] focus:outline-none"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-2.5 text-[#94A3B8] hover:text-[#1E293B]"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* If searching: Show filtered search results; Else: show 4 tabs */}
        {searchQuery.trim() ? (
          <div className="space-y-4">
            <div className="text-xs font-bold text-[#475569] pb-2 border-b border-[#E2E8F0]">
              検索結果: 「{searchQuery}」
            </div>
            {/* Filtered view includes all matching widgets */}
            <div className="space-y-4">
              <GeneralOutputTab
                values={values}
                setFieldValue={setFieldValue}
                choices={systemInfo.choices}
                errors={errors}
              />
              <DetectionConfidenceTab
                values={values}
                setFieldValue={setFieldValue}
                choices={systemInfo.choices}
                errors={errors}
                rtmlibWarning={rtmlibWarning}
              />
              <TrackingWeightsTab
                values={values}
                setFieldValue={setFieldValue}
                choices={systemInfo.choices}
              />
              <VisualizationTab values={values} setFieldValue={setFieldValue} />
            </div>
          </div>
        ) : (
          <>
            {/* 4-Tab Navigation */}
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
              </button>
              <button
                onClick={() => setActiveTab('detection')}
                className={`px-4 py-2 text-xs font-bold border-b-2 transition-colors cursor-pointer ${
                  activeTab === 'detection'
                    ? 'border-[#0F766E] text-[#0F766E] bg-[#E4F3F0]/30'
                    : 'border-transparent text-[#64748B] hover:text-[#1E293B]'
                }`}
              >
                検出・信頼度設定
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
                />
              )}
              {activeTab === 'detection' && (
                <DetectionConfidenceTab
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
          </>
        )}
      </div>
    </div>
  );
};
