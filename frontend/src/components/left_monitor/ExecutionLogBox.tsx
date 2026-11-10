import React, { useEffect, useRef, useState } from 'react';
import { Trash2, Pause, Play } from 'lucide-react';
import { LogEntry } from '../../types/models';

export interface ExecutionLogBoxProps {
  logs: LogEntry[];
  onClear: () => void;
  className?: string;
}

export const ExecutionLogBox: React.FC<ExecutionLogBoxProps> = ({
  logs,
  onClear,
  className = '',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState<boolean>(true);

  // Auto-scroll when new logs arrive, if auto-scroll is enabled
  useEffect(() => {
    if (!autoScroll || !containerRef.current) return;
    const el = containerRef.current;
    el.scrollTop = el.scrollHeight;
  }, [logs, autoScroll]);

  // Handle user manual scroll: pause auto-scroll if user scrolls up
  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 15;
    if (isAtBottom !== autoScroll) {
      setAutoScroll(isAtBottom);
    }
  };

  const getTagClass = (tag: LogEntry['tag']) => {
    switch (tag) {
      case 'heading':
        return 'text-[#0B534D] font-bold';
      case 'error':
        return 'text-[#C8332B] font-medium bg-[#FEF2F2]/50 px-1 rounded';
      case 'system':
        return 'text-[#64748B] italic';
      default:
        return 'text-[#1E293B]';
    }
  };

  return (
    <div
      className={`flex flex-col h-36 bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg overflow-hidden shadow-inner ${className}`}
    >
      {/* Log Header */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#F1F5F9] border-b border-[#CBD5E1] text-xs select-none">
        <span className="font-bold text-[#475569]">実行ログ</span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className="flex items-center gap-1 text-[11px] text-[#64748B] hover:text-[#1E293B] transition-colors"
            title={autoScroll ? '自動スクロールを一時停止' : '自動スクロールを再開'}
          >
            {autoScroll ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
            <span>{autoScroll ? '追従中' : '停止中'}</span>
          </button>
          <button
            onClick={onClear}
            className="flex items-center gap-1 text-[11px] text-[#64748B] hover:text-[#C8332B] transition-colors"
            title="ログをクリア"
          >
            <Trash2 className="w-3 h-3" />
            <span>クリア</span>
          </button>
        </div>
      </div>

      {/* Scrollable Monospace Body */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 p-2.5 overflow-y-auto font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-all select-text"
      >
        {logs.length === 0 ? (
          <div className="text-[#94A3B8] italic">[ログはありません]</div>
        ) : (
          logs.map((log) => (
            <div key={log.id} className={`${getTagClass(log.tag)} py-0.5`}>
              {log.text}
            </div>
          ))
        )}
      </div>
    </div>
  );
};
