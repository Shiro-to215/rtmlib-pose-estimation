import React from 'react';
import { ArrowDown, ArrowUp, Search, Trash2, X } from 'lucide-react';

export type QueueFilterMode = 'all' | 'pending' | 'failed';

export interface QueueToolbarProps {
  filterMode: QueueFilterMode;
  onChangeFilterMode: (mode: QueueFilterMode) => void;
  searchQuery: string;
  onChangeSearchQuery: (query: string) => void;
  totalCount: number;
  pendingCount: number;
  failedCount: number;
  selectedCount: number;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onClearSelection: () => void;
  onDelete: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

export const QueueToolbar: React.FC<QueueToolbarProps> = ({
  filterMode,
  onChangeFilterMode,
  searchQuery,
  onChangeSearchQuery,
  totalCount,
  pendingCount,
  failedCount,
  selectedCount,
  canMoveUp,
  canMoveDown,
  onClearSelection,
  onDelete,
  onMoveUp,
  onMoveDown,
}) => {
  const filterTabs: Array<{ id: QueueFilterMode; label: string; count: number }> = [
    { id: 'all', label: 'すべて', count: totalCount },
    { id: 'pending', label: '待機', count: pendingCount },
    { id: 'failed', label: '失敗', count: failedCount },
  ];

  return (
    <div className="h-11 px-4 border-b border-black/[0.06] flex items-center justify-between gap-3 flex-shrink-0 select-none">
      {selectedCount > 0 ? (
        <>
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="text-xs font-semibold text-[#111111] tabular-nums">
              {selectedCount}件を選択中
            </span>
            <button
              type="button"
              onClick={onClearSelection}
              className="h-7 px-2 rounded-[6px] text-xs font-medium text-[#71717A] hover:text-[#111111] hover:bg-[#F4F5F6] transition-colors cursor-pointer"
            >
              選択解除
            </button>
          </div>

          <div className="flex items-center gap-1.5 flex-shrink-0">
            <button
              type="button"
              onClick={onMoveUp}
              disabled={!canMoveUp}
              className="h-7 px-2.5 rounded-[6px] text-xs font-medium bg-[#F4F5F6] hover:bg-[#E3E5E8] text-[#111111] disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1 transition-colors cursor-pointer"
            >
              <ArrowUp className="w-3.5 h-3.5" strokeWidth={1.6} />
              <span>上へ</span>
            </button>
            <button
              type="button"
              onClick={onMoveDown}
              disabled={!canMoveDown}
              className="h-7 px-2.5 rounded-[6px] text-xs font-medium bg-[#F4F5F6] hover:bg-[#E3E5E8] text-[#111111] disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1 transition-colors cursor-pointer"
            >
              <ArrowDown className="w-3.5 h-3.5" strokeWidth={1.6} />
              <span>下へ</span>
            </button>
            <button
              type="button"
              onClick={onDelete}
              className="h-7 px-2.5 rounded-[6px] text-xs font-medium bg-[#FEE2E2] hover:bg-[#FECACA] text-[#B91C1C] inline-flex items-center gap-1 transition-colors cursor-pointer"
            >
              <Trash2 className="w-3.5 h-3.5" strokeWidth={1.6} />
              <span>削除</span>
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="flex items-center gap-3 min-w-0">
            <h2 className="text-[13px] font-semibold text-[#111111] flex-shrink-0">
              予約リスト
            </h2>
            <div className="bg-[#F4F5F6] p-[2px] rounded-[6px] flex items-center">
              {filterTabs.map((tab) => {
                const isActive = filterMode === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => onChangeFilterMode(tab.id)}
                    className={`px-2 h-6 rounded-[4px] text-[11px] font-medium transition-colors tabular-nums cursor-pointer ${
                      isActive
                        ? 'bg-white text-[#111111]'
                        : 'text-[#71717A] hover:text-[#111111]'
                    }`}
                  >
                    {tab.label} {tab.count}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="relative flex items-center flex-shrink-0">
            <Search
              className="w-3.5 h-3.5 text-[#A1A1AA] absolute left-2.5 pointer-events-none"
              strokeWidth={1.6}
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onChangeSearchQuery(e.target.value)}
              placeholder="動画名で検索..."
              aria-label="動画名で検索"
              className="w-44 h-7 pl-7 pr-6 rounded-[6px] bg-[#F4F5F6] text-xs text-[#111111] placeholder:text-[#A1A1AA] focus:bg-white focus:outline-none focus:ring-1 focus:ring-black/15 transition-colors select-text"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => onChangeSearchQuery('')}
                className="absolute right-1.5 p-0.5 text-[#A1A1AA] hover:text-[#111111] cursor-pointer"
                aria-label="検索をクリア"
              >
                <X className="w-3 h-3" strokeWidth={1.8} />
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
};
