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
      className={`h-9 mx-4 mb-3 mt-1 rounded-[6px] border border-dashed transition-colors flex items-center justify-center gap-1.5 cursor-pointer select-none text-xs font-medium flex-shrink-0 ${
        isDragOver
          ? 'border-[#111111] bg-[#E3E5E8] text-[#111111]'
          : 'border-black/[0.12] hover:border-[#111111] bg-[#F4F5F6]/50 hover:bg-[#F4F5F6] text-[#71717A] hover:text-[#111111]'
      }`}
    >
      <Plus className="w-3.5 h-3.5 flex-shrink-0" strokeWidth={1.6} />
      <span>動画ファイルをドロップ、またはクリックして予約を追加</span>
    </div>
  );
};
