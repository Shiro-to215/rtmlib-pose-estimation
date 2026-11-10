import React from 'react';
import { Trash2, ArrowUp, ArrowDown, Settings } from 'lucide-react';

export interface QueueToolbarProps {
  pendingCount: number;
  failedCount: number;
  selectedCount: number;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onDelete: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onOpenBasicSettings: () => void;
}

export const QueueToolbar: React.FC<QueueToolbarProps> = ({
  pendingCount,
  failedCount,
  selectedCount,
  canMoveUp,
  canMoveDown,
  onDelete,
  onMoveUp,
  onMoveDown,
  onOpenBasicSettings,
}) => {
  return (
    <div className="h-14 px-5 border-b border-[#D4DFDC] flex items-center justify-between bg-[#F8FAFA] flex-shrink-0 select-none">
      {/* Left: Title & Summary Badge */}
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-bold text-[#1E293B]">予約リスト</h2>
        <span className="px-2.5 py-0.5 rounded-md text-xs font-bold bg-[#E4F3F0] text-[#0B534D] border border-[#B5DDD6]">
          待機 {pendingCount}件{failedCount > 0 ? ` ・ 失敗 ${failedCount}件` : ''}
        </span>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-2">
        {/* 削除 Button */}
        <button
          onClick={onDelete}
          disabled={selectedCount === 0}
          className={`flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-bold rounded-lg border transition-colors ${
            selectedCount > 0
              ? 'border-[#F5C2C0] text-[#C8332B] hover:bg-[#FEF2F2] cursor-pointer'
              : 'border-[#E2E8F0] text-[#94A3B8] cursor-not-allowed bg-transparent'
          }`}
        >
          <Trash2 className="w-3.5 h-3.5" />
          <span>削除</span>
        </button>

        {/* 上へ Button */}
        <button
          onClick={onMoveUp}
          disabled={!canMoveUp}
          className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg border transition-colors ${
            canMoveUp
              ? 'border-[#B2C4BE] text-[#1E293B] hover:bg-[#EBF0EE] cursor-pointer'
              : 'border-[#E2E8F0] text-[#94A3B8] cursor-not-allowed bg-transparent'
          }`}
        >
          <ArrowUp className="w-3.5 h-3.5" />
          <span>上へ</span>
        </button>

        {/* 下へ Button */}
        <button
          onClick={onMoveDown}
          disabled={!canMoveDown}
          className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-lg border transition-colors ${
            canMoveDown
              ? 'border-[#B2C4BE] text-[#1E293B] hover:bg-[#EBF0EE] cursor-pointer'
              : 'border-[#E2E8F0] text-[#94A3B8] cursor-not-allowed bg-transparent'
          }`}
        >
          <ArrowDown className="w-3.5 h-3.5" />
          <span>下へ</span>
        </button>

        {/* 基本設定 Button */}
        <button
          onClick={onOpenBasicSettings}
          className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-bold bg-[#E4F3F0] hover:bg-[#D0EBE6] text-[#0B534D] border border-[#B5DDD6] rounded-lg transition-colors ml-1 cursor-pointer"
        >
          <Settings className="w-3.5 h-3.5" />
          <span>基本設定</span>
        </button>
      </div>
    </div>
  );
};
