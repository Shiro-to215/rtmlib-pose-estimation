import React from 'react';

export const QueueGuideStrip: React.FC = () => {
  return (
    <div className="h-9 px-4 bg-[#F8FAFA] border-b border-[#D4DFDC] text-xs font-bold text-[#475569] grid grid-cols-[216px_108px_1fr] items-center flex-shrink-0 select-none">
      <div className="pl-3 text-left">順番 / プレビュー</div>
      <div className="text-center">設定</div>
      <div className="pl-3 text-left">動画名 / 出力フォルダー</div>
    </div>
  );
};
