import React from 'react';

export type StatusBadgeState = 'idle' | 'running' | 'yolo' | 'rtmpose' | 'stopping';

export interface StatusBadgeProps {
  state: StatusBadgeState;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ state, className = '' }) => {
  const configs: Record<StatusBadgeState, { text: string; bg: string; textCol: string }> = {
    idle: {
      text: '待機中',
      bg: 'bg-[#EBF0EE]',
      textCol: 'text-[#475569]',
    },
    running: {
      text: '解析実行中',
      bg: 'bg-[#E4F3F0]',
      textCol: 'text-[#0B534D]',
    },
    yolo: {
      text: 'YOLO 処理中',
      bg: 'bg-[#E4F3F0]',
      textCol: 'text-[#0B534D]',
    },
    rtmpose: {
      text: 'RTMPose 処理中',
      bg: 'bg-[#E0F2FE]',
      textCol: 'text-[#0369A1]',
    },
    stopping: {
      text: '中断処理中',
      bg: 'bg-[#FEF2F2]',
      textCol: 'text-[#C8332B]',
    },
  };

  const config = configs[state] || configs.idle;

  return (
    <span
      className={`inline-flex items-center justify-center h-6 px-2.5 rounded-md text-xs font-bold transition-colors select-none ${config.bg} ${config.textCol} ${className}`}
    >
      {config.text}
    </span>
  );
};
