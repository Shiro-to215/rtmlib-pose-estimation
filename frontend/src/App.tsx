import React, { useState } from 'react';
import { Play, Square, Settings, Trash2, ArrowUp, ArrowDown, Plus } from 'lucide-react';

export const App: React.FC = () => {
  const [isRunning, setIsRunning] = useState(false);

  return (
    <div className="flex flex-col h-screen w-screen bg-[#F2F5F4] text-[#1E293B] font-sans overflow-hidden select-none">
      {/* Top Header / Control Bar */}
      <header className="h-16 bg-white border-b border-[#D4DFDC] px-6 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsRunning(!isRunning)}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-sm shadow-sm transition-colors ${
              isRunning
                ? 'bg-[#C8332B] hover:bg-[#A62620] text-white'
                : 'bg-[#0F766E] hover:bg-[#115E59] text-white'
            }`}
          >
            {isRunning ? (
              <>
                <Square className="w-4 h-4 fill-current" />
                <span>■ 解析中断</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-current" />
                <span>▶ 解析開始</span>
              </>
            )}
          </button>
        </div>
        <div className="text-sm text-[#475569] font-medium">
          {isRunning ? '解析実行中: サンプル動画 (YOLO 25%)' : '待機中の予約を上から順番に解析します。'}
        </div>
      </header>

      {/* Main 2-Pane Split (1 : 3 Ratio) */}
      <div className="flex-1 grid grid-cols-4 p-4 gap-4 overflow-hidden">
        {/* Left Monitor Pane (1 col = 25%) */}
        <aside className="col-span-1 bg-white rounded-xl border border-[#D4DFDC] p-4 flex flex-col shadow-sm overflow-hidden">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-lg font-bold text-[#1E293B]">解析中</h1>
            <span className="px-2.5 py-0.5 rounded text-xs font-bold bg-[#EBF0EE] text-[#475569]">
              待機中
            </span>
          </div>

          {/* 16:9 Video Preview */}
          <div className="w-full aspect-video bg-[#E2E8E6] rounded border border-[#D4DFDC] flex items-center justify-center text-xs text-[#64748B] text-center p-2 mb-3">
            動画プレビュー<br />（現在解析中の動画はありません）
          </div>

          {/* Circular Progress Placeholder */}
          <div className="flex-1 flex flex-col items-center justify-center p-2">
            <div className="w-40 h-40 rounded-full border-8 border-[#E2EBE8] border-t-[#0F766E] flex flex-col items-center justify-center text-center">
              <span className="text-2xl font-bold">0%</span>
              <span className="text-xs font-bold text-[#475569]">待機中</span>
            </div>
          </div>

          {/* Execution Log */}
          <div className="h-32 bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg p-2 font-mono text-xs flex flex-col">
            <div className="flex justify-between items-center pb-1 border-b border-slate-200 mb-1 text-[11px] text-slate-500">
              <span>実行ログ</span>
              <button className="hover:text-slate-800">クリア</button>
            </div>
            <div className="flex-1 overflow-y-auto text-slate-600">
              [System] 準備完了
            </div>
          </div>
        </aside>

        {/* Right Workspace Pane (3 cols = 75%) */}
        <main className="col-span-3 bg-white rounded-xl border border-[#D4DFDC] flex flex-col shadow-sm overflow-hidden">
          {/* Queue Toolbar */}
          <div className="h-14 border-b border-[#D4DFDC] px-5 flex items-center justify-between bg-[#F8FAFA]">
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-bold text-[#1E293B]">予約リスト</h2>
              <span className="px-2 py-0.5 rounded text-xs font-bold bg-[#EBF0EE] text-[#475569]">
                待機 0件
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button className="flex items-center gap-1 px-3 py-1.5 text-xs font-bold border border-[#F5C2C0] text-[#C8332B] hover:bg-[#FEF2F2] rounded-md transition-colors">
                <Trash2 className="w-3.5 h-3.5" />
                <span>削除</span>
              </button>
              <button className="flex items-center gap-1 px-3 py-1.5 text-xs font-bold border border-[#B2C4BE] text-[#1E293B] hover:bg-[#EBF0EE] rounded-md transition-colors">
                <ArrowUp className="w-3.5 h-3.5" />
                <span>上へ</span>
              </button>
              <button className="flex items-center gap-1 px-3 py-1.5 text-xs font-bold border border-[#B2C4BE] text-[#1E293B] hover:bg-[#EBF0EE] rounded-md transition-colors">
                <ArrowDown className="w-3.5 h-3.5" />
                <span>下へ</span>
              </button>
              <button className="flex items-center gap-1 px-3.5 py-1.5 text-xs font-bold bg-[#E4F3F0] hover:bg-[#D0EBE6] text-[#0B534D] border border-[#B5DDD6] rounded-md transition-colors">
                <Settings className="w-3.5 h-3.5" />
                <span>基本設定</span>
              </button>
            </div>
          </div>

          {/* Queue Content / Dashed Add Zone */}
          <div className="flex-1 p-6 overflow-y-auto flex flex-col justify-end">
            <div className="border-2 border-dashed border-[#8DA49E] hover:border-[#0F766E] hover:bg-[#E4F3F0] transition-colors rounded-xl p-6 flex flex-col items-center justify-center cursor-pointer text-center">
              <Plus className="w-6 h-6 text-[#0F766E] mb-1" />
              <span className="font-bold text-sm text-[#1E293B]">＋ 予約を追加</span>
              <span className="text-xs text-[#64748B]">
                クリックして動画と出力先を指定（または動画ファイルをここへドロップ）
              </span>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
