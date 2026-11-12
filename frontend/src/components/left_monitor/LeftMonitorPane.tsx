import React from 'react';
import { StatusBadge, StatusBadgeState } from './StatusBadge';
import { VideoPreviewCanvas } from './VideoPreviewCanvas';
import { CircularProgressRing, ProgressTone } from './CircularProgressRing';
import { ExecutionLogBox } from './ExecutionLogBox';
import { LogEntry, ReservationJob } from '../../types/models';

export interface LeftMonitorPaneProps {
  activeJob: ReservationJob | null;
  progressPercent: number;
  phaseCode: string;
  isProcessing: boolean;
  isStopping: boolean;
  logs: LogEntry[];
  onClearLogs: () => void;
}

export const LeftMonitorPane: React.FC<LeftMonitorPaneProps> = ({
  activeJob,
  progressPercent,
  phaseCode,
  isProcessing,
  isStopping,
  logs,
  onClearLogs,
}) => {
  // Compute badge state & progress tone
  let badgeState: StatusBadgeState = 'idle';
  let progressTone: ProgressTone = 'idle';
  let phaseTitle = '待機中';
  let subtitle = '予約を開始すると進捗を表示';

  if (isStopping) {
    badgeState = 'stopping';
    progressTone = 'stopping';
    phaseTitle = '中断処理中';
    subtitle = '待機リストへ戻します';
  } else if (isProcessing && activeJob) {
    const upperPhase = (phaseCode || '').trim().toUpperCase();
    if (upperPhase === 'YOLO') {
      badgeState = 'yolo';
      progressTone = 'yolo';
      phaseTitle = 'YOLO';
      subtitle = '人物検出・追跡 (1/2)';
    } else if (upperPhase.includes('VITPOSE')) {
      badgeState = 'vitpose';
      progressTone = 'rtmpose';
      phaseTitle = 'ViTPose++';
      subtitle = '骨格推定 (2/2)';
    } else if (upperPhase.includes('RTM') || upperPhase === 'POSE' || upperPhase.includes('RTMLIB')) {
      badgeState = 'rtmpose';
      progressTone = 'rtmpose';
      phaseTitle = 'RTMPose';
      subtitle = '骨格推定 (2/2)';
    } else if (upperPhase === 'DONE') {
      badgeState = 'running';
      progressTone = 'done';
      phaseTitle = '完了';
      subtitle = '解析完了';
    } else {
      badgeState = 'running';
      progressTone = 'yolo';
      phaseTitle = '起動中...';
      subtitle = 'モデル初期化';
    }
  }

  const isIdle = !isProcessing || !activeJob;

  return (
    <aside className="w-full h-full bg-white rounded-xl border border-[#D4DFDC] p-3.5 flex flex-col justify-between shadow-sm overflow-hidden select-none">
      {/* Top Header: "解析中" + Status Badge */}
      <div className="flex items-center justify-between pb-2 border-b border-[#EBF0EE] flex-shrink-0">
        <h1 className="text-base font-bold text-[#1E293B]">解析中</h1>
        <StatusBadge state={badgeState} />
      </div>

      {/* 16:9 Video Preview Canvas & Info */}
      <div className="py-1.5 flex-shrink-0">
        <VideoPreviewCanvas
          imageSrc={activeJob?.thumbnail}
          videoTitle={activeJob?.video_name}
          metaText={activeJob ? `出力: ${activeJob.output_folder}` : '右側の予約リストから解析を開始できます'}
          resolutionInfo={activeJob?.thumbnail_info}
          isIdle={isIdle}
        />
      </div>

      {/* 184px Circular Progress Ring */}
      <div className="py-1 flex items-center justify-center flex-shrink-0">
        <CircularProgressRing
          percent={progressPercent}
          phaseTitle={phaseTitle}
          subtitle={subtitle}
          tone={progressTone}
        />
      </div>

      {/* Compact Execution Log Box */}
      <div className="pt-1 flex-1 min-h-0 flex flex-col justify-end">
        <ExecutionLogBox logs={logs} onClear={onClearLogs} />
      </div>
    </aside>
  );
};
