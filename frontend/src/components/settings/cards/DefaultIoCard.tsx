import React from 'react';
import { FolderOpen } from 'lucide-react';
import { getBackendApi } from '../../../api/pywebview';

export interface DefaultIoCardProps {
  defaultRoot: string;
  onChangeDefaultRoot: (path: string) => void;
}

export const DefaultIoCard: React.FC<DefaultIoCardProps> = ({
  defaultRoot,
  onChangeDefaultRoot,
}) => {
  const handleBrowse = async () => {
    const api = getBackendApi();
    try {
      const dir = await api.select_directory('既定の出力親フォルダーを選択');
      if (dir) {
        onChangeDefaultRoot(dir);
      }
    } catch (err) {
      console.error('Error selecting default directory:', err);
    }
  };

  return (
    <div className="bg-white rounded-[14px] p-5 select-none">
      <label className="block text-xs font-semibold text-[#111111]">
        新規予約時の既定出力親フォルダー
      </label>
      <p className="text-[11px] text-[#71717A] mt-0.5 mb-3">
        「予約を追加」を開いたときに最初から入力される出力先の親フォルダーです（登録済みの予約には影響しません）。
      </p>
      <div className="flex gap-2">
        <input
          type="text"
          value={defaultRoot}
          onChange={(e) => onChangeDefaultRoot(e.target.value)}
          placeholder="C:\...\動画解析出力"
          className="flex-1 min-w-0 h-9 px-3 text-xs font-mono rounded-[6px] bg-[#F4F5F6] border border-black/[0.08] text-[#111111] placeholder:text-[#A1A1AA] focus:bg-white focus:border-[#111111] focus:outline-none select-text"
        />
        <button
          type="button"
          onClick={handleBrowse}
          className="h-9 px-3 text-xs font-medium bg-[#F4F5F6] hover:bg-[#E3E5E8] text-[#111111] rounded-[6px] transition-colors cursor-pointer inline-flex items-center gap-1.5 flex-shrink-0"
        >
          <FolderOpen className="w-3.5 h-3.5 text-[#52525B]" strokeWidth={1.6} />
          <span>参照…</span>
        </button>
      </div>
    </div>
  );
};
