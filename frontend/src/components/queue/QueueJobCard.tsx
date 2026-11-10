import React from 'react';
import { Film, Settings } from 'lucide-react';
import { ReservationJob } from '../../types/models';

export interface QueueJobCardProps {
  job: ReservationJob;
  orderNum: number;
  isSelected: boolean;
  onSelect: (e: React.MouseEvent, jobId: string) => void;
  onOpenJobSettings: (jobId: string) => void;
  onRetry: (jobId: string) => void;
  onDragStart: (e: React.DragEvent, jobId: string, index: number) => void;
  onDragOver: (e: React.DragEvent, index: number) => void;
  onDrop: (e: React.DragEvent, index: number) => void;
  index: number;
}

export const QueueJobCard: React.FC<QueueJobCardProps> = ({
  job,
  orderNum,
  isSelected,
  onSelect,
  onOpenJobSettings,
  onRetry,
  onDragStart,
  onDragOver,
  onDrop,
  index,
}) => {
  const isFailed = job.state === 'failed';

  let cardBorderClass = 'border border-[#D4DFDC] bg-white hover:bg-[#F4F9F8]';
  if (isSelected) {
    cardBorderClass = 'border-2 border-[#0F766E] bg-[#E2F2EE] shadow-sm';
  } else if (isFailed) {
    cardBorderClass = 'border border-[#F5C2C0] bg-[#FEF2F2] hover:bg-[#FDF0F0]';
  }

  const yoloShort = (job.summary.yolo_model || 'yolo11m.pt').replace(/^yolo11|\.pt$/g, '');

  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, job.id, index)}
      onDragOver={(e) => onDragOver(e, index)}
      onDrop={(e) => onDrop(e, index)}
      onClick={(e) => onSelect(e, job.id)}
      className={`rounded-lg p-2.5 transition-all grid grid-cols-[216px_108px_1fr] items-center gap-2 cursor-pointer select-none mb-2 ${cardBorderClass}`}
    >
      {/* Column 0: Order Number + 160x90 Thumbnail */}
      <div className="flex items-center gap-2 pl-1">
        <span
          className={`w-7 text-center font-bold text-sm ${
            isFailed ? 'text-[#C8332B]' : 'text-[#475569]'
          }`}
        >
          {orderNum}
        </span>
        <div className="w-40 h-[90px] rounded-md overflow-hidden bg-[#E2E8E6] border border-[#B2C4BE] flex items-center justify-center relative flex-shrink-0">
          {job.thumbnail ? (
            <img
              src={job.thumbnail}
              alt={job.video_name}
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="flex flex-col items-center justify-center text-[#64748B]">
              <Film className="w-6 h-6 mb-1 opacity-60" />
              <span className="text-[10px]">プレビュー</span>
            </div>
          )}
          {job.thumbnail_info && (
            <span className="absolute bottom-1 right-1 bg-black/60 text-white text-[9px] px-1 rounded font-mono">
              {job.thumbnail_info}
            </span>
          )}
        </div>
      </div>

      {/* Column 1: Per-job [設定] Button */}
      <div className="flex justify-center">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onOpenJobSettings(job.id);
          }}
          className="px-4 py-2 text-xs font-bold rounded-lg border border-[#B2C4BE] text-[#1E293B] hover:bg-[#EBF0EE] bg-white transition-colors shadow-xs flex items-center gap-1 cursor-pointer"
        >
          <Settings className="w-3.5 h-3.5 text-[#475569]" />
          <span>設定</span>
        </button>
      </div>

      {/* Column 2: Video Filename, Specs, Destination & Error Bar */}
      <div className="flex flex-col justify-center min-w-0 pr-3">
        {/* Line 1: Name and Spec tag */}
        <div className="flex items-center justify-between gap-2">
          <span className="font-bold text-sm text-[#1E293B] truncate" title={job.video_name}>
            {job.video_name}
          </span>
          <span className="text-[11px] text-[#64748B] whitespace-nowrap bg-slate-100/80 px-2 py-0.5 rounded">
            {job.summary.model_mode} / YOLO-{yoloShort} / {job.summary.device}
          </span>
        </div>

        {/* Line 2: Output Destination */}
        <div className="mt-1 text-xs text-[#475569] truncate" title={job.output_path}>
          出力先: {job.output_path}
        </div>

        {/* Line 3: Failed Error & Retry (if failed) */}
        {isFailed && (
          <div className="mt-1.5 flex items-center justify-between bg-white/80 border border-[#F5C2C0] rounded px-2.5 py-1">
            <span className="text-[11px] font-bold text-[#C8332B] truncate mr-2" title={job.error}>
              失敗: {job.error || '解析エラーが発生しました'}
            </span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onRetry(job.id);
              }}
              className="px-2.5 py-1 text-[11px] font-bold rounded bg-[#C8332B] hover:bg-[#A62620] text-white transition-colors flex-shrink-0 cursor-pointer"
            >
              再試行
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
