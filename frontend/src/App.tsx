import React, { useEffect, useMemo, useState } from 'react';
import {
  InitialDataPayload,
  JobSettings,
  LogEntry,
  ReservationJob,
  RightViewType,
  SystemInfo,
} from './types/models';
import {
  getBackendApi,
  subscribeToJobFinished,
  subscribeToJobLog,
  subscribeToJobProgress,
  subscribeToJobStarted,
  subscribeToQueueStatus,
  subscribeToQueueUpdate,
  subscribeToThumbnail,
} from './api/pywebview';
import { MainLayout } from './components/layout/MainLayout';
import { RightWorkspaceShell } from './components/layout/RightWorkspaceShell';
import { LeftMonitorPane } from './components/left_monitor/LeftMonitorPane';
import { QueueListView } from './components/queue/QueueListView';
import { AddReservationView } from './components/add_reservation/AddReservationView';
import { SettingsView } from './components/settings/SettingsView';

export const App: React.FC = () => {
  // Global Application State
  const [queue, setQueue] = useState<ReservationJob[]>([]);
  const [defaultSettings, setDefaultSettings] = useState<Partial<JobSettings>>({});
  const [systemInfo, setSystemInfo] = useState<SystemInfo>({
    output_root: '',
    is_processing: false,
    current_job_id: null,
    queue_active: false,
    active_job_id: null,
    choices: {},
    labels: {},
    groups: [],
  });

  // Processing & Telemetry State
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [isStopping, setIsStopping] = useState<boolean>(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [progressPercent, setProgressPercent] = useState<number>(0);
  const [phaseCode, setPhaseCode] = useState<string>('IDLE');
  const [logs, setLogs] = useState<LogEntry[]>([]);

  // Right Pane View State
  const [activeView, setActiveView] = useState<RightViewType>('queue');
  const [selectedJobForSettings, setSelectedJobForSettings] = useState<ReservationJob | null>(null);
  const [addInitialVideos, setAddInitialVideos] = useState<string[]>([]);

  // Initial Data Fetch
  useEffect(() => {
    const api = getBackendApi();
    api.get_initial_data().then((payload: InitialDataPayload) => {
      if (payload) {
        setQueue(payload.queue || []);
        setDefaultSettings(payload.settings || {});
        if (payload.system) {
          setSystemInfo(payload.system);
          setIsProcessing(Boolean(payload.system.is_processing || payload.system.queue_active));
          setActiveJobId(payload.system.current_job_id || payload.system.active_job_id || null);
        }
      }
    });
  }, []);

  // Telemetry Subscriptions (Dual Event Delivery)
  useEffect(() => {
    const unsubProgress = subscribeToJobProgress((jobId, progress, phase) => {
      setActiveJobId(jobId);
      setProgressPercent(progress);
      setPhaseCode(phase);
    });

    const unsubLog = subscribeToJobLog((jobId, logLine) => {
      const isHeading = logLine.trim().startsWith('---');
      const isError = /error|エラー|失敗|traceback/i.test(logLine);
      const isSystem = logLine.trim().startsWith('[');

      const newEntry: LogEntry = {
        id: `log-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
        jobId,
        text: logLine,
        tag: isHeading ? 'heading' : isError ? 'error' : isSystem ? 'system' : 'default',
        timestamp: new Date().toLocaleTimeString(),
      };

      setLogs((prev) => {
        const next = [...prev, newEntry];
        return next.length > 1000 ? next.slice(-1000) : next;
      });
    });

    const unsubStarted = subscribeToJobStarted((jobId) => {
      setIsProcessing(true);
      setIsStopping(false);
      setActiveJobId(jobId);
      setProgressPercent(0);
      setPhaseCode('STARTING');
    });

    const unsubFinished = subscribeToJobFinished((_jobId, returnCode) => {
      if (returnCode === 0) {
        setProgressPercent(100);
        setPhaseCode('DONE');
      } else {
        setPhaseCode('IDLE');
      }
    });

    const unsubQueueUpdate = subscribeToQueueUpdate((jobs, activeId, queueActive) => {
      setQueue(jobs);
      if (activeId !== null && activeId !== undefined) {
        setActiveJobId(activeId);
      }
      if (queueActive !== undefined) {
        setIsProcessing(queueActive);
        if (!queueActive) {
          setIsStopping(false);
        }
      }
    });

    const unsubQueueStatus = subscribeToQueueStatus((isActive, activeId) => {
      setIsProcessing(isActive);
      setActiveJobId(activeId);
      if (!isActive) {
        setIsStopping(false);
      }
    });

    const unsubThumbnail = subscribeToThumbnail((jobId, dataUrl, info) => {
      setQueue((prev) =>
        prev.map((j) => (j.id === jobId ? { ...j, thumbnail: dataUrl, thumbnail_info: info } : j))
      );
    });

    return () => {
      unsubProgress();
      unsubLog();
      unsubStarted();
      unsubFinished();
      unsubQueueUpdate();
      unsubQueueStatus();
      unsubThumbnail();
    };
  }, []);

  // Compute Active Job (the running job or currently tracked job)
  const activeJob = useMemo(() => {
    if (activeJobId) {
      const match = queue.find((j) => j.id === activeJobId);
      if (match) return match;
    }
    const running = queue.find((j) => j.state === 'running');
    if (running) return running;
    return null;
  }, [queue, activeJobId]);

  // Compute Top Action Bar Banner Text
  const hasPendingJobs = useMemo(() => {
    return queue.some((j) => j.state === 'pending');
  }, [queue]);

  const bannerText = useMemo(() => {
    if (isStopping) {
      return '解析を中断しています。現在の動画を待機リストの先頭へ戻します…';
    }
    if (isProcessing && activeJob) {
      return `解析実行中: ${activeJob.video_name} (${phaseCode} ${Math.round(progressPercent)}%)`;
    }
    return '待機中の予約を上から順番に解析します。';
  }, [isStopping, isProcessing, activeJob, phaseCode, progressPercent]);

  // Top Bar Actions
  const handleStartAnalysis = async () => {
    const api = getBackendApi();
    try {
      const res = await api.start_queue_processing();
      if (res && res.status === 'started') {
        setIsProcessing(true);
        setIsStopping(false);
      }
    } catch (err) {
      console.error('Failed to start analysis queue:', err);
    }
  };

  const handleCancelAnalysis = async () => {
    const api = getBackendApi();
    setIsStopping(true);
    try {
      await api.cancel_current_job();
    } catch (err) {
      console.error('Failed to cancel analysis job:', err);
      setIsStopping(false);
    }
  };

  // Queue Operations
  const handleDeleteJobs = async (jobIds: string[]) => {
    const api = getBackendApi();
    try {
      const remaining = await api.remove_jobs(jobIds);
      setQueue(remaining);
    } catch (err) {
      console.error('Failed to remove jobs:', err);
    }
  };

  const handleMoveJob = async (jobId: string, direction: 'up' | 'down') => {
    const api = getBackendApi();
    try {
      const updated = await api.move_job(jobId, direction);
      setQueue(updated);
    } catch (err) {
      console.error('Failed to move job:', err);
    }
  };

  const handleRetryJob = async (jobId: string) => {
    const api = getBackendApi();
    try {
      const updated = await api.retry_job(jobId);
      setQueue(updated);
    } catch (err) {
      console.error('Failed to retry job:', err);
    }
  };

  // Navigation Handlers
  const handleOpenAddReservation = (initialVideos?: string[]) => {
    setAddInitialVideos(initialVideos || []);
    setActiveView('add');
  };

  const handleOpenBasicSettings = () => {
    setSelectedJobForSettings(null);
    setActiveView('basic_settings');
  };

  const handleOpenJobSettings = (jobId: string) => {
    const found = queue.find((j) => j.id === jobId);
    if (found) {
      setSelectedJobForSettings(found);
      setActiveView('job_settings');
    }
  };

  // Add Reservation Submit Handler
  const handleAddReservationSubmit = async (
    videos: string[],
    outputFolder: string,
    isMulti: boolean,
    thumbnail?: string | null
  ): Promise<boolean> => {
    const api = getBackendApi();
    try {
      const created = await api.add_reservations(
        videos,
        outputFolder,
        isMulti,
        defaultSettings,
        thumbnail
      );
      if (created && created.length > 0) {
        setQueue((prev) => [...prev, ...created]);
        setActiveView('queue');
        return true;
      }
      return false;
    } catch (err) {
      console.error('Failed to add reservations:', err);
      return false;
    }
  };

  // Save Settings Handlers
  const handleSaveDefaultSettings = async (
    settings: Partial<JobSettings>,
    defaultRoot: string
  ): Promise<boolean> => {
    const api = getBackendApi();
    try {
      const saved = await api.save_default_settings(settings, defaultRoot);
      setDefaultSettings(saved);
      setSystemInfo((prev) => ({ ...prev, output_root: defaultRoot }));
      return true;
    } catch (err) {
      console.error('Failed to save default settings:', err);
      return false;
    }
  };

  const handleSaveJobSettings = async (
    jobId: string,
    settings: Partial<JobSettings>,
    resetFailed: boolean,
    destination?: string
  ): Promise<boolean> => {
    const api = getBackendApi();
    try {
      const updated = await api.update_job_settings(jobId, settings, resetFailed, destination);
      if (updated) {
        setQueue((prev) => prev.map((j) => (j.id === jobId ? updated : j)));
        return true;
      }
      return false;
    } catch (err) {
      console.error('Failed to update job settings:', err);
      return false;
    }
  };

  // Left Pane Component (Always Visible, 25% Width)
  const leftPane = (
    <LeftMonitorPane
      activeJob={activeJob}
      progressPercent={progressPercent}
      phaseCode={phaseCode}
      isProcessing={isProcessing}
      isStopping={isStopping}
      logs={logs}
      onClearLogs={() => setLogs([])}
    />
  );

  // Right Pane Switchable View Content (75% Width)
  const renderRightViewContent = () => {
    switch (activeView) {
      case 'add':
        return (
          <AddReservationView
            initialVideos={addInitialVideos}
            defaultOutputRoot={systemInfo.output_root}
            defaultSettings={defaultSettings}
            onCancel={() => setActiveView('queue')}
            onSubmit={handleAddReservationSubmit}
            onOpenBasicSettings={handleOpenBasicSettings}
          />
        );
      case 'basic_settings':
        return (
          <SettingsView
            mode="default"
            defaultSettings={defaultSettings}
            systemInfo={systemInfo}
            onBack={() => setActiveView('queue')}
            onSaveDefault={handleSaveDefaultSettings}
            onSaveJob={handleSaveJobSettings}
          />
        );
      case 'job_settings':
        if (!selectedJobForSettings) return null;
        return (
          <SettingsView
            mode="job"
            job={selectedJobForSettings}
            defaultSettings={defaultSettings}
            systemInfo={systemInfo}
            onBack={() => setActiveView('queue')}
            onSaveDefault={handleSaveDefaultSettings}
            onSaveJob={handleSaveJobSettings}
          />
        );
      case 'queue':
      default:
        return (
          <QueueListView
            jobs={queue}
            onOpenAddReservation={handleOpenAddReservation}
            onOpenBasicSettings={handleOpenBasicSettings}
            onOpenJobSettings={handleOpenJobSettings}
            onDeleteJobs={handleDeleteJobs}
            onMoveJob={handleMoveJob}
            onRetryJob={handleRetryJob}
          />
        );
    }
  };

  // Right Workspace Shell wrapping TopActionBar and Active Workspace View
  const rightPane = (
    <RightWorkspaceShell
      isProcessing={isProcessing}
      isStopping={isStopping}
      hasPendingJobs={hasPendingJobs}
      bannerText={bannerText}
      onStart={handleStartAnalysis}
      onCancel={handleCancelAnalysis}
    >
      {renderRightViewContent()}
    </RightWorkspaceShell>
  );

  return <MainLayout leftPane={leftPane} rightPane={rightPane} />;
};
export default App;
