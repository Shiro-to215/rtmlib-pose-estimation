import React from 'react';
import { Settings } from 'lucide-react';
import { JobSettings, PoseEngineType, ReservationJob } from '../../types/models';
import { StatusBadge, StatusBadgeState } from '../left_monitor/StatusBadge';

export interface StatusSummaryStripProps {
  pendingCount: number;
  doneCount: number;
  failedCount: number;
  isProcessing: boolean;
  isStopping: boolean;
  progressPercent: number;
  phaseCode: string;
  activeJob: ReservationJob | null;
  inspectedJob: ReservationJob | null;
  defaultSettings: Partial<JobSettings>;
  onTogglePoseEngine: (nextEngine: PoseEngineType) => void;
  onOpenJobSettings: (jobId: string) => void;
}

function getPhaseDisplay(
  isStopping: boolean,
  isProcessing: boolean,
  phaseCode: string
): { badgeState: StatusBadgeState; detail: string } {
  if (isStopping) {
    return { badgeState: 'stopping', detail: '待機リストへ戻しています' };
  }
  if (!isProcessing) {
    return { badgeState: 'idle', detail: '待機中' };
  }
  const upper = (phaseCode || '').trim().toUpperCase();
  if (upper === 'YOLO') {
    return { badgeState: 'yolo', detail: '人物検出・追跡 (1/2)' };
  }
  if (upper.includes('VITPOSE')) {
    return { badgeState: 'vitpose', detail: '骨格推定 (2/2)' };
  }
  if (upper.includes('RTM') || upper === 'POSE' || upper.includes('RTMLIB')) {
    return { badgeState: 'rtmpose', detail: '骨格推定 (2/2)' };
  }
  if (upper === 'DONE') {
    return { badgeState: 'running', detail: '出力を保存しました' };
  }
  return { badgeState: 'running', detail: '推論ワーカーを初期化中' };
}

function formatYoloShort(model?: string): string {
  const raw = String(model || 'yolo11m.pt');
  const suffix = raw.replace(/^yolo11|\.pt$/g, '');
  return `YOLO11-${suffix}`;
}

export const StatusSummaryStrip: React.FC<StatusSummaryStripProps> = ({
  pendingCount,
  doneCount,
  failedCount,
  isProcessing,
  isStopping,
  progressPercent,
  phaseCode,
  activeJob,
  inspectedJob,
  defaultSettings,
  onTogglePoseEngine,
  onOpenJobSettings,
}) => {
  const safeProgress = isNaN(progressPercent)
    ? 0
    : Math.max(0, Math.min(100, Math.round(progressPercent)));
  const yoloPct = Math.min(100, Math.max(0, Math.round(safeProgress * 2)));
  const posePct = Math.min(100, Math.max(0, Math.round((safeProgress - 50) * 2)));

  const { badgeState, detail } = getPhaseDisplay(isStopping, isProcessing, phaseCode);

  const defaultEngine: PoseEngineType =
    String(defaultSettings.POSE_ENGINE || 'rtmpose').toLowerCase() === 'vitpose'
      ? 'vitpose'
      : 'rtmpose';

  const defaultPoseModelLabel =
    defaultEngine === 'vitpose'
      ? `ViTPose++-${String(defaultSettings.VITPOSE_MODEL || 'h').toUpperCase()}`
      : `RTMPose-${String(defaultSettings.RTMLIB_POSE_MODEL || 'x').toUpperCase()}`;

  const defaultPoseInputSize =
    defaultEngine === 'vitpose'
      ? String(defaultSettings.VITPOSE_INPUT_SIZE || '256x192')
      : String(defaultSettings.RTMLIB_POSE_INPUT_SIZE || '384x288');

  // Inspected job specs (only shown when NOT processing/stopping)
  const inspectedEngine: PoseEngineType =
    (inspectedJob?.summary?.pose_engine || inspectedJob?.settings?.POSE_ENGINE || 'rtmpose') ===
    'vitpose'
      ? 'vitpose'
      : 'rtmpose';

  const inspectedPoseLabel = inspectedJob
    ? inspectedEngine === 'vitpose'
      ? `ViTPose++-${String(
          inspectedJob.summary.vitpose_model || inspectedJob.settings?.VITPOSE_MODEL || 'h'
        ).toUpperCase()}`
      : `RTMPose-${String(inspectedJob.summary.pose_model || 'x').toUpperCase()}`
    : '';

  const inspectedPoseInputSize = inspectedJob
    ? inspectedEngine === 'vitpose'
      ? String(inspectedJob.summary.vitpose_input_size || '256x192')
      : String(inspectedJob.summary.pose_input_size || '384x288')
    : '';

  return (
    <div className="grid grid-cols-12 gap-3 flex-shrink-0">
      {/* Left 4 cols: Pending Queue Count KPI (no decorative barcode bars) */}
      <div className="col-span-4 bg-white rounded-[14px] p-4 flex flex-col justify-between min-w-0">
        <div>
          <div className="text-xs font-medium text-[#71717A]">待機予約</div>
          <div className="mt-2 flex items-baseline">
            <span className="text-[38px] leading-none font-bold tracking-[-0.035em] text-[#111111] tabular-nums">
              {pendingCount}
            </span>
            <span className="text-xs font-medium text-[#71717A] ml-1.5">件</span>
          </div>
        </div>

        <div className="pt-2.5 mt-3 border-t border-black/[0.06] flex items-center gap-3 text-[11px] tabular-nums">
          <span className="text-[#71717A]">完了 {doneCount}件</span>
          <span className={failedCount > 0 ? 'text-[#B91C1C] font-medium' : 'text-[#A1A1AA]'}>
            失敗 {failedCount}件
          </span>
        </div>
      </div>

      {/* Right 8 cols: Adaptive Progress (Priority 1) / Selected Inspector (Priority 2) / Default Spec (Priority 3) */}
      <div className="col-span-8 bg-white rounded-[14px] p-4 flex flex-col justify-between min-w-0">
        {isProcessing || isStopping ? (
          <>
            <div className="flex items-start justify-between gap-3 min-h-[34px]">
              <div className="min-w-0">
                <div
                  className="text-[13px] font-semibold text-[#111111] truncate"
                  title={activeJob?.video_name}
                >
                  {activeJob?.video_name || '解析準備中'}
                </div>
                <div className="text-[11px] text-[#71717A] mt-0.5 truncate">{detail}</div>
              </div>

              <div className="flex items-center gap-2.5 flex-shrink-0">
                <StatusBadge state={badgeState} />
                <span className="text-[30px] leading-none font-bold tracking-[-0.03em] text-[#111111] tabular-nums">
                  {safeProgress}%
                </span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 pt-2.5 mt-3 border-t border-black/[0.06]">
              <div>
                <div className="flex items-center justify-between text-[11px] mb-1.5">
                  <span className="text-[#71717A] font-medium">YOLO 検出</span>
                  <span className="font-mono text-[#111111] tabular-nums">{yoloPct}%</span>
                </div>
                <div className="h-1.5 w-full rounded-[6px] bg-[#F4F5F6] overflow-hidden">
                  <div
                    className={`h-full rounded-[6px] transition-all duration-200 ${
                      isStopping ? 'bg-[#B91C1C]' : 'bg-[#111111]'
                    }`}
                    style={{ width: `${yoloPct}%` }}
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between text-[11px] mb-1.5">
                  <span className="text-[#71717A] font-medium">骨格推定</span>
                  <span className="font-mono text-[#111111] tabular-nums">{posePct}%</span>
                </div>
                <div className="h-1.5 w-full rounded-[6px] bg-[#F4F5F6] overflow-hidden">
                  <div
                    className={`h-full rounded-[6px] transition-all duration-200 ${
                      isStopping ? 'bg-[#B91C1C]' : 'bg-[#111111]'
                    }`}
                    style={{ width: `${posePct}%` }}
                  />
                </div>
              </div>
            </div>
          </>
        ) : inspectedJob ? (
          <>
            <div className="flex items-center justify-between gap-3 min-h-[34px]">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-xs font-medium text-[#71717A] flex-shrink-0">
                  選択中の予約
                </span>
                <span
                  className="text-[13px] font-semibold text-[#111111] truncate"
                  title={inspectedJob.video_name}
                >
                  {inspectedJob.video_name}
                </span>
              </div>
              <button
                type="button"
                onClick={() => onOpenJobSettings(inspectedJob.id)}
                className="h-6 px-2.5 rounded-[6px] bg-[#F4F5F6] hover:bg-[#E3E5E8] text-[#111111] text-[11px] font-medium inline-flex items-center gap-1 flex-shrink-0 transition-colors cursor-pointer"
              >
                <Settings className="w-3 h-3 text-[#71717A]" strokeWidth={1.6} />
                <span>個別設定</span>
              </button>
            </div>

            <div className="grid grid-cols-3 divide-x divide-black/[0.06] pt-2.5 mt-3 border-t border-black/[0.06]">
              <div className="pr-3 min-w-0">
                <div className="text-[11px] text-[#71717A]">姿勢推定</div>
                <div className="text-[13px] font-semibold text-[#111111] truncate mt-0.5">
                  {inspectedPoseLabel}
                </div>
                <div className="text-[11px] font-mono text-[#71717A] tabular-nums truncate">
                  {inspectedPoseInputSize}
                </div>
              </div>
              <div className="px-3 min-w-0">
                <div className="text-[11px] text-[#71717A]">人物検出</div>
                <div className="text-[13px] font-semibold text-[#111111] truncate mt-0.5">
                  {formatYoloShort(inspectedJob.summary.yolo_model)}
                </div>
                <div className="text-[11px] font-mono text-[#71717A] truncate">
                  デバイス: {inspectedJob.summary.device || 'auto'}
                </div>
              </div>
              <div className="pl-3 min-w-0">
                <div className="text-[11px] text-[#71717A]">フレーム処理</div>
                <div className="text-[13px] font-semibold text-[#111111] tabular-nums truncate mt-0.5">
                  {inspectedJob.summary.capture_fps ? `${inspectedJob.summary.capture_fps} fps` : '元FPS'}
                </div>
                <div
                  className="text-[11px] font-mono text-[#71717A] truncate"
                  title={inspectedJob.output_folder}
                >
                  出力: {inspectedJob.output_folder}
                </div>
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="flex items-center justify-between gap-3 min-h-[34px]">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-xs font-medium text-[#71717A]">既定の推論構成</span>
                <StatusBadge state="idle" />
              </div>

              <div
                className="bg-[#F4F5F6] p-[2px] rounded-[6px] flex items-center flex-shrink-0"
                title="新規予約に適用する姿勢推定エンジン"
              >
                <button
                  type="button"
                  onClick={() => {
                    if (defaultEngine !== 'rtmpose') onTogglePoseEngine('rtmpose');
                  }}
                  className={`px-2.5 h-6 rounded-[4px] text-[11px] font-medium transition-colors cursor-pointer ${
                    defaultEngine === 'rtmpose'
                      ? 'bg-white text-[#111111]'
                      : 'text-[#71717A] hover:text-[#111111]'
                  }`}
                >
                  RTMPose
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (defaultEngine !== 'vitpose') onTogglePoseEngine('vitpose');
                  }}
                  className={`px-2.5 h-6 rounded-[4px] text-[11px] font-medium transition-colors cursor-pointer ${
                    defaultEngine === 'vitpose'
                      ? 'bg-white text-[#111111]'
                      : 'text-[#71717A] hover:text-[#111111]'
                  }`}
                >
                  ViTPose++
                </button>
              </div>
            </div>

            <div className="grid grid-cols-3 divide-x divide-black/[0.06] pt-2.5 mt-3 border-t border-black/[0.06]">
              <div className="pr-3 min-w-0">
                <div className="text-[11px] text-[#71717A]">姿勢推定</div>
                <div className="text-[13px] font-semibold text-[#111111] truncate mt-0.5">
                  {defaultPoseModelLabel}
                </div>
                <div className="text-[11px] font-mono text-[#71717A] tabular-nums truncate">
                  {defaultPoseInputSize}
                </div>
              </div>
              <div className="px-3 min-w-0">
                <div className="text-[11px] text-[#71717A]">人物検出</div>
                <div className="text-[13px] font-semibold text-[#111111] truncate mt-0.5">
                  {formatYoloShort(defaultSettings.YOLO_MODEL)}
                </div>
                <div className="text-[11px] font-mono text-[#71717A] truncate">
                  デバイス: {defaultSettings.DEVICE || 'auto'}
                </div>
              </div>
              <div className="pl-3 min-w-0">
                <div className="text-[11px] text-[#71717A]">フレーム処理</div>
                <div className="text-[13px] font-semibold text-[#111111] tabular-nums truncate mt-0.5">
                  {defaultSettings.CAPTURE_FPS ? `${defaultSettings.CAPTURE_FPS} fps` : '元FPS'}
                </div>
                <div className="text-[11px] text-[#A1A1AA] truncate">新規予約の既定値</div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
