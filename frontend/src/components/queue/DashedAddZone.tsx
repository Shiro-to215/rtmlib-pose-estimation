import React, { useState } from 'react';
import { Plus } from 'lucide-react';

export interface DashedAddZoneProps {
  onClick: () => void;
  onDropVideos: (videoPaths: string[]) => void;
}

export const DashedAddZone: React.FC<DashedAddZoneProps> = ({ onClick, onDropVideos }) => {
  const [isDragOver, setIsDragOver] = useState(false);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const videoExts = ['.mp4', '.mov', '.avi', '.mkv', '.m4v', '.wmv', '.webm'];
    const paths: string[] = [];
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      for (let i = 0; i < e.dataTransfer.files.length; i++) {
        const file = e.dataTransfer.files[i];
        const path = (file as any).pywebviewFullPath || (file as any).path || '';
        const ext = path ? '.' + path.split('.').pop()?.toLowerCase() : '';
        if (path && videoExts.includes(ext)) {
          paths.push(path);
        }
      }
    }
    if (paths.length > 0) {
      onDropVideos(paths);
    }
  };

  return (
    <div
      onClick={onClick}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`h-20 rounded-xl border-2 border-dashed transition-all flex flex-col items-center justify-center cursor-pointer select-none my-2 px-4 flex-shrink-0 ${
        isDragOver
          ? 'border-[#0F766E] bg-[#E4F3F0] text-[#0B534D]'
          : 'border-[#8DA49E] hover:border-[#0F766E] bg-[#F9FBFA] hover:bg-[#E4F3F0] text-[#1E293B]'
      }`}
    >
      <div className="flex items-center gap-1.5 font-bold text-sm">
        <Plus className="w-4 h-4 text-[#0F766E]" />
        <span>予約を追加</span>
      </div>
      <span className="text-[11px] text-[#64748B] mt-0.5">
        クリックして動画と出力先を指定（または動画ファイルをここへドロップ）
      </span>
    </div>
  );
};
