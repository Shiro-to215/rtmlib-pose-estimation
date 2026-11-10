import React from 'react';

export type ProgressTone = 'idle' | 'yolo' | 'rtmpose' | 'done' | 'stopping';

export interface CircularProgressRingProps {
  percent: number; // 0 to 100
  phaseTitle?: string;
  subtitle?: string;
  tone?: ProgressTone;
}

export const CircularProgressRing: React.FC<CircularProgressRingProps> = ({
  percent = 0,
  phaseTitle = '待機中',
  subtitle = '予約を開始すると進捗を表示',
  tone = 'idle',
}) => {
  const safePct = isNaN(percent) ? 0 : Math.max(0, Math.min(100, Math.round(percent)));

  // SVG Geometry constants matching CustomTkinter 184px diameter & 15px stroke
  const size = 184;
  const strokeWidth = 15;
  const center = size / 2; // 92
  const radius = 76; // Centerline radius
  const circumference = 2 * Math.PI * radius; // ~477.522px
  const strokeDashoffset = circumference * (1 - safePct / 100);

  // Phase color mappings
  const colorMap: Record<ProgressTone, { stroke: string; pct: string; phase: string }> = {
    idle: {
      stroke: '#0F766E',
      pct: 'text-[#64748B]',
      phase: 'text-[#475569]',
    },
    yolo: {
      stroke: '#0F766E', // TEAL
      pct: 'text-[#1E293B]',
      phase: 'text-[#0B534D]',
    },
    rtmpose: {
      stroke: '#0369A1', // POSE_BLUE
      pct: 'text-[#1E293B]',
      phase: 'text-[#0369A1]',
    },
    done: {
      stroke: '#15803D', // SUCCESS
      pct: 'text-[#15803D]',
      phase: 'text-[#15803D]',
    },
    stopping: {
      stroke: '#C8332B', // DANGER
      pct: 'text-[#C8332B]',
      phase: 'text-[#C8332B]',
    },
  };

  const currentColors = colorMap[tone] || colorMap.idle;

  return (
    <div className="relative flex items-center justify-center select-none" style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="transform -rotate-90"
      >
        {/* Track Ring */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke="#E2EBE8"
          strokeWidth={strokeWidth}
        />

        {/* 50% Milestone Marker (Bottom / 6 o'clock dividing YOLO and RTMPose phases) */}
        <line
          x1={center - radius - strokeWidth / 2 - 1}
          y1={center}
          x2={center - radius + strokeWidth / 2 + 1}
          y2={center}
          stroke="#FFFFFF"
          strokeWidth="2.5"
          strokeOpacity="0.95"
          strokeLinecap="round"
        />

        {/* Active Progress Arc (GPU-Accelerated strokeDashoffset) */}
        {safePct > 0 && (
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={currentColors.stroke}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            className="transition-all duration-200 ease-out"
          />
        )}
      </svg>

      {/* Center Status Typography */}
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center pointer-events-none px-4">
        <span className={`text-2xl font-bold font-mono tracking-tight ${currentColors.pct}`}>
          {safePct}%
        </span>
        <span className={`text-xs font-bold tracking-wide mt-0.5 ${currentColors.phase}`}>
          {phaseTitle}
        </span>
        {subtitle && (
          <span className="text-[10px] text-[#64748B] mt-0.5 truncate max-w-[140px]">
            {subtitle}
          </span>
        )}
      </div>
    </div>
  );
};
