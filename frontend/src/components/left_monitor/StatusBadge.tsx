import React from 'react';

export type StatusBadgeState = 'idle' | 'running' | 'yolo' | 'rtmpose' | 'vitpose' | 'stopping';

export interface StatusBadgeProps {
  state: StatusBadgeState;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ state, className = '' }) => {
  const configs: Record<
    StatusBadgeState,
    { text: string; bg: string; textCol: string; dot: string | null }
  > = {
    idle: {
      text: '待機中',
      bg: 'bg-[#F4F5F6]',
      textCol: 'text-[#71717A]',
      dot: null,
    },
    running: {
      text: '解析実行中',
      bg: 'bg-[#DCFCE7]',
      textCol: 'text-[#15803D]',
      dot: 'bg-[#15803D]',
    },
    yolo: {
      text: 'YOLO 処理中',
      bg: 'bg-[#DCFCE7]',
      textCol: 'text-[#15803D]',
      dot: 'bg-[#15803D]',
    },
    rtmpose: {
      text: 'RTMPose 処理中',
      bg: 'bg-[#DCFCE7]',
      textCol: 'text-[#15803D]',
      dot: 'bg-[#15803D]',
    },
    vitpose: {
      text: 'ViTPose++ 処理中',
      bg: 'bg-[#DCFCE7]',
      textCol: 'text-[#15803D]',
      dot: 'bg-[#15803D]',
    },
    stopping: {
      text: '中断処理中',
      bg: 'bg-[#FEE2E2]',
      textCol: 'text-[#B91C1C]',
      dot: 'bg-[#B91C1C]',
    },
  };

  const config = configs[state] || configs.idle;

  return (
    <span
      className={`inline-flex items-center justify-center gap-1.5 h-6 px-2 rounded-[6px] text-[11px] font-medium select-none whitespace-nowrap ${config.bg} ${config.textCol} ${className}`}
    >
      {config.dot && <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${config.dot}`} />}
      <span>{config.text}</span>
    </span>
  );
};
