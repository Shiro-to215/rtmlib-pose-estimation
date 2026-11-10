import React from 'react';

export interface MainLayoutProps {
  leftPane: React.ReactNode;
  rightPane: React.ReactNode;
}

export const MainLayout: React.FC<MainLayoutProps> = ({ leftPane, rightPane }) => {
  return (
    <div className="flex h-screen w-screen bg-[#F2F5F4] text-[#1E293B] font-sans overflow-hidden select-none p-3.5 gap-3.5">
      {/* Left Column (1 uniform unit = 25% width) */}
      <div className="w-1/4 h-full flex flex-col min-w-[280px] max-w-[380px] overflow-hidden flex-shrink-0">
        {leftPane}
      </div>

      {/* Right Column (3 uniform units = 75% width) */}
      <div className="flex-1 h-full flex flex-col min-w-0 overflow-hidden">
        {rightPane}
      </div>
    </div>
  );
};
