import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ColabCliStatus,
  ColabConfig,
  ColabHealthInfo,
  ExecutionTarget,
  InitialDataPayload,
  JobSettings,
  LogEntry,
  PoseEngineType,
  ReservationJob,
  RightViewType,
  SystemInfo,
} from './types/models';
import {
  getBackendApi,
  isPyWebViewHost,
  subscribeToFilesDropped,
  subscribeToJobFinished,
  subscribeToJobLog,
  subscribeToJobProgress,
  subscribeToJobStarted,
  subscribeToQueueStatus,
  subscribeToQueueUpdate,
  subscribeToThumbnail,
  waitForBackendApi,
} from './api/pywebview';
import { MainLayout } from './components/layout/MainLayout';
import { TopHeader } from './components/layout/TopHeader';
import { StatusSummaryStrip } from './components/dashboard/StatusSummaryStrip';
import { VideoPreviewCanvas } from './components/left_monitor/VideoPreviewCanvas';
import { ExecutionLogBox } from './components/left_monitor/ExecutionLogBox';
import { QueueListView } from './components/queue/QueueListView';
import { AddReservationView } from './components/add_reservation/AddReservationView';
import { SettingsView } from './components/settings/SettingsView';
import { ColabConnectionModal } from './components/colab/ColabConnectionModal';

const DEFAULT_COLAB_CONFIG: ColabConfig = {
  execution_target: 'local',
  colab_mode: 'cli_ssh',
  server_url: '',
  api_token: '',
  remember_token: false,
  cli_gpu: 'T4',
  cli_high_mem: false,
  cli_use_drive_cache: false,
  cli_idle_timeout_minutes: 30,
  last_health: null,
  cli_status: null,
};

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
  const activeJobIdRef = useRef<string | null>(null);
  useEffect(() => {
    activeJobIdRef.current = activeJobId;
  }, [activeJobId]);
  const [progressPercent, setProgressPercent] = useState<number>(0);
  const [phaseCode, setPhaseCode] = useState<string>('IDLE');
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [selectedQueueIds, setSelectedQueueIds] = useState<string[]>([]);

  // Colab Remote Execution State
  const [colabConfig, setColabConfig] = useState<ColabConfig>(DEFAULT_COLAB_CONFIG);
  const [isColabModalOpen, setIsColabModalOpen] = useState<boolean>(false);

  // Poll pure in-memory Colab CLI status for header badge (does not extend idle timer)
  useEffect(() => {
    const mode = colabConfig.colab_mode || 'cli_ssh';
    if (colabConfig.execution_target !== 'colab' || mode !== 'cli_ssh') {
      return;
    }
    let cancelled = false;
    const refreshStatus = () => {
      getBackendApi()
        .get_colab_cli_status()
        .then((cliStatus) => {
          if (!cancelled && cliStatus) {
            setColabConfig((prev) => ({
              ...prev,
              cli_status: cliStatus,
              last_health: cliStatus.last_health ?? prev.last_health,
            }));
          }
        })
        .catch(() => {});
    };
    refreshStatus();
    const timer = window.setInterval(refreshStatus, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [colabConfig.execution_target, colabConfig.colab_mode, isProcessing]);

  // Workspace View State
  const [activeView, setActiveView] = useState<RightViewType>('queue');
  const activeViewRef = useRef<RightViewType>('queue');
  useEffect(() => {
    activeViewRef.current = activeView;
  }, [activeView]);
  const [selectedJobIdForSettings, setSelectedJobIdForSettings] = useState<string | null>(null);
  const selectedJobForSettings = useMemo(
    () => (selectedJobIdForSettings ? queue.find((j) => j.id === selectedJobIdForSettings) || null : null),
    [queue, selectedJobIdForSettings]
  );
  const [addInitialVideos, setAddInitialVideos] = useState<string[]>([]);

  // Initial Data Fetch (waits for pywebviewready before falling back to dev mock)
  useEffect(() => {
    let cancelled = false;
    const applyInitialPayload = (payload: InitialDataPayload) => {
      if (cancelled || !payload) return;
      setQueue(payload.queue || []);
      setDefaultSettings(payload.settings || {});
      if (payload.system) {
        setSystemInfo(payload.system);
        setIsProcessing(Boolean(payload.system.is_processing || payload.system.queue_active));
        setActiveJobId(payload.system.current_job_id || payload.system.active_job_id || null);
        if (payload.system.colab) {
          setColabConfig({ ...DEFAULT_COLAB_CONFIG, ...payload.system.colab });
        }
      }
    };

    waitForBackendApi().then((api) => {
      api.get_initial_data().then(applyInitialPayload).catch((err) => {
        console.error('Failed to fetch initial data:', err);
        setBannerError('初期データの読み込みに失敗しました。');
      });
    });

    const handleLateBridgeReady = () => {
      if (isPyWebViewHost()) {
        getBackendApi().get_initial_data().then(applyInitialPayload).catch((err) => {
          console.error('Failed to refresh initial data on pywebviewready:', err);
          setBannerError('初期データの再読み込みに失敗しました。');
        });
      }
    };
    window.addEventListener('pywebviewready', handleLateBridgeReady);

    return () => {
      cancelled = true;
      window.removeEventListener('pywebviewready', handleLateBridgeReady);
    };
  }, []);

  // Prevent browser navigation on external file drop and route native drops cleanly
  useEffect(() => {
    const preventNav = (e: DragEvent) => {
      e.preventDefault();
    };
    window.addEventListener('dragover', preventNav);
    window.addEventListener('drop', preventNav);

    const unsubDropped = subscribeToFilesDropped((paths) => {
      if (!paths || paths.length === 0) return;
      const curr = activeViewRef.current;
      if (curr !== 'queue' && curr !== 'add') return;
      setAddInitialVideos((prev) =>
        curr === 'add' ? Array.from(new Set([...prev, ...paths])) : paths
      );
      setActiveView('add');
    });

    return () => {
      window.removeEventListener('dragover', preventNav);
      window.removeEventListener('drop', preventNav);
      unsubDropped();
    };
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

    const unsubFinished = subscribeToJobFinished((finishedJobId, returnCode) => {
      if (activeJobIdRef.current && finishedJobId && finishedJobId !== activeJobIdRef.current) {
        return;
      }
      if (returnCode === 0) {
        setProgressPercent(100);
        setPhaseCode('DONE');
      } else {
        setProgressPercent(0);
        setPhaseCode('IDLE');
      }
    });

    const unsubQueueUpdate = subscribeToQueueUpdate((jobs, activeId, queueActive) => {
      setQueue(jobs);
      if (activeId !== undefined) {
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

  const inspectedJob = useMemo(() => {
    if (selectedQueueIds.length !== 1) return null;
    return queue.find((j) => j.id === selectedQueueIds[0]) || null;
  }, [queue, selectedQueueIds]);

  const pendingCount = useMemo(
    () => queue.filter((j) => j.state === 'pending').length,
    [queue]
  );
  const doneCount = useMemo(
    () => queue.filter((j) => j.state === 'done').length,
    [queue]
  );
  const failedCount = useMemo(
    () => queue.filter((j) => j.state === 'failed').length,
    [queue]
  );
  const hasPendingJobs = pendingCount > 0;

  // Colab Config & Connection Handlers
  const handleChangeExecutionTarget = async (target: ExecutionTarget) => {
    if (isProcessing || target === colabConfig.execution_target) return;
    const api = getBackendApi();
    setBannerError(null);
    try {
      const res = await api.save_colab_config({ execution_target: target });
      if (res && res.status === 'ok' && res.config) {
        setColabConfig({ ...DEFAULT_COLAB_CONFIG, ...res.config });
        if (target === 'colab') {
          const mode = res.config.colab_mode || 'cli_ssh';
          if (mode === 'manual' && !(res.config.server_url || '').trim()) {
            setIsColabModalOpen(true);
          } else if (mode === 'cli_ssh') {
            api
              .check_colab_cli_prereqs()
              .then((prereqs) => {
                if (prereqs && !prereqs.ok) {
                  setIsColabModalOpen(true);
                }
              })
              .catch(() => {});
          }
        }
      } else if (res?.message) {
        setBannerError(res.message);
      }
    } catch (err) {
      console.error('Failed to change execution target:', err);
      setBannerError('実行先の切り替えに失敗しました。');
    }
  };

  const handleSaveColabConfig = async (
    nextConfig: Partial<ColabConfig>
  ): Promise<{ status: string; config?: ColabConfig; message?: string }> => {
    const api = getBackendApi();
    const res = await api.save_colab_config(nextConfig);
    if (res && res.status === 'ok' && res.config) {
      setColabConfig({ ...DEFAULT_COLAB_CONFIG, ...res.config });
      setBannerError(null);
    }
    return res;
  };

  const handleTestColabConnection = async (
    serverUrl: string,
    apiToken: string
  ): Promise<{ ok: boolean; health?: ColabHealthInfo; error?: string }> => {
    const api = getBackendApi();
    const res = await api.test_colab_connection(serverUrl, apiToken);
    if (res.ok && res.health) {
      setColabConfig((prev) => ({ ...prev, last_health: res.health }));
    }
    return res;
  };

  const handleCliStatusUpdate = (cliStatus: ColabCliStatus) => {
    setColabConfig((prev) => ({
      ...prev,
      cli_status: cliStatus,
      last_health: cliStatus.last_health ?? (cliStatus.state === 'stopped' ? null : prev.last_health),
    }));
  };

  const handleStopColabCli = async () => {
    if (isProcessing) return;
    const api = getBackendApi();
    try {
      const res = await api.stop_colab_cli();
      if (res?.cli_status) {
        handleCliStatusUpdate(res.cli_status);
      }
      if (!res?.ok && res?.error) {
        setBannerError(res.error);
      }
    } catch (err) {
      console.error('Failed to stop Colab CLI runtime:', err);
      setBannerError('Colab ランタイムの停止に失敗しました。');
    }
  };

  // Top Header Start / Cancel Actions
  const handleStartAnalysis = async () => {
    const mode = colabConfig.colab_mode || 'cli_ssh';
    if (
      colabConfig.execution_target === 'colab' &&
      mode === 'manual' &&
      (!colabConfig.server_url.trim() || !colabConfig.api_token.trim())
    ) {
      setBannerError('Google Colab のサーバー URL と API トークンを設定してから解析を開始してください。');
      setIsColabModalOpen(true);
      return;
    }
    const api = getBackendApi();
    setBannerError(null);
    try {
      const res = await api.start_queue_processing();
      if (res && res.status === 'started') {
        setIsProcessing(true);
        setIsStopping(false);
      } else if (res && res.status === 'error') {
        setBannerError(res.message || '解析の開始に失敗しました。');
        if (res.code === 'prereq_missing') {
          setIsColabModalOpen(true);
        }
      }
    } catch (err) {
      console.error('Failed to start analysis queue:', err);
      setBannerError('解析の開始中にエラーが発生しました。');
    }
  };

  const handleCancelAnalysis = async () => {
    const api = getBackendApi();
    setBannerError(null);
    setIsStopping(true);
    try {
      await api.cancel_current_job();
    } catch (err) {
      console.error('Failed to cancel analysis job:', err);
      setIsStopping(false);
      setBannerError('解析の中断要求に失敗しました。');
    }
  };

  // Queue Operations
  const handleDeleteJobs = async (jobIds: string[]) => {
    const api = getBackendApi();
    setBannerError(null);
    try {
      const remaining = await api.remove_jobs(jobIds);
      setQueue(remaining);
    } catch (err) {
      console.error('Failed to remove jobs:', err);
      setBannerError('予約の削除に失敗しました。');
    }
  };

  const handleMoveJob = async (jobId: string, direction: 'up' | 'down') => {
    const api = getBackendApi();
    setBannerError(null);
    try {
      const updated = await api.move_job(jobId, direction);
      setQueue(updated);
    } catch (err) {
      console.error('Failed to move job:', err);
      setBannerError('予約の並び替えに失敗しました。');
    }
  };

  const handleReorderJob = async (jobId: string, targetVisibleIndex: number) => {
    const api = getBackendApi();
    setBannerError(null);
    try {
      const updated = await api.reorder_job(jobId, targetVisibleIndex);
      setQueue(updated);
    } catch (err) {
      console.error('Failed to reorder job:', err);
      setBannerError('ドラッグ＆ドロップでの並び替えに失敗しました。');
    }
  };

  const handleRetryJob = async (jobId: string) => {
    const api = getBackendApi();
    setBannerError(null);
    try {
      const updated = await api.retry_job(jobId);
      setQueue(updated);
    } catch (err) {
      console.error('Failed to retry job:', err);
      setBannerError('再試行の登録に失敗しました。');
    }
  };

  // Navigation Handlers
  const handleOpenAddReservation = (initialVideos?: string[]) => {
    setAddInitialVideos(initialVideos || []);
    setActiveView('add');
  };

  const handleOpenBasicSettings = () => {
    setSelectedJobIdForSettings(null);
    setActiveView('basic_settings');
  };

  const handleOpenJobSettings = (jobId: string) => {
    const found = queue.find((j) => j.id === jobId);
    if (found) {
      setSelectedJobIdForSettings(jobId);
      setActiveView('job_settings');
    }
  };

  // Add Reservation Submit Handler
  const handleAddReservationSubmit = async (
    videos: string[],
    outputFolder: string,
    isMulti: boolean
  ): Promise<boolean> => {
    const api = getBackendApi();
    setBannerError(null);
    try {
      const created = await api.add_reservations(
        videos,
        outputFolder,
        isMulti,
        defaultSettings
      );
      if (created && created.length > 0) {
        setActiveView('queue');
        return true;
      }
      setBannerError('予約を追加できませんでした。');
      return false;
    } catch (err) {
      console.error('Failed to add reservations:', err);
      setBannerError('予約の追加に失敗しました。');
      return false;
    }
  };

  // Save Settings Handlers
  const handleSaveDefaultSettings = async (
    settings: Partial<JobSettings>,
    defaultRoot: string
  ): Promise<boolean> => {
    const api = getBackendApi();
    setBannerError(null);
    try {
      const saved = await api.save_default_settings(settings, defaultRoot);
      setDefaultSettings(saved);
      setSystemInfo((prev) => ({ ...prev, output_root: defaultRoot }));
      return true;
    } catch (err) {
      console.error('Failed to save default settings:', err);
      setBannerError('基本設定の保存に失敗しました。');
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
    setBannerError(null);
    try {
      const updated = await api.update_job_settings(jobId, settings, resetFailed, destination);
      if (updated) {
        setQueue((prev) => prev.map((j) => (j.id === jobId ? updated : j)));
        return true;
      }
      setBannerError('予約設定の更新に失敗しました。');
      return false;
    } catch (err) {
      console.error('Failed to update job settings:', err);
      setBannerError('予約設定の更新に失敗しました。');
      return false;
    }
  };

  const handleSelectDefaultPoseEngine = async (nextEngine: PoseEngineType) => {
    const currentEngine =
      String(defaultSettings.POSE_ENGINE || 'rtmpose').toLowerCase() === 'vitpose'
        ? 'vitpose'
        : 'rtmpose';
    if (nextEngine === currentEngine) return;
    await handleSaveDefaultSettings(
      { ...defaultSettings, POSE_ENGINE: nextEngine },
      systemInfo.output_root || ''
    );
  };

  const headerNode = (
    <TopHeader
      activeView={activeView}
      isProcessing={isProcessing}
      isStopping={isStopping}
      hasPendingJobs={hasPendingJobs}
      executionTarget={colabConfig.execution_target}
      colabConfig={colabConfig}
      onNavigateQueue={() => setActiveView('queue')}
      onNavigateAdd={() => handleOpenAddReservation()}
      onNavigateBasicSettings={handleOpenBasicSettings}
      onChangeExecutionTarget={handleChangeExecutionTarget}
      onOpenColabModal={() => setIsColabModalOpen(true)}
      onStopColabCli={handleStopColabCli}
      onStart={handleStartAnalysis}
      onCancel={handleCancelAnalysis}
    />
  );

  const bannerNode = bannerError ? (
    <div className="px-4 py-2 bg-[#FEE2E2] border border-black/[0.06] rounded-[10px] flex items-center justify-between text-xs text-[#B91C1C] flex-shrink-0">
      <span>{bannerError}</span>
      <button
        type="button"
        onClick={() => setBannerError(null)}
        className="ml-3 font-semibold text-[#B91C1C] hover:underline cursor-pointer"
      >
        閉じる
      </button>
    </div>
  ) : null;

  const renderSubView = () => {
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
      default:
        return null;
    }
  };

  return (
    <>
      <MainLayout header={headerNode} banner={bannerNode}>
        <div
          key={activeView}
          className="flex-1 min-h-0 flex flex-col overflow-hidden view-fade-in"
        >
          {activeView === 'queue' ? (
            <div className="flex-1 min-h-0 grid grid-cols-12 gap-3">
              {/* Left Pane (8 cols): Compact Status/Progress Strip + Scrollable Queue Card */}
              <div className="col-span-8 min-h-0 flex flex-col gap-3">
                <StatusSummaryStrip
                  pendingCount={pendingCount}
                  doneCount={doneCount}
                  failedCount={failedCount}
                  isProcessing={isProcessing}
                  isStopping={isStopping}
                  progressPercent={progressPercent}
                  phaseCode={phaseCode}
                  activeJob={activeJob}
                  inspectedJob={inspectedJob}
                  defaultSettings={defaultSettings}
                  onTogglePoseEngine={handleSelectDefaultPoseEngine}
                  onOpenJobSettings={handleOpenJobSettings}
                />

                <section className="flex-1 min-h-0 bg-white rounded-[14px] flex flex-col overflow-hidden">
                  <QueueListView
                    jobs={queue}
                    onOpenAddReservation={handleOpenAddReservation}
                    onOpenJobSettings={handleOpenJobSettings}
                    onDeleteJobs={handleDeleteJobs}
                    onMoveJob={handleMoveJob}
                    onReorderJob={handleReorderJob}
                    onRetryJob={handleRetryJob}
                    onSelectionChange={setSelectedQueueIds}
                  />
                </section>
              </div>

              {/* Right Pane (4 cols): 16:9 Live Preview Card + Dark #111111 Execution Log Card */}
              <div className="col-span-4 min-h-0 flex flex-col gap-3">
                <VideoPreviewCanvas
                  imageSrc={activeJob?.thumbnail}
                  videoTitle={activeJob?.video_name}
                  metaText={activeJob ? `出力: ${activeJob.output_folder}` : ''}
                  resolutionInfo={activeJob?.thumbnail_info}
                  isIdle={!isProcessing || !activeJob}
                />

                <ExecutionLogBox logs={logs} onClear={() => setLogs([])} />
              </div>
            </div>
          ) : (
            renderSubView()
          )}
        </div>
      </MainLayout>

      <ColabConnectionModal
        isOpen={isColabModalOpen}
        config={colabConfig}
        isProcessing={isProcessing}
        onClose={() => setIsColabModalOpen(false)}
        onTestConnection={handleTestColabConnection}
        onSave={handleSaveColabConfig}
        onCliStatusChange={handleCliStatusUpdate}
      />
    </>
  );
};
export default App;
