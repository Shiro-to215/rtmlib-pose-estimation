import React, { useEffect, useRef, useState } from 'react';
import { Pause, Play, Trash2 } from 'lucide-react';
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

  useEffect(() => {
    if (!autoScroll || !containerRef.current) return;
    const el = containerRef.current;
    el.scrollTop = el.scrollHeight;
  }, [logs, autoScroll]);

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
        return 'text-white font-semibold';
      case 'error':
        return 'text-[#FCA5A5] bg-[#EF4444]/15 px-1.5 py-0.5 rounded-[4px]';
      case 'system':
        return 'text-[#A1A1AA]';
      default:
        return 'text-[#D4D4D8]';
    }
  };

  return (
    <section
      className={`flex-1 min-h-0 bg-[#111111] text-white rounded-[14px] p-4 flex flex-col overflow-hidden ${className}`}
    >
      {/* Log Header */}
      <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.08] flex-shrink-0 select-none">
        <div className="flex items-center gap-2">
          <h2 className="text-xs font-medium text-white">実行ログ</h2>
          {logs.length > 0 && (
            <span className="text-[11px] font-mono text-[#A1A1AA] tabular-nums">
              {logs.length}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setAutoScroll(!autoScroll)}
            className="flex items-center gap-1 text-[11px] text-[#A1A1AA] hover:text-white transition-colors cursor-pointer"
            title={autoScroll ? '自動スクロールを一時停止' : '自動スクロールを再開'}
          >
            {autoScroll ? (
              <Pause className="w-3 h-3" strokeWidth={1.6} />
            ) : (
              <Play className="w-3 h-3" strokeWidth={1.6} />
            )}
            <span>{autoScroll ? '追従中' : '停止中'}</span>
          </button>

          <button
            type="button"
            onClick={onClear}
            className="flex items-center gap-1 text-[11px] text-[#A1A1AA] hover:text-white transition-colors cursor-pointer"
            title="ログをクリア"
          >
            <Trash2 className="w-3 h-3" strokeWidth={1.6} />
            <span>クリア</span>
          </button>
        </div>
      </div>

      {/* Scrollable Monospace Log Body */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 min-h-0 pt-2.5 overflow-y-auto font-mono text-[11.5px] leading-[1.55] whitespace-pre-wrap break-all select-text dark-scrollbar tabular-nums"
      >
        {logs.length === 0 ? (
          <div className="text-[#A1A1AA]">ログ待機中</div>
        ) : (
          logs.map((log) => (
            <div key={log.id} className={`${getTagClass(log.tag)} py-0.5`}>
              {log.text}
            </div>
          ))
        )}
      </div>
    </section>
  );
};
