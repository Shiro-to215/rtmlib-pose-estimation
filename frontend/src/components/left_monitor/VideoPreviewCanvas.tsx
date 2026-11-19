import React from 'react';

export interface VideoPreviewCanvasProps {
  imageSrc?: string;
  videoTitle?: string;
  metaText?: string;
  resolutionInfo?: string;
  isIdle?: boolean;
}

function ellipsize(text: string, limit: number): string {
  if (!text || text.length <= limit) return text;
  const keep = Math.max(4, Math.floor((limit - 3) / 2));
  return `${text.slice(0, keep)}...${text.slice(-keep)}`;
}

export const VideoPreviewCanvas: React.FC<VideoPreviewCanvasProps> = ({
  imageSrc,
  videoTitle = '待機中',
  metaText = '',
  resolutionInfo,
  isIdle = true,
}) => {
  const displayTitle = isIdle ? '待機中' : ellipsize(videoTitle, 28);
  const displayMeta = isIdle ? 'キュー開始でフレーム表示' : metaText;

  return (
    <section className="bg-white rounded-[14px] p-4 flex flex-col gap-2.5 flex-shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xs font-medium text-[#71717A]">解析中プレビュー</h2>
        <span className="text-[11px] font-mono text-[#71717A] tabular-nums">
          {!isIdle && resolutionInfo ? resolutionInfo : '16:9'}
        </span>
      </div>

      {/* Flexible 16:9 Viewport (CSS hairline grid when idle, zero decorative SVG) */}
      <div className="w-full aspect-video rounded-[6px] overflow-hidden relative flex items-center justify-center">
        {imageSrc ? (
          <img
            src={imageSrc}
            alt={videoTitle}
            className="w-full h-full object-contain select-none bg-[#111111]"
          />
        ) : (
          <div className="w-full h-full preview-idle-grid border border-black/[0.06] rounded-[6px] flex items-center justify-center select-none">
            <span className="text-[11px] font-medium text-[#A1A1AA] tracking-wide">
              {isIdle ? '解析待機中' : 'フレーム読み込み中...'}
            </span>
          </div>
        )}
      </div>

      {/* 1-Line Compact Metadata Footer */}
      <div className="flex items-center justify-between gap-3 pt-0.5 min-w-0">
        <span
          className={`text-xs font-medium truncate ${
            isIdle ? 'text-[#71717A]' : 'text-[#111111]'
          }`}
          title={videoTitle}
        >
          {displayTitle}
        </span>
        <span
          className="text-[11px] font-mono text-[#A1A1AA] truncate max-w-[48%]"
          title={displayMeta}
        >
          {displayMeta}
        </span>
      </div>
    </section>
  );
};
