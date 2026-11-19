import React, { useEffect, useMemo, useState } from 'react';
import { QueueFilterMode, QueueToolbar } from './QueueToolbar';
import { QueueJobCard } from './QueueJobCard';
import { DashedAddZone } from './DashedAddZone';
import { ReservationJob } from '../../types/models';

export interface QueueListViewProps {
  jobs: ReservationJob[];
  onOpenAddReservation: (initialVideos?: string[]) => void;
  onOpenJobSettings: (jobId: string) => void;
  onDeleteJobs: (jobIds: string[]) => void;
  onMoveJob: (jobId: string, direction: 'up' | 'down') => void;
  onReorderJob?: (jobId: string, targetVisibleIndex: number) => void;
  onRetryJob: (jobId: string) => void;
  onSelectionChange?: (selectedIds: string[]) => void;
}

export const QueueListView: React.FC<QueueListViewProps> = ({
  jobs,
  onOpenAddReservation,
  onOpenJobSettings,
  onDeleteJobs,
  onMoveJob,
  onReorderJob,
  onRetryJob,
  onSelectionChange,
}) => {
  // Display pending, failed, and background local-rendering jobs in the active queue list
  const visibleJobs = useMemo(
    () =>
      jobs.filter(
        (j) => j.state === 'pending' || j.state === 'failed' || Boolean(j.local_rendering)
      ),
    [jobs]
  );

  const pendingCount = useMemo(
    () => jobs.filter((j) => j.state === 'pending').length,
    [jobs]
  );
  const failedCount = useMemo(
    () => jobs.filter((j) => j.state === 'failed').length,
    [jobs]
  );

  const [filterMode, setFilterMode] = useState<QueueFilterMode>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [lastAnchorId, setLastAnchorId] = useState<string | null>(null);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);

  const filteredJobs = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return visibleJobs.filter((job) => {
      if (filterMode === 'pending' && job.state !== 'pending') return false;
      if (filterMode === 'failed' && job.state !== 'failed') return false;
      if (q) {
        const hay = `${job.video_name} ${job.output_folder} ${job.output_path}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [visibleJobs, filterMode, searchQuery]);

  const canReorder = filterMode === 'all' && searchQuery.trim() === '';

  useEffect(() => {
    const selectableSet = new Set(
      visibleJobs.filter((j) => !j.local_rendering).map((j) => j.id)
    );
    setSelectedIds((prev) => {
      const next = prev.filter((id) => selectableSet.has(id));
      return next.length === prev.length ? prev : next;
    });
    if (lastAnchorId && !selectableSet.has(lastAnchorId)) {
      setLastAnchorId(null);
    }
  }, [visibleJobs, lastAnchorId]);

  useEffect(() => {
    onSelectionChange?.(selectedIds);
  }, [selectedIds, onSelectionChange]);

  // Selection logic supporting single, Ctrl (toggle), and Shift (range)
  const handleSelect = (e: React.MouseEvent, jobId: string) => {
    const targetJob = visibleJobs.find((j) => j.id === jobId);
    if (!targetJob || targetJob.local_rendering) return;

    if (e.ctrlKey || e.metaKey) {
      if (selectedIds.includes(jobId)) {
        setSelectedIds(selectedIds.filter((id) => id !== jobId));
      } else {
        setSelectedIds([...selectedIds, jobId]);
      }
      setLastAnchorId(jobId);
    } else if (e.shiftKey && lastAnchorId) {
      const anchorIdx = filteredJobs.findIndex((j) => j.id === lastAnchorId);
      const currentIdx = filteredJobs.findIndex((j) => j.id === jobId);
      if (anchorIdx !== -1 && currentIdx !== -1) {
        const start = Math.min(anchorIdx, currentIdx);
        const end = Math.max(anchorIdx, currentIdx);
        const rangeIds = filteredJobs
          .slice(start, end + 1)
          .filter((j) => !j.local_rendering)
          .map((j) => j.id);
        setSelectedIds(Array.from(new Set([...selectedIds, ...rangeIds])));
      }
    } else {
      setSelectedIds([jobId]);
      setLastAnchorId(jobId);
    }
  };

  const selectedCount = selectedIds.length;
  const selectedIndex =
    selectedCount === 1 ? visibleJobs.findIndex((j) => j.id === selectedIds[0]) : -1;
  const canMoveUp = selectedCount === 1 && selectedIndex > 0;
  const canMoveDown =
    selectedCount === 1 && selectedIndex !== -1 && selectedIndex < visibleJobs.length - 1;

  const handleClearSelection = () => {
    setSelectedIds([]);
    setLastAnchorId(null);
  };

  const handleDelete = () => {
    if (selectedIds.length > 0) {
      onDeleteJobs(selectedIds);
      setSelectedIds([]);
    }
  };

  const handleMoveUp = () => {
    if (canMoveUp) {
      onMoveJob(selectedIds[0], 'up');
    }
  };

  const handleMoveDown = () => {
    if (canMoveDown) {
      onMoveJob(selectedIds[0], 'down');
    }
  };

  // DnD Card Reordering (active when viewing full unfiltered list)
  const handleDragStart = (_e: React.DragEvent, _jobId: string, index: number) => {
    if (!canReorder) return;
    setDraggedIndex(index);
  };

  const handleDragOver = (e: React.DragEvent, _index: number) => {
    if (!canReorder) return;
    e.preventDefault();
  };

  const handleDrop = (_e: React.DragEvent, targetIndex: number) => {
    if (!canReorder || draggedIndex === null || draggedIndex === targetIndex) {
      setDraggedIndex(null);
      return;
    }
    const draggedJob = visibleJobs[draggedIndex];
    if (!draggedJob) {
      setDraggedIndex(null);
      return;
    }

    if (onReorderJob) {
      onReorderJob(draggedJob.id, targetIndex);
    } else if (draggedIndex < targetIndex) {
      onMoveJob(draggedJob.id, 'down');
    } else {
      onMoveJob(draggedJob.id, 'up');
    }
    setDraggedIndex(null);
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden select-none">
      {/* Contextual Queue Toolbar */}
      <QueueToolbar
        filterMode={filterMode}
        onChangeFilterMode={setFilterMode}
        searchQuery={searchQuery}
        onChangeSearchQuery={setSearchQuery}
        totalCount={visibleJobs.length}
        pendingCount={pendingCount}
        failedCount={failedCount}
        selectedCount={selectedCount}
        canMoveUp={canMoveUp}
        canMoveDown={canMoveDown}
        onClearSelection={handleClearSelection}
        onDelete={handleDelete}
        onMoveUp={handleMoveUp}
        onMoveDown={handleMoveDown}
      />

      {/* Column Header Strip (matches card column template exactly) */}
      <div className="h-8 px-4 border-b border-black/[0.06] grid grid-cols-[36px_76px_minmax(0,1fr)_140px_72px_64px] items-center gap-2.5 text-[11px] font-medium text-[#71717A] flex-shrink-0">
        <div>#</div>
        <div>プレビュー</div>
        <div>動画 / 出力先</div>
        <div>推論構成</div>
        <div>状態</div>
        <div className="text-right">操作</div>
      </div>

      {/* Scrollable Queue Rows */}
      <div className="flex-1 min-h-0 overflow-y-auto px-[6px] py-2 flex flex-col">
        {visibleJobs.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center px-4 py-8">
            <p className="text-xs font-medium text-[#111111]">待機中の予約はありません</p>
            <p className="text-[11px] text-[#71717A] mt-1">
              下のドロップ欄、または上部の「予約を追加」から動画を登録してください。
            </p>
          </div>
        ) : filteredJobs.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center px-4 py-8">
            <p className="text-xs font-medium text-[#111111]">一致する予約が見つかりません</p>
            <p className="text-[11px] text-[#71717A] mt-1">
              フィルタまたは検索キーワードを変更してください。
            </p>
          </div>
        ) : (
          <div>
            {filteredJobs.map((job, idx) => {
              const fullIdx = visibleJobs.findIndex((j) => j.id === job.id);
              return (
                <QueueJobCard
                  key={job.id}
                  job={job}
                  orderNum={fullIdx !== -1 ? fullIdx + 1 : idx + 1}
                  isSelected={selectedIds.includes(job.id)}
                  canReorder={canReorder}
                  onSelect={handleSelect}
                  onOpenJobSettings={onOpenJobSettings}
                  onRetry={onRetryJob}
                  onDragStart={handleDragStart}
                  onDragOver={handleDragOver}
                  onDrop={handleDrop}
                  onDragEnd={() => setDraggedIndex(null)}
                  index={fullIdx !== -1 ? fullIdx : idx}
                />
              );
            })}
          </div>
        )}
      </div>

      {/* Compact Drop / Add Footer */}
      <DashedAddZone
        onClick={() => onOpenAddReservation()}
        onDropVideos={(videos) => onOpenAddReservation(videos)}
      />
    </div>
  );
};
