import React from 'react';
import { Cloud, Cpu, Link2, Play, Square } from 'lucide-react';
import { ColabConfig, ExecutionTarget } from '../../types/models';

export interface TopActionBarProps {
  isProcessing: boolean;
  isStopping: boolean;
  hasPendingJobs: boolean;
  bannerText: string;
  executionTarget: ExecutionTarget;
  colabConfig: ColabConfig;
  onChangeExecutionTarget: (target: ExecutionTarget) => void;
  onOpenColabModal: () => void;
  onStart: () => void;
  onCancel: () => void;
}

export const TopActionBar: React.FC<TopActionBarProps> = ({
  isProcessing,
  isStopping,
  hasPendingJobs,
  bannerText,
  executionTarget,
  colabConfig,
  onChangeExecutionTarget,
  onOpenColabModal,
  onStart,
  onCancel,
}) => {
  const canStart = !isProcessing && hasPendingJobs;
  const canCancel = isProcessing && !isStopping;
  const isColab = executionTarget === 'colab';
  const hasUrl = Boolean((colabConfig?.server_url || '').trim());
  const gpuLabel = colabConfig?.last_health?.gpu_name;

  return (
    <header className="h-16 bg-white rounded-xl border border-[#D4DFDC] px-4 flex items-center justify-between gap-3 shadow-sm mb-2.5 flex-shrink-0 select-none">
      {/* Start / Cancel & Execution Target Switch */}
      <div className="flex items-center gap-2.5 flex-shrink-0">
        <button
          onClick={onStart}
          disabled={!canStart}
          className={`flex items-center justify-center gap-2 px-5 h-10 rounded-lg font-bold text-sm shadow-sm transition-all ${
            canStart
              ? 'bg-[#0F766E] hover:bg-[#115E59] active:bg-[#0B534D] text-white cursor-pointer'
              : 'bg-[#E2E8F0] text-[#94A3B8] cursor-not-allowed shadow-none'
          }`}
        >
          <Play className="w-4 h-4 fill-current" />
          <span>解析開始</span>
        </button>

        <button
          onClick={onCancel}
          disabled={!canCancel}
          className={`flex items-center justify-center gap-2 px-4 h-10 rounded-lg font-bold text-sm transition-all ${
            canCancel
              ? 'bg-white border border-[#F5C2C0] text-[#C8332B] hover:bg-[#FEF2F2] active:bg-[#FEE2E2] cursor-pointer shadow-sm'
              : isStopping
              ? 'bg-[#C8332B] text-white cursor-wait animate-pulse'
              : 'bg-[#E2E8F0] border-transparent text-[#94A3B8] cursor-not-allowed shadow-none'
          }`}
        >
          <Square className="w-4 h-4 fill-current" />
          <span>{isStopping ? '中断中...' : '解析中断'}</span>
        </button>

        {/* Execution Target Segmented Toggle */}
        <div
          className="flex items-center bg-[#F1F5F9] rounded-lg p-0.5 border border-[#CBD5E1]"
          title={isProcessing ? '解析中は実行先を変更できません' : '解析の実行先を選択'}
        >
          <button
            type="button"
            disabled={isProcessing}
            onClick={() => onChangeExecutionTarget('local')}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-bold transition-all ${
              !isColab
                ? 'bg-white text-[#0F766E] shadow-xs'
                : 'text-[#64748B] hover:text-[#1E293B]'
            } ${isProcessing ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>ローカル</span>
          </button>
          <button
            type="button"
            disabled={isProcessing}
            onClick={() => onChangeExecutionTarget('colab')}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-bold transition-all ${
              isColab
                ? 'bg-white text-[#0F766E] shadow-xs'
                : 'text-[#64748B] hover:text-[#1E293B]'
            } ${isProcessing ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
          >
            <Cloud className="w-3.5 h-3.5" />
            <span>Colab GPU</span>
          </button>
        </div>

        {/* Colab Connection Settings Pill */}
        <button
          type="button"
          onClick={onOpenColabModal}
          className={`flex items-center gap-1.5 px-2.5 h-9 rounded-lg border text-xs font-bold transition-all cursor-pointer ${
            isColab && !hasUrl
              ? 'bg-[#FEF3C7] border-[#F59E0B] text-[#92400E] hover:bg-[#FDE68A]'
              : hasUrl && gpuLabel
              ? 'bg-[#F0FDF4] border-[#BBF7D0] text-[#15803D] hover:bg-[#DCFCE7]'
              : 'bg-white border-[#CBD5E1] text-[#475569] hover:bg-[#F8FAFC]'
          }`}
          title="Google Colab 接続 URL / トークン設定を開く"
        >
          <Link2 className="w-3.5 h-3.5 flex-shrink-0" />
          <span className="max-w-[140px] truncate">
            {gpuLabel ? gpuLabel : hasUrl ? 'Colab 設定済' : 'Colab 接続設定'}
          </span>
        </button>
      </div>

      {/* Real-time Status Banner */}
      <div className="text-xs font-medium text-[#475569] truncate text-right min-w-0">
        {bannerText}
      </div>
    </header>
  );
};
