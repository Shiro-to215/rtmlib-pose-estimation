import React from 'react';
import { Film } from 'lucide-react';

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
  metaText = '右側の予約リストから解析を開始できます',
  resolutionInfo,
  isIdle = true,
}) => {
  const displayTitle = isIdle ? '待機中' : ellipsize(videoTitle, 28);
  const displayMeta = isIdle
    ? metaText
    : resolutionInfo
    ? `${resolutionInfo}  |  ${ellipsize(metaText, 38)}`
    : ellipsize(metaText, 38);

  return (
    <div className="flex flex-col w-full">
      {/* 16:9 Letterbox Frame */}
      <div className="relative w-full aspect-video bg-[#E2E8E6] rounded-lg border border-[#D4DFDC] overflow-hidden flex items-center justify-center shadow-inner">
        {imageSrc ? (
          <>
            <img
              src={imageSrc}
              alt={videoTitle}
              className="w-full h-full object-contain select-none"
            />
            {resolutionInfo && (
              <span className="absolute bottom-1.5 right-1.5 bg-black/60 text-white text-[10px] px-1.5 py-0.5 rounded backdrop-blur-sm font-mono">
                {resolutionInfo}
              </span>
            )}
          </>
        ) : (
          <div className="flex flex-col items-center justify-center text-center p-4 text-[#64748B] select-none">
            <Film className="w-8 h-8 text-[#94A3B8] mb-1.5 stroke-[1.5]" />
            <p className="text-xs font-medium leading-relaxed">
              動画プレビュー
              <br />
              <span className="text-[11px] text-[#94A3B8]">
                （現在解析中の動画はありません）
              </span>
            </p>
          </div>
        )}
      </div>

      {/* Video Name & Destination Info Labels */}
      <div className="mt-2.5 px-1 text-center">
        <h2
          className={`text-sm font-bold truncate transition-colors ${
            isIdle ? 'text-[#475569]' : 'text-[#1E293B]'
          }`}
          title={videoTitle}
        >
          {displayTitle}
        </h2>
        <p
          className="text-xs text-[#64748B] mt-0.5 truncate transition-colors"
          title={metaText}
        >
          {displayMeta}
        </p>
      </div>
    </div>
  );
};
