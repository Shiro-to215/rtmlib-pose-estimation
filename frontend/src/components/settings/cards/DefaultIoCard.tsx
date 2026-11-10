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
    <div className="bg-[#E4F3F0] border border-[#B5DDD6] rounded-lg p-4 mb-4 select-none">
      <label className="block text-xs font-bold text-[#0B534D] mb-0.5">
        新規予約時の既定出力親フォルダー
      </label>
      <p className="text-[11px] text-[#475569] mb-2.5">
        「予約を追加」を開いたときに最初から入力される出力先の親フォルダーです（登録済みの予約には影響しません）。
      </p>
      <div className="flex gap-2">
        <input
          type="text"
          value={defaultRoot}
          onChange={(e) => onChangeDefaultRoot(e.target.value)}
          placeholder="C:\...\動画解析出力"
          className="flex-1 h-9 px-3 text-xs border border-[#B5DDD6] rounded-lg bg-white text-[#1E293B] font-mono focus:border-[#0F766E] focus:outline-none"
        />
        <button
          onClick={handleBrowse}
          className="px-3.5 h-9 text-xs font-bold bg-white hover:bg-[#D0EBE6] text-[#0B534D] border border-[#B5DDD6] rounded-lg transition-colors cursor-pointer flex items-center gap-1"
        >
          <FolderOpen className="w-3.5 h-3.5" />
          <span>参照…</span>
        </button>
      </div>
    </div>
  );
};
