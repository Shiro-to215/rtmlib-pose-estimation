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
  onStopColabCli?: () => void;
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
  onStopColabCli,
  onStart,
  onCancel,
}) => {
  const canStart = !isProcessing && hasPendingJobs;
  const canCancel = isProcessing && !isStopping;
  const isColab = executionTarget === 'colab';
  const colabMode = colabConfig?.colab_mode || 'cli_ssh';
  const isCliSsh = colabMode === 'cli_ssh';
  const cliStatus = colabConfig?.cli_status;
  const hasUrl = Boolean((colabConfig?.server_url || '').trim());
  const gpuLabel = colabConfig?.last_health?.gpu_name;

  const renderColabPillLabel = (): string => {
    if (!isCliSsh) {
      return gpuLabel ? gpuLabel : hasUrl ? 'Colab 設定済' : 'Colab 接続設定';
    }
    if (cliStatus?.state === 'running') {
      const remSec = cliStatus.idle_remaining_sec;
      const remText =
        !isProcessing && remSec != null && cliStatus.idle_timeout_minutes > 0
          ? ` · 残${Math.max(1, Math.ceil(remSec / 60))}分`
          : '';
      return `Colab SSH: 稼働中 (${cliStatus.gpu})${remText}`;
    }
    if (cliStatus?.state === 'starting') {
      return `Colab SSH: 起動中 (${cliStatus.gpu})...`;
    }
    if (cliStatus?.state === 'stopping') {
      return 'Colab SSH: 停止中...';
    }
    if (cliStatus?.state === 'error') {
      return 'Colab SSH: エラー';
    }
    return `Colab SSH: 待機 (${colabConfig?.cli_gpu || 'T4'})`;
  };

  const pillColorClass = (): string => {
    if (!isCliSsh) {
      if (isColab && !hasUrl) {
        return 'bg-[#FEF3C7] border-[#F59E0B] text-[#92400E] hover:bg-[#FDE68A]';
      }
      if (hasUrl && gpuLabel) {
        return 'bg-[#F0FDF4] border-[#BBF7D0] text-[#15803D] hover:bg-[#DCFCE7]';
      }
      return 'bg-white border-[#CBD5E1] text-[#475569] hover:bg-[#F8FAFC]';
    }
    if (cliStatus?.state === 'running') {
      return 'bg-[#F0FDF4] border-[#BBF7D0] text-[#15803D] hover:bg-[#DCFCE7]';
    }
    if (cliStatus?.state === 'error') {
      return 'bg-[#FEF2F2] border-[#FECACA] text-[#B91C1C] hover:bg-[#FEE2E2]';
    }
    if (cliStatus?.state === 'starting' || cliStatus?.state === 'stopping') {
      return 'bg-[#EFF6FF] border-[#BFDBFE] text-[#1D4ED8] hover:bg-[#DBEAFE]';
    }
    return 'bg-white border-[#CBD5E1] text-[#475569] hover:bg-[#F8FAFC]';
  };

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

        {/* Colab Connection Settings Pill + Quick Stop */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onOpenColabModal}
            className={`flex items-center gap-1.5 px-2.5 h-9 rounded-lg border text-xs font-bold transition-all cursor-pointer ${pillColorClass()}`}
            title={
              isCliSsh
                ? cliStatus?.status_message || 'Google Colab CLI / SSH 接続設定を開く'
                : 'Google Colab 接続 URL / トークン設定を開く'
            }
          >
            <Link2 className="w-3.5 h-3.5 flex-shrink-0" />
            <span className="max-w-[220px] truncate">{renderColabPillLabel()}</span>
          </button>

          {isCliSsh && cliStatus?.state === 'running' && !isProcessing && onStopColabCli && (
            <button
              type="button"
              onClick={onStopColabCli}
              className="flex items-center justify-center w-8 h-9 rounded-lg border border-[#F5C2C0] bg-white text-[#C8332B] hover:bg-[#FEF2F2] transition-colors cursor-pointer"
              title="Colab ランタイムを今すぐ停止 (colab stop)"
              aria-label="Colab ランタイム停止"
            >
              <Square className="w-3.5 h-3.5 fill-current" />
            </button>
          )}
        </div>
      </div>

      {/* Real-time Status Banner */}
      <div className="text-xs font-medium text-[#475569] truncate text-right min-w-0">
        {bannerText}
      </div>
    </header>
  );
};
