import React from 'react';
import { TopActionBar, TopActionBarProps } from './TopActionBar';

export interface RightWorkspaceShellProps extends TopActionBarProps {
  children: React.ReactNode;
}

export const RightWorkspaceShell: React.FC<RightWorkspaceShellProps> = ({
  children,
  isProcessing,
  isStopping,
  hasPendingJobs,
  bannerText,
  executionTarget,
  colabConfig,
  onChangeExecutionTarget,
  onOpenColabModal,
  onStopColabCli,
  onStart,
  onCancel,
}) => {
  return (
    <div className="flex-1 flex flex-col h-full min-w-0 overflow-hidden">
      {/* Top Action Bar */}
      <TopActionBar
        isProcessing={isProcessing}
        isStopping={isStopping}
        hasPendingJobs={hasPendingJobs}
        bannerText={bannerText}
        executionTarget={executionTarget}
        colabConfig={colabConfig}
        onChangeExecutionTarget={onChangeExecutionTarget}
        onOpenColabModal={onOpenColabModal}
        onStopColabCli={onStopColabCli}
        onStart={onStart}
        onCancel={onCancel}
      />

      {/* Switchable Workspace Container */}
      <div className="flex-1 bg-white rounded-xl border border-[#D4DFDC] flex flex-col shadow-sm overflow-hidden min-h-0">
        {children}
      </div>
    </div>
  );
};
