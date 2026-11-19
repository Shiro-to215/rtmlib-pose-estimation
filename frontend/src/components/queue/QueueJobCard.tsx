import React from 'react';
import { Film, GripVertical, RotateCcw, Settings } from 'lucide-react';
import { ReservationJob } from '../../types/models';

export interface QueueJobCardProps {
  job: ReservationJob;
  orderNum: number;
  isSelected: boolean;
  canReorder: boolean;
  onSelect: (e: React.MouseEvent, jobId: string) => void;
  onOpenJobSettings: (jobId: string) => void;
  onRetry: (jobId: string) => void;
  onDragStart: (e: React.DragEvent, jobId: string, index: number) => void;
  onDragOver: (e: React.DragEvent, index: number) => void;
  onDrop: (e: React.DragEvent, index: number) => void;
  onDragEnd?: () => void;
  index: number;
}

export const QueueJobCard: React.FC<QueueJobCardProps> = ({
  job,
  orderNum,
  isSelected,
  canReorder,
  onSelect,
  onOpenJobSettings,
  onRetry,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
  index,
}) => {
  const isFailed = job.state === 'failed';
  const isLocalRendering = Boolean(job.local_rendering);
  const draggable = canReorder && !isLocalRendering;

  let rowStyle = 'bg-white hover:bg-[#F4F5F6]';
  if (isSelected) {
    rowStyle = 'bg-[#F4F5F6] ring-1 ring-inset ring-[#111111]';
  } else if (isFailed) {
    rowStyle = 'bg-[#FEE2E2]/35 hover:bg-[#FEE2E2]/55';
  } else if (isLocalRendering) {
    rowStyle = 'bg-[#DCFCE7]/35';
  }

  const yoloShort = (job.summary.yolo_model || 'yolo11m.pt').replace(/^yolo11|\.pt$/g, '');
  const poseEngine = job.summary.pose_engine || job.settings?.POSE_ENGINE || 'rtmpose';
  const isVitpose = poseEngine === 'vitpose';
  const poseTitle = isVitpose
    ? `ViTPose++-${(job.summary.vitpose_model || job.settings?.VITPOSE_MODEL || 'h').toUpperCase()}`
    : `RTMPose-${String(job.summary.pose_model || 'x').toUpperCase()}`;
  const poseRes = isVitpose
    ? job.summary.vitpose_input_size || '256x192'
    : job.summary.pose_input_size || '384x288';

  return (
    <div
      draggable={draggable}
      onDragStart={(e) => {
        if (draggable) onDragStart(e, job.id, index);
      }}
      onDragOver={(e) => {
        if (canReorder) onDragOver(e, index);
      }}
      onDrop={(e) => {
        if (draggable) onDrop(e, index);
      }}
      onDragEnd={() => onDragEnd?.()}
      onClick={(e) => onSelect(e, job.id)}
      className={`grid grid-cols-[36px_76px_minmax(0,1fr)_140px_72px_64px] items-center gap-2.5 px-2.5 py-2 rounded-[6px] transition-colors select-none mb-1 ${
        isLocalRendering ? 'cursor-default' : 'cursor-pointer'
      } ${rowStyle}`}
    >
      {/* Column 0: Drag Handle + Order Number */}
      <div className="flex items-center gap-1 min-w-0">
        {draggable ? (
          <GripVertical className="w-3.5 h-3.5 text-[#A1A1AA] flex-shrink-0" strokeWidth={1.6} />
        ) : (
          <span className="w-3.5 flex-shrink-0" />
        )}
        <span
          className={`text-xs font-mono font-medium tabular-nums ${
            isSelected
              ? 'text-[#111111]'
              : isFailed
              ? 'text-[#B91C1C]'
              : 'text-[#71717A]'
          }`}
        >
          {orderNum}
        </span>
      </div>

      {/* Column 1: 16:9 Compact Thumbnail */}
      <div
        className="w-[76px] h-[43px] rounded-[6px] overflow-hidden bg-[#F4F5F6] border border-black/[0.06] flex items-center justify-center flex-shrink-0"
        title={job.thumbnail_info || job.video_name}
      >
        {job.thumbnail ? (
          <img
            src={job.thumbnail}
            alt={job.video_name}
            className="w-full h-full object-cover"
          />
        ) : (
          <Film className="w-4 h-4 text-[#A1A1AA]" strokeWidth={1.6} />
        )}
      </div>

      {/* Column 2: Video Name & Output Path / Error */}
      <div className="min-w-0">
        <div
          className="text-[13px] font-semibold text-[#111111] truncate"
          title={job.video_name}
        >
          {job.video_name}
        </div>
        {isFailed ? (
          <div
            className="text-[11px] text-[#B91C1C] truncate mt-0.5"
            title={job.error}
          >
            失敗: {job.error || '解析エラーが発生しました'}
          </div>
        ) : isLocalRendering ? (
          <div className="text-[11px] text-[#15803D] truncate mt-0.5">
            MP4 動画をローカル書き出し中...
          </div>
        ) : (
          <div
            className="text-[11px] font-mono text-[#71717A] truncate mt-0.5"
            title={job.output_path}
          >
            {job.output_path}
          </div>
        )}
      </div>

      {/* Column 3: Inference Spec */}
      <div className="min-w-0">
        <div className="text-xs font-medium text-[#111111] truncate">{poseTitle}</div>
        <div className="text-[11px] font-mono text-[#71717A] tabular-nums truncate">
          {poseRes} / YOLO11-{yoloShort}
        </div>
      </div>

      {/* Column 4: Status Tag */}
      <div>
        {isLocalRendering ? (
          <span className="inline-flex items-center justify-center px-2 h-6 rounded-[6px] text-[11px] font-medium bg-[#DCFCE7] text-[#15803D] whitespace-nowrap">
            書出中
          </span>
        ) : isFailed ? (
          <span className="inline-flex items-center justify-center px-2 h-6 rounded-[6px] text-[11px] font-medium bg-[#FEE2E2] text-[#B91C1C] whitespace-nowrap">
            失敗
          </span>
        ) : (
          <span className="inline-flex items-center justify-center px-2 h-6 rounded-[6px] text-[11px] font-medium bg-[#F4F5F6] text-[#71717A] whitespace-nowrap">
            待機
          </span>
        )}
      </div>

      {/* Column 5: Actions */}
      <div className="flex items-center justify-end gap-1">
        {isFailed && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onRetry(job.id);
            }}
            className="w-7 h-7 rounded-[6px] bg-[#FEE2E2] text-[#B91C1C] hover:bg-[#FECACA] flex items-center justify-center transition-colors cursor-pointer"
            title="再試行"
            aria-label="再試行"
          >
            <RotateCcw className="w-3.5 h-3.5" strokeWidth={1.6} />
          </button>
        )}
        <button
          type="button"
          disabled={isLocalRendering}
          onClick={(e) => {
            e.stopPropagation();
            if (!isLocalRendering) onOpenJobSettings(job.id);
          }}
          className={`w-7 h-7 rounded-[6px] flex items-center justify-center transition-colors ${
            isLocalRendering
              ? 'opacity-40 cursor-not-allowed text-[#A1A1AA]'
              : 'text-[#71717A] hover:text-[#111111] hover:bg-[#E3E5E8] cursor-pointer'
          }`}
          title="個別設定"
          aria-label="個別設定"
        >
          <Settings className="w-3.5 h-3.5" strokeWidth={1.6} />
        </button>
      </div>
    </div>
  );
};
