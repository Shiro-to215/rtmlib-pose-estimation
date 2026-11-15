import React, { useEffect, useState } from 'react';
import { QueueToolbar } from './QueueToolbar';
import { QueueGuideStrip } from './QueueGuideStrip';
import { QueueJobCard } from './QueueJobCard';
import { DashedAddZone } from './DashedAddZone';
import { ReservationJob } from '../../types/models';

export interface QueueListViewProps {
  jobs: ReservationJob[];
  onOpenAddReservation: (initialVideos?: string[]) => void;
  onOpenBasicSettings: () => void;
  onOpenJobSettings: (jobId: string) => void;
  onDeleteJobs: (jobIds: string[]) => void;
  onMoveJob: (jobId: string, direction: 'up' | 'down') => void;
  onReorderJob?: (jobId: string, targetVisibleIndex: number) => void;
  onRetryJob: (jobId: string) => void;
}

export const QueueListView: React.FC<QueueListViewProps> = ({
  jobs,
  onOpenAddReservation,
  onOpenBasicSettings,
  onOpenJobSettings,
  onDeleteJobs,
  onMoveJob,
  onReorderJob,
  onRetryJob,
}) => {
  // Only display pending and failed jobs in the active queue list
  const visibleJobs = jobs.filter((j) => j.state === 'pending' || j.state === 'failed');

  const pendingCount = jobs.filter((j) => j.state === 'pending').length;
  const failedCount = jobs.filter((j) => j.state === 'failed').length;

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [lastAnchorId, setLastAnchorId] = useState<string | null>(null);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);

  useEffect(() => {
    const visibleSet = new Set(visibleJobs.map((j) => j.id));
    setSelectedIds((prev) => {
      const next = prev.filter((id) => visibleSet.has(id));
      return next.length === prev.length ? prev : next;
    });
    if (lastAnchorId && !visibleSet.has(lastAnchorId)) {
      setLastAnchorId(null);
    }
  }, [jobs]);

  // Selection logic supporting single, Ctrl (toggle), and Shift (range)
  const handleSelect = (e: React.MouseEvent, jobId: string) => {
    if (e.ctrlKey || e.metaKey) {
      if (selectedIds.includes(jobId)) {
        setSelectedIds(selectedIds.filter((id) => id !== jobId));
      } else {
        setSelectedIds([...selectedIds, jobId]);
      }
      setLastAnchorId(jobId);
    } else if (e.shiftKey && lastAnchorId) {
      const anchorIdx = visibleJobs.findIndex((j) => j.id === lastAnchorId);
      const currentIdx = visibleJobs.findIndex((j) => j.id === jobId);
      if (anchorIdx !== -1 && currentIdx !== -1) {
        const start = Math.min(anchorIdx, currentIdx);
        const end = Math.max(anchorIdx, currentIdx);
        const rangeIds = visibleJobs.slice(start, end + 1).map((j) => j.id);
        setSelectedIds(Array.from(new Set([...selectedIds, ...rangeIds])));
      }
    } else {
      setSelectedIds([jobId]);
      setLastAnchorId(jobId);
    }
  };

  const selectedCount = selectedIds.length;
  const selectedIndex = selectedCount === 1 ? visibleJobs.findIndex((j) => j.id === selectedIds[0]) : -1;
  const canMoveUp = selectedCount === 1 && selectedIndex > 0;
  const canMoveDown = selectedCount === 1 && selectedIndex !== -1 && selectedIndex < visibleJobs.length - 1;

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

  // DnD Card Reordering
  const handleDragStart = (_e: React.DragEvent, _jobId: string, index: number) => {
    setDraggedIndex(index);
  };

  const handleDragOver = (e: React.DragEvent, _index: number) => {
    e.preventDefault();
  };

  const handleDrop = (_e: React.DragEvent, targetIndex: number) => {
    if (draggedIndex === null || draggedIndex === targetIndex) {
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
    <div className="flex-1 flex flex-col h-full overflow-hidden select-none">
      {/* Queue Toolbar */}
      <QueueToolbar
        pendingCount={pendingCount}
        failedCount={failedCount}
        selectedCount={selectedCount}
        canMoveUp={canMoveUp}
        canMoveDown={canMoveDown}
        onDelete={handleDelete}
        onMoveUp={handleMoveUp}
        onMoveDown={handleMoveDown}
        onOpenBasicSettings={onOpenBasicSettings}
      />

      {/* Guide Strip Column Headers */}
      <QueueGuideStrip />

      {/* Card List & Dropzone Scroll Area */}
      <div className="flex-1 p-3 overflow-y-auto min-h-0 flex flex-col">
        {visibleJobs.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 text-[#64748B]">
            <p className="text-sm font-medium mb-1">待機中の予約はありません。</p>
            <p className="text-xs text-[#94A3B8]">
              下の「＋ 予約を追加」から動画を登録してください。
            </p>
          </div>
        ) : (
          <div className="flex-1">
            {visibleJobs.map((job, idx) => (
              <QueueJobCard
                key={job.id}
                job={job}
                orderNum={idx + 1}
                isSelected={selectedIds.includes(job.id)}
                onSelect={handleSelect}
                onOpenJobSettings={onOpenJobSettings}
                onRetry={onRetryJob}
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                onDragEnd={() => setDraggedIndex(null)}
                index={idx}
              />
            ))}
          </div>
        )}

        {/* Dashed Add Zone */}
        <DashedAddZone
          onClick={() => onOpenAddReservation()}
          onDropVideos={(videos) => onOpenAddReservation(videos)}
        />
      </div>
    </div>
  );
};
