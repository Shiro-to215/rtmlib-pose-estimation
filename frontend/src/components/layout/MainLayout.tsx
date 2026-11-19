import React from 'react';

export interface MainLayoutProps {
  header: React.ReactNode;
  banner?: React.ReactNode;
  children: React.ReactNode;
}

export const MainLayout: React.FC<MainLayoutProps> = ({
  header,
  banner,
  children,
}) => {
  return (
    <div className="h-screen w-screen overflow-hidden bg-[#ECEEEF] text-[#111111] font-sans p-4 flex flex-col gap-3 select-none">
      {header}
      {banner}
      <main className="flex-1 min-h-0 flex flex-col overflow-hidden">
        {children}
      </main>
    </div>
  );
};
