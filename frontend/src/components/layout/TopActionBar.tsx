import React from 'react';
import { Play, Square } from 'lucide-react';

export interface TopActionBarProps {
  isProcessing: boolean;
  isStopping: boolean;
  hasPendingJobs: boolean;
  bannerText: string;
  onStart: () => void;
  onCancel: () => void;
}

export const TopActionBar: React.FC<TopActionBarProps> = ({
  isProcessing,
  isStopping,
  hasPendingJobs,
  bannerText,
  onStart,
  onCancel,
}) => {
  const canStart = !isProcessing && hasPendingJobs;
  const canCancel = isProcessing && !isStopping;

  return (
    <header className="h-16 bg-white rounded-xl border border-[#D4DFDC] px-5 flex items-center justify-between shadow-sm mb-2.5 flex-shrink-0 select-none">
      {/* Start / Cancel Button Group */}
      <div className="flex items-center gap-3">
        <button
          onClick={onStart}
          disabled={!canStart}
          className={`flex items-center justify-center gap-2 px-6 h-10 rounded-lg font-bold text-sm shadow-sm transition-all ${
            canStart
              ? 'bg-[#0F766E] hover:bg-[#115E59] active:bg-[#0B534D] text-white cursor-pointer'
              : 'bg-[#E2E8F0] text-[#94A3B8] cursor-not-allowed shadow-none'
          }`}
        >
          <Play className="w-4 h-4 fill-current" />
          <span>▶  解析開始</span>
        </button>

        <button
          onClick={onCancel}
          disabled={!canCancel}
          className={`flex items-center justify-center gap-2 px-5 h-10 rounded-lg font-bold text-sm transition-all ${
            canCancel
              ? 'bg-white border border-[#F5C2C0] text-[#C8332B] hover:bg-[#FEF2F2] active:bg-[#FEE2E2] cursor-pointer shadow-sm'
              : isStopping
              ? 'bg-[#C8332B] text-white cursor-wait animate-pulse'
              : 'bg-[#E2E8F0] border-transparent text-[#94A3B8] cursor-not-allowed shadow-none'
          }`}
        >
          <Square className="w-4 h-4 fill-current" />
          <span>{isStopping ? '中断中...' : '■  解析中断'}</span>
        </button>
      </div>

      {/* Real-time Status Banner */}
      <div className="text-sm font-medium text-[#475569] truncate max-w-xl text-right">
        {bannerText}
      </div>
    </header>
  );
};
