import React from 'react';
import { Cloud, Cpu, Link2, Play, Square } from 'lucide-react';
import { ColabConfig, ExecutionTarget, RightViewType } from '../../types/models';

export interface TopHeaderProps {
  activeView: RightViewType;
  isProcessing: boolean;
  isStopping: boolean;
  hasPendingJobs: boolean;
  executionTarget: ExecutionTarget;
  colabConfig: ColabConfig;
  onNavigateQueue: () => void;
  onNavigateAdd: () => void;
  onNavigateBasicSettings: () => void;
  onChangeExecutionTarget: (target: ExecutionTarget) => void;
  onOpenColabModal: () => void;
  onStopColabCli?: () => void;
  onStart: () => void;
  onCancel: () => void;
}

export const TopHeader: React.FC<TopHeaderProps> = ({
  activeView,
  isProcessing,
  isStopping,
  hasPendingJobs,
  executionTarget,
  colabConfig,
  onNavigateQueue,
  onNavigateAdd,
  onNavigateBasicSettings,
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

  const navItems: Array<{
    id: string;
    label: string;
    active: boolean;
    onClick: () => void;
  }> = [
    {
      id: 'queue',
      label: 'ダッシュボード',
      active: activeView === 'queue',
      onClick: onNavigateQueue,
    },
    {
      id: 'add',
      label: '予約を追加',
      active: activeView === 'add',
      onClick: onNavigateAdd,
    },
    {
      id: 'basic_settings',
      label: '基本設定',
      active: activeView === 'basic_settings' || activeView === 'job_settings',
      onClick: onNavigateBasicSettings,
    },
  ];

  const getColabLabel = (): string => {
    if (!isCliSsh) {
      return gpuLabel ? gpuLabel : hasUrl ? 'Colab設定済' : 'Colab設定';
    }
    if (cliStatus?.state === 'running') {
      const remSec = cliStatus.idle_remaining_sec;
      const remText =
        !isProcessing && remSec != null && cliStatus.idle_timeout_minutes > 0
          ? ` (${Math.max(1, Math.ceil(remSec / 60))}m)`
          : '';
      return `${cliStatus.gpu}${remText}`;
    }
    if (cliStatus?.state === 'starting') return '起動中...';
    if (cliStatus?.state === 'stopping') return '停止中...';
    if (cliStatus?.state === 'error') return '接続エラー';
    return 'Colab設定';
  };

  const colabStateDot = (): string | null => {
    if (isCliSsh) {
      if (cliStatus?.state === 'running') return 'bg-[#15803D]';
      if (cliStatus?.state === 'error') return 'bg-[#B91C1C]';
      return null;
    }
    if (hasUrl && gpuLabel) return 'bg-[#15803D]';
    return null;
  };

  const dotClass = colabStateDot();

  const handlePrimaryAction = () => {
    if (isProcessing) {
      if (canCancel) onCancel();
    } else if (canStart) {
      onStart();
    }
  };

  return (
    <header className="h-11 flex-shrink-0 flex items-center justify-between gap-4 select-none">
      {/* Left: Crisp Monochrome Geometric Mark + Product Name */}
      <div className="flex items-center gap-2.5 min-w-0 flex-shrink-0">
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
          className="flex-shrink-0"
        >
          <rect x="1.5" y="1.5" width="17" height="17" rx="4" fill="#111111" />
          <circle cx="10" cy="6.5" r="1.6" fill="#FFFFFF" />
          <path
            d="M6.2 13.8L8.4 9.8H11.6L13.8 13.8"
            stroke="#FFFFFF"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span className="text-[15px] font-semibold tracking-[-0.02em] text-[#111111]">
          PoseStudio
        </span>
      </div>

      {/* Center: Pill Navigation Tabs (ONLY 9999px pills in the UI) */}
      <nav aria-label="メインナビゲーション" className="flex items-center gap-1.5">
        {navItems.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={item.onClick}
            className={`h-8 px-4 rounded-full text-xs font-medium transition-colors cursor-pointer whitespace-nowrap ${
              item.active
                ? 'bg-[#111111] text-white'
                : 'bg-[#E3E5E8] text-[#52525B] hover:text-[#111111] hover:bg-[#D9DCE0]'
            }`}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {/* Right: Single Execution Target Switch + Colab Trigger + Fixed-Width Primary Action */}
      <div className="flex items-center gap-2 flex-shrink-0">
        {/* Execution Target Segmented Control (6px radius, white active surface on muted gray) */}
        <div
          className="flex items-center bg-[#E3E5E8] rounded-[6px] p-[3px]"
          title={isProcessing ? '解析中は実行先を変更できません' : '解析の実行先を選択'}
        >
          <button
            type="button"
            disabled={isProcessing}
            onClick={() => onChangeExecutionTarget('local')}
            className={`flex items-center gap-1.5 px-2.5 h-[26px] rounded-[4px] text-xs font-medium transition-colors ${
              !isColab
                ? 'bg-white text-[#111111]'
                : 'text-[#71717A] hover:text-[#111111]'
            } ${isProcessing ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
          >
            <Cpu className="w-3.5 h-3.5" strokeWidth={1.6} />
            <span>ローカル</span>
          </button>
          <button
            type="button"
            disabled={isProcessing}
            onClick={() => onChangeExecutionTarget('colab')}
            className={`flex items-center gap-1.5 px-2.5 h-[26px] rounded-[4px] text-xs font-medium transition-colors ${
              isColab
                ? 'bg-white text-[#111111]'
                : 'text-[#71717A] hover:text-[#111111]'
            } ${isProcessing ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
          >
            <Cloud className="w-3.5 h-3.5" strokeWidth={1.6} />
            <span>Colab</span>
          </button>
        </div>

        {/* Colab Connection Settings Trigger + Optional Quick Stop */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onOpenColabModal}
            className="h-8 px-2.5 rounded-[6px] bg-transparent hover:bg-black/[0.05] text-xs font-medium text-[#52525B] hover:text-[#111111] flex items-center gap-1.5 tabular-nums transition-colors cursor-pointer"
            title={
              isCliSsh
                ? cliStatus?.status_message || 'Google Colab 接続設定を開く'
                : 'Google Colab 接続設定を開く'
            }
          >
            <Link2 className="w-3.5 h-3.5 flex-shrink-0" strokeWidth={1.6} />
            {dotClass && <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotClass}`} />}
            <span className="max-w-[110px] truncate">{getColabLabel()}</span>
          </button>

          {isCliSsh && cliStatus?.state === 'running' && !isProcessing && onStopColabCli && (
            <button
              type="button"
              onClick={onStopColabCli}
              className="w-8 h-8 rounded-[6px] bg-[#FEE2E2] text-[#B91C1C] hover:bg-[#FECACA] flex items-center justify-center transition-colors cursor-pointer"
              title="Colab ランタイムを今すぐ停止 (colab stop)"
              aria-label="Colab ランタイム停止"
            >
              <Square className="w-3 h-3 fill-current" strokeWidth={1.8} />
            </button>
          )}
        </div>

        {/* Single Unified Start / Stop CTA (fixed width 112px, zero jitter) */}
        <button
          type="button"
          onClick={handlePrimaryAction}
          disabled={isProcessing ? !canCancel : !canStart}
          className={`h-8 w-[112px] rounded-[6px] text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors flex-shrink-0 ${
            isStopping
              ? 'bg-[#B91C1C] text-white cursor-wait opacity-90'
              : isProcessing
              ? 'bg-[#FEE2E2] text-[#B91C1C] hover:bg-[#FECACA] cursor-pointer'
              : canStart
              ? 'bg-[#111111] text-white hover:bg-[#27272A] cursor-pointer'
              : 'bg-[#D9DCE0] text-[#8E8E98] cursor-not-allowed'
          }`}
        >
          {isProcessing ? (
            <>
              <Square className="w-3 h-3 fill-current" strokeWidth={1.8} />
              <span>{isStopping ? '中断中...' : '解析中断'}</span>
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-current" strokeWidth={1.8} />
              <span>解析開始</span>
            </>
          )}
        </button>
      </div>
    </header>
  );
};
