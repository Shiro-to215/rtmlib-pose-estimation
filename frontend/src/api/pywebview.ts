import {
  InitialDataPayload,
  JobSettings,
  ReservationJob,
} from '../types/models';
import { BackendApi } from '../types/pywebview';

/**
 * Returns true if the PyWebView native desktop bridge is available
 */
export function isPyWebViewHost(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.pywebview !== 'undefined' &&
    typeof window.pywebview.api !== 'undefined'
  );
}

/**
 * Waits for window.pywebview.api injection (`pywebviewready`) before falling back to browser mock
 */
export async function waitForBackendApi(timeoutMs = 1500): Promise<BackendApi> {
  if (isPyWebViewHost()) {
    return window.pywebview!.api;
  }
  if (typeof window === 'undefined') {
    return browserMockBackend;
  }

  return new Promise<BackendApi>((resolve) => {
    let settled = false;
    let pollTimer: number | undefined;
    let timeoutTimer: number | undefined;

    const cleanup = () => {
      window.removeEventListener('pywebviewready', onReady);
      if (pollTimer !== undefined) window.clearInterval(pollTimer);
      if (timeoutTimer !== undefined) window.clearTimeout(timeoutTimer);
    };

    const tryResolveReal = () => {
      if (!settled && isPyWebViewHost()) {
        settled = true;
        cleanup();
        resolve(window.pywebview!.api);
        return true;
      }
      return false;
    };

    const onReady = () => {
      tryResolveReal();
    };

    window.addEventListener('pywebviewready', onReady);
    pollTimer = window.setInterval(() => {
      tryResolveReal();
    }, 40);

    timeoutTimer = window.setTimeout(() => {
      if (!settled) {
        settled = true;
        cleanup();
        resolve(isPyWebViewHost() ? window.pywebview!.api : browserMockBackend);
      }
    }, timeoutMs);
  });
}

/**
 * Retrieves the native BackendApi or falls back to BrowserMockBackend for standalone dev
 */
export function getBackendApi(): BackendApi {
  if (isPyWebViewHost()) {
    return window.pywebview!.api;
  }
  return browserMockBackend;
}

/**
 * Helper to execute an API call with fallback on error
 */
export async function callApi<T>(fn: (api: BackendApi) => Promise<T>, fallback: T): Promise<T> {
  const api = getBackendApi();
  try {
    return await fn(api);
  } catch (err) {
    console.error('[PyWebView] Bridge call error:', err);
    return fallback;
  }
}

// ---------------------------------------------------------------------------
// Telemetry Subscription Listeners (Dual Event Delivery Support & Deduplication)
// ---------------------------------------------------------------------------

/**
 * Event deduplicator preventing duplicate callback execution when PyWebView pushes
 * telemetry via both DOM CustomEvent (`pywebview:job-*`) and global window callback (`window.on*`)
 * in the same event tick.
 */
export class EventDeduplicator {
  private recentKeys = new Map<string, number>();
  private windowMs: number;

  constructor(windowMs = 80) {
    this.windowMs = windowMs;
  }

  isDuplicate(key: string): boolean {
    const now = typeof performance !== 'undefined' && typeof performance.now === 'function'
      ? performance.now()
      : Date.now();

    // Prune expired entries
    for (const [k, t] of this.recentKeys.entries()) {
      if (now - t > this.windowMs) {
        this.recentKeys.delete(k);
      }
    }

    if (this.recentKeys.has(key)) {
      return true;
    }
    this.recentKeys.set(key, now);
    return false;
  }
}

export function subscribeToJobProgress(
  callback: (jobId: string, progress: number, phase: string) => void
): () => void {
  const dedup = new EventDeduplicator(80);
  const emit = (jobId: string, pct: number, phase: string) => {
    if (dedup.isDuplicate(`progress:${jobId}:${pct}:${phase}`)) return;
    callback(jobId, pct, phase);
  };
  const handler = (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail) {
      emit(detail.jobId, detail.progress, detail.phase);
    }
  };
  window.addEventListener('pywebview:job-progress', handler);
  const oldFn = window.onJobProgress;
  window.onJobProgress = (jobId, pct, phase) => {
    emit(jobId, pct, phase);
    if (oldFn) oldFn(jobId, pct, phase);
  };
  return () => {
    window.removeEventListener('pywebview:job-progress', handler);
    window.onJobProgress = oldFn;
  };
}

export function subscribeToJobLog(
  callback: (jobId: string, logLine: string) => void
): () => void {
  const dedup = new EventDeduplicator(80);
  const emit = (jobId: string, logLine: string) => {
    if (dedup.isDuplicate(`log:${jobId}:${logLine}`)) return;
    callback(jobId, logLine);
  };
  const handler = (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail) {
      emit(detail.jobId, detail.logLine);
    }
  };
  window.addEventListener('pywebview:job-log', handler);
  const oldFn = window.onJobLog;
  window.onJobLog = (jobId, line) => {
    emit(jobId, line);
    if (oldFn) oldFn(jobId, line);
  };
  return () => {
    window.removeEventListener('pywebview:job-log', handler);
    window.onJobLog = oldFn;
  };
}

export function subscribeToJobFinished(
  callback: (jobId: string, returnCode: number) => void
): () => void {
  const dedup = new EventDeduplicator(80);
  const emit = (jobId: string, returnCode: number) => {
    if (dedup.isDuplicate(`finished:${jobId}:${returnCode}`)) return;
    callback(jobId, returnCode);
  };
  const handler = (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail) {
      emit(detail.jobId, detail.returnCode);
    }
  };
  window.addEventListener('pywebview:job-finished', handler);
  const oldFn = window.onJobFinished;
  window.onJobFinished = (jobId, code) => {
    emit(jobId, code);
    if (oldFn) oldFn(jobId, code);
  };
  return () => {
    window.removeEventListener('pywebview:job-finished', handler);
    window.onJobFinished = oldFn;
  };
}

export function subscribeToJobStarted(
  callback: (jobId: string, videoName: string, outputPath: string) => void
): () => void {
  const dedup = new EventDeduplicator(80);
  const emit = (jobId: string, videoName: string, outputPath: string) => {
    if (dedup.isDuplicate(`started:${jobId}:${videoName}:${outputPath}`)) return;
    callback(jobId, videoName, outputPath);
  };
  const handler = (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail) {
      emit(detail.jobId, detail.videoName, detail.outputPath);
    }
  };
  window.addEventListener('pywebview:job-started', handler);
  const oldFn = window.onJobStarted;
  window.onJobStarted = (jobId, name, out) => {
    emit(jobId, name, out);
    if (oldFn) oldFn(jobId, name, out);
  };
  return () => {
    window.removeEventListener('pywebview:job-started', handler);
    window.onJobStarted = oldFn;
  };
}

export function subscribeToQueueUpdate(
  callback: (jobs: ReservationJob[], activeJobId?: string | null, queueActive?: boolean) => void
): () => void {
  const dedup = new EventDeduplicator(80);
  const emit = (
    jobs: ReservationJob[],
    activeJobId: string | null | undefined,
    queueActive: boolean | undefined,
    source: 'event' | 'legacy'
  ) => {
    const jobsSig = jobs?.map((j) => `${j.id}_${j.state}_${j.output_path}`).join(',') ?? '';
    const signature = `queue:${source}:${activeJobId ?? ''}:${queueActive ?? ''}:${jobs?.length ?? 0}:${jobsSig}`;
    if (dedup.isDuplicate(signature)) return;
    callback(jobs, activeJobId, queueActive);
  };
  const handler = (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail) {
      emit(detail.jobs, detail.active_job_id ?? null, detail.queue_active, 'event');
    }
  };
  window.addEventListener('pywebview:queue-update', handler);
  const oldFn = window.onQueueUpdated;
  window.onQueueUpdated = (jobs) => {
    // Legacy callback carries jobs only; avoid clobbering activeJobId/queueActive with null/false
    emit(jobs, undefined, undefined, 'legacy');
    if (oldFn) oldFn(jobs);
  };
  return () => {
    window.removeEventListener('pywebview:queue-update', handler);
    window.onQueueUpdated = oldFn;
  };
}

export function subscribeToFilesDropped(callback: (paths: string[]) => void): () => void {
  const dedup = new EventDeduplicator(120);
  const handler = (e: Event) => {
    const detail = (e as CustomEvent).detail;
    const paths: string[] = Array.isArray(detail?.paths) ? detail.paths : [];
    if (paths.length === 0) return;
    if (dedup.isDuplicate(`drop:${paths.join('|')}`)) return;
    callback(paths);
  };
  window.addEventListener('pywebview:files-dropped', handler);
  return () => {
    window.removeEventListener('pywebview:files-dropped', handler);
  };
}

export function subscribeToQueueStatus(
  callback: (isActive: boolean, activeJobId: string | null) => void
): () => void {
  const dedup = new EventDeduplicator(80);
  const emit = (isActive: boolean, activeJobId: string | null) => {
    if (dedup.isDuplicate(`status:${isActive}:${activeJobId}`)) return;
    callback(isActive, activeJobId);
  };
  const handler = (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail) {
      emit(detail.isActive, detail.activeJobId);
    }
  };
  window.addEventListener('pywebview:queue-status', handler);
  const oldFn = window.onQueueStatusChanged;
  window.onQueueStatusChanged = (isActive, activeJobId) => {
    emit(isActive, activeJobId);
    if (oldFn) oldFn(isActive, activeJobId);
  };
  return () => {
    window.removeEventListener('pywebview:queue-status', handler);
    window.onQueueStatusChanged = oldFn;
  };
}

export function subscribeToThumbnail(
  callback: (jobId: string, dataUrl: string, info: string) => void
): () => void {
  const dedup = new EventDeduplicator(80);
  const emit = (jobId: string, dataUrl: string, info: string) => {
    if (dedup.isDuplicate(`thumb:${jobId}:${info}:${dataUrl?.length ?? 0}`)) return;
    callback(jobId, dataUrl, info);
  };
  const handler = (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail) {
      emit(detail.job_id, detail.data_url, detail.info);
    }
  };
  window.addEventListener('pywebview:thumbnail', handler);
  const oldFn = window.onJobThumbnail;
  window.onJobThumbnail = (jobId, url, info) => {
    emit(jobId, url, info);
    if (oldFn) oldFn(jobId, url, info);
  };
  return () => {
    window.removeEventListener('pywebview:thumbnail', handler);
    window.onJobThumbnail = oldFn;
  };
}

// ---------------------------------------------------------------------------
// Standalone Browser Mock Backend Implementation (`npm run dev`)
// ---------------------------------------------------------------------------

class BrowserMockBackend implements BackendApi {
  private _jobs: ReservationJob[] = [
    {
      id: 'mock-job-001',
      state: 'pending',
      error: '',
      created_at: new Date().toISOString(),
      video_path: 'C:\\Videos\\sample_dance_01.mp4',
      video_name: 'sample_dance_01.mp4',
      output_path: 'C:\\Output\\sample_dance_01',
      output_folder: 'sample_dance_01',
      thumbnail: '',
      thumbnail_info: '1920×1080 px',
      settings: {
        INPUT_ROOT: 'C:\\Videos',
        INPUT_VIDEO_NAME: 'sample_dance_01.mp4',
        OUTPUT_ROOT: 'C:\\Output',
        OUTPUT_FOLDER_NAME: 'sample_dance_01',
        OUTPUT_VIDEO_NAME: 'sample_dance_01.mp4',
        OUTPUT_CROP_VIDEO_NAME: 'sample_dance_01-crop.mp4',
        OUTPUT_CROP_SKELETON_VIDEO_NAME: 'sample_dance_01-crop-skeleton.mp4',
        OUTPUT_CSV_NAME: 'sample_dance_01.csv',
        OUTPUT_METADATA_NAME: 'sample_dance_01_metadata.txt',
        DEVICE: 'auto',
        YOLO_MODEL: 'yolo11m.pt',
        YOLO_CLASSES: [0],
        YOLO_TRACK_ID: null,
        CSV_MAX_PERSONS: 3,
        RTMLIB_POSE_MODEL: 'x',
        RTMLIB_POSE_INPUT_SIZE: '384x288',
        YOLO_IMAGE_SIZE: 1280,
        YOLO_CONFIDENCE: 0.20,
        YOLO_IOU: 0.50,
        CROP_PADDING_RATIO: 0.25,
        KEYPOINT_THRESHOLD: 0.45,
        YOLO_TRACKER: 'bytetrack.yaml',
        TARGET_LOCK_RAW_ID: true,
        TARGET_REQUIRE_SAME_RAW_ID_WHEN_MISSING: true,
        TARGET_SELECTION_MIN_FRAMES: 15,
        TARGET_SELECTION_COVERAGE_WEIGHT: 0.50,
        TARGET_BOX_FILL_MAX_FRAMES: 60,
        TARGET_REACQUIRE_MAX_DISTANCE: 300.0,
        TARGET_REACQUIRE_MIN_IOU: 0.05,
        TARGET_TRACK_MATCH_THRESHOLD: 0.75,
        TARGET_TRACK_MIN_IOU: 0.15,
        TRACK_MAX_DISTANCE: 250.0,
        TRACK_MAX_MISSED_FRAMES: 8,
        TRACK_MATCH_THRESHOLD: 2.00,
        TRACK_CENTER_WEIGHT: 0.35,
        TRACK_KEYPOINT_WEIGHT: 0.35,
        TRACK_POSE_WEIGHT: 0.20,
        TRACK_BBOX_WEIGHT: 0.10,
        TRACK_VELOCITY_SMOOTHING: 0.35,
        TRACK_RAW_ID_BONUS: 2.00,
        TRACK_PREDICTED_BOX_WEIGHT: 0.35,
        TRACK_PREDICTION_MAX_FRAMES: 2,
        POSE_TRACK_KEYPOINT_WEIGHT: 0.65,
        POSE_TRACK_CENTER_WEIGHT: 0.25,
        POSE_TRACK_SHAPE_WEIGHT: 0.10,
        POSE_BOX_IOU_WEIGHT: 2.00,
        POSE_BOX_CENTER_WEIGHT: 0.50,
        POSE_TEMPORAL_WEIGHT: 0.50,
        DRAW_SKELETON: true,
        DRAW_BBOX: true,
        SKELETON_LINE_WIDTH: 2,
        KEYPOINT_RADIUS: 4,
        LABEL_FONT_SCALE: 0.70,
      },
      summary: {
        pose_model: 'x',
        pose_input_size: '384x288',
        yolo_model: 'yolo11m.pt',
        device: 'auto',
        track_id: null,
        csv_max_persons: 3,
      },
    },
    {
      id: 'mock-job-002',
      state: 'done',
      error: '',
      created_at: new Date(Date.now() - 3600000).toISOString(),
      video_path: 'C:\\Videos\\sample_sprint.mp4',
      video_name: 'sample_sprint.mp4',
      output_path: 'C:\\Output\\sample_sprint',
      output_folder: 'sample_sprint',
      thumbnail: '',
      thumbnail_info: '1280×720 px',
      settings: {
        INPUT_ROOT: 'C:\\Videos',
        INPUT_VIDEO_NAME: 'sample_sprint.mp4',
        OUTPUT_ROOT: 'C:\\Output',
        OUTPUT_FOLDER_NAME: 'sample_sprint',
        OUTPUT_VIDEO_NAME: 'sample_sprint.mp4',
        OUTPUT_CROP_VIDEO_NAME: 'sample_sprint-crop.mp4',
        OUTPUT_CROP_SKELETON_VIDEO_NAME: 'sample_sprint-crop-skeleton.mp4',
        OUTPUT_CSV_NAME: 'sample_sprint.csv',
        OUTPUT_METADATA_NAME: 'sample_sprint_metadata.txt',
        DEVICE: 'auto',
        YOLO_MODEL: 'yolo11s.pt',
        YOLO_CLASSES: [0],
        YOLO_TRACK_ID: 1,
        CSV_MAX_PERSONS: 1,
        RTMLIB_POSE_MODEL: 's',
        RTMLIB_POSE_INPUT_SIZE: '256x192',
      },
      summary: {
        pose_model: 's',
        pose_input_size: '256x192',
        yolo_model: 'yolo11s.pt',
        device: 'auto',
        track_id: 1,
        csv_max_persons: 1,
      },
    },
  ];

  private _isProcessing = false;
  private _simTimer: number | null = null;
  private _activeJobId: string | null = null;

  private _stripJobScopedKeys(settings: Partial<JobSettings>): Partial<JobSettings> {
    const blocked = new Set([
      'INPUT_ROOT',
      'INPUT_VIDEO_NAME',
      'THUMBNAIL_ROOT',
      'THUMBNAIL_IMAGE_NAME',
      'OUTPUT_FOLDER_NAME',
      'OUTPUT_VIDEO_NAME',
      'OUTPUT_CROP_VIDEO_NAME',
      'OUTPUT_CROP_SKELETON_VIDEO_NAME',
      'OUTPUT_CSV_NAME',
      'OUTPUT_METADATA_NAME',
    ]);
    const out: Record<string, any> = {};
    for (const [k, v] of Object.entries(settings || {})) {
      if (!blocked.has(k)) {
        out[k] = v;
      }
    }
    return out as Partial<JobSettings>;
  }

  async get_initial_data(): Promise<InitialDataPayload> {
    return {
      settings: this._stripJobScopedKeys(this._jobs[0].settings) as JobSettings,
      queue: [...this._jobs],
      system: {
        output_root: 'C:\\Output',
        is_processing: this._isProcessing,
        current_job_id: this._activeJobId,
        queue_active: this._isProcessing,
        active_job_id: this._activeJobId,
        choices: {
          YOLO_MODEL: ['yolo11n.pt', 'yolo11s.pt', 'yolo11m.pt', 'yolo11l.pt', 'yolo11x.pt'],
          DEVICE: ['auto', 'cpu', 'cuda'],
          RTMLIB_POSE_MODEL: ['t', 's', 'm', 'l', 'x'],
          RTMLIB_POSE_INPUT_SIZE: ['256x192', '384x288'],
          YOLO_TRACKER: ['bytetrack.yaml', 'botsort.yaml'],
          BACKEND: ['onnxruntime', 'opencv'],
        },
        labels: {
          YOLO_MODEL: 'YOLOモデル',
          DEVICE: '推論デバイス',
          RTMLIB_POSE_MODEL: 'RTMPoseモデル',
          RTMLIB_POSE_INPUT_SIZE: 'RTMPose入力解像度',
          YOLO_TRACKER: 'トラッカー設定',
          BACKEND: '推論バックエンド',
        },
        groups: [
          { title: '基本推論設定', keys: ['YOLO_MODEL', 'DEVICE'] },
        ],
      },
      choices: {
        YOLO_MODEL: ['yolo11n.pt', 'yolo11s.pt', 'yolo11m.pt', 'yolo11l.pt', 'yolo11x.pt'],
        DEVICE: ['auto', 'cpu', 'cuda'],
        RTMLIB_POSE_MODEL: ['t', 's', 'm', 'l', 'x'],
        RTMLIB_POSE_INPUT_SIZE: ['256x192', '384x288'],
        YOLO_TRACKER: ['bytetrack.yaml', 'botsort.yaml'],
        BACKEND: ['onnxruntime', 'opencv'],
      },
    };
  }

  async select_video_files(): Promise<string[]> {
    return ['C:\\Videos\\sample_video_simulated.mp4'];
  }

  async select_directory(_title?: string): Promise<string> {
    return 'C:\\Output\\CustomFolder';
  }

  async select_image_file(_title?: string): Promise<string | null> {
    return 'C:\\Videos\\thumbnail.jpg';
  }

  async add_reservations(
    videos: string[],
    outputFolder?: string | null,
    _isMulti?: boolean,
    settings?: Partial<JobSettings>,
    _thumbnail?: string | null
  ): Promise<ReservationJob[]> {
    const created: ReservationJob[] = videos.map((v, idx) => {
      const name = v.split('\\').pop() || v.split('/').pop() || `video_${Date.now()}_${idx}.mp4`;
      const stem = name.replace(/\.[^/.]+$/, '');
      const out = outputFolder ? `${outputFolder}\\${stem}` : `C:\\Output\\${stem}`;
      return {
        id: `mock-job-${Date.now()}-${idx}`,
        state: 'pending',
        error: '',
        created_at: new Date().toISOString(),
        video_path: v,
        video_name: name,
        output_path: out,
        output_folder: stem,
        thumbnail: '',
        thumbnail_info: '1920×1080 px',
        settings: {
          ...this._jobs[0].settings,
          ...settings,
          INPUT_VIDEO_NAME: name,
          OUTPUT_FOLDER_NAME: stem,
        },
        summary: {
          pose_model: settings?.RTMLIB_POSE_MODEL || 'x',
          pose_input_size: settings?.RTMLIB_POSE_INPUT_SIZE || '384x288',
          yolo_model: settings?.YOLO_MODEL || 'yolo11m.pt',
          device: settings?.DEVICE || 'auto',
          track_id: settings?.YOLO_TRACK_ID ?? null,
          csv_max_persons: settings?.CSV_MAX_PERSONS ?? 3,
        },
      };
    });
    this._jobs.push(...created);
    this._emitQueueUpdate();
    return created;
  }

  async remove_jobs(jobIds: string[]): Promise<ReservationJob[]> {
    this._jobs = this._jobs.filter((j) => !jobIds.includes(j.id) || j.state === 'running');
    this._emitQueueUpdate();
    return [...this._jobs];
  }

  async move_job(jobId: string, direction: 'up' | 'down' | number): Promise<ReservationJob[]> {
    const idx = this._jobs.findIndex((j) => j.id === jobId);
    if (idx === -1) return [...this._jobs];
    const delta = direction === 'up' || direction === -1 ? -1 : 1;
    const targetIdx = idx + delta;
    if (targetIdx >= 0 && targetIdx < this._jobs.length) {
      const temp = this._jobs[idx];
      this._jobs[idx] = this._jobs[targetIdx];
      this._jobs[targetIdx] = temp;
      this._emitQueueUpdate();
    }
    return [...this._jobs];
  }

  async update_job_settings(
    jobId: string,
    settings: Partial<JobSettings>,
    resetFailed?: boolean,
    destination?: string
  ): Promise<ReservationJob> {
    const job = this._jobs.find((j) => j.id === jobId);
    if (!job) throw new Error('Job not found');
    const safeSettings = { ...this._stripJobScopedKeys(settings) } as Record<string, any>;
    delete safeSettings.OUTPUT_ROOT;
    delete safeSettings.OUTPUT_DIRECTORY;
    if ('THUMBNAIL_ROOT' in settings) safeSettings.THUMBNAIL_ROOT = settings.THUMBNAIL_ROOT;
    if ('THUMBNAIL_IMAGE_NAME' in settings) safeSettings.THUMBNAIL_IMAGE_NAME = settings.THUMBNAIL_IMAGE_NAME;
    job.settings = { ...job.settings, ...safeSettings };
    if (destination) {
      job.output_path = destination;
      job.output_folder = destination.split('\\').pop() || destination.split('/').pop() || job.output_folder;
    }
    if (resetFailed && job.state === 'failed') {
      job.state = 'pending';
      job.error = '';
    }
    this._emitQueueUpdate();
    return { ...job };
  }

  async retry_job(jobId: string): Promise<ReservationJob[]> {
    const job = this._jobs.find((j) => j.id === jobId);
    if (job) {
      job.state = 'pending';
      job.error = '';
      this._emitQueueUpdate();
    }
    return [...this._jobs];
  }

  async save_default_settings(settings: Partial<JobSettings>, _defaultRoot?: string): Promise<JobSettings> {
    const clean = this._stripJobScopedKeys(settings);
    this._jobs[0].settings = { ...this._jobs[0].settings, ...clean };
    return this._stripJobScopedKeys(this._jobs[0].settings) as JobSettings;
  }

  async start_queue_processing(): Promise<{ status: string; job_id?: string }> {
    const pending = this._jobs.find((j) => j.state === 'pending');
    if (!pending) return { status: 'empty' };
    this._isProcessing = true;
    this._activeJobId = pending.id;
    pending.state = 'running';
    this._emitQueueUpdate();

    this._emitEvent('pywebview:job-started', {
      jobId: pending.id,
      videoName: pending.video_name,
      outputPath: pending.output_path,
    });
    this._emitLog(pending.id, `--- 解析開始: ${pending.video_name} ---\n`);

    let currentPct = 0;
    this._simTimer = window.setInterval(() => {
      if (!this._isProcessing) {
        if (this._simTimer) clearInterval(this._simTimer);
        return;
      }
      currentPct += 5;
      const phase = currentPct <= 50 ? 'YOLO' : 'RTMLIB';
      this._emitEvent('pywebview:job-progress', {
        jobId: pending.id,
        progress: currentPct,
        phase,
      });

      if (currentPct % 20 === 0) {
        this._emitLog(pending.id, `[Worker] ${phase} 進捗: ${currentPct}%\n`);
      }

      if (currentPct >= 100) {
        if (this._simTimer) clearInterval(this._simTimer);
        pending.state = 'done';
        this._emitLog(pending.id, `--- 解析完了: ${pending.video_name} ---\n`);
        this._emitEvent('pywebview:job-finished', { jobId: pending.id, returnCode: 0 });
        this._isProcessing = false;
        this._activeJobId = null;
        this._emitQueueUpdate();
      }
    }, 250);

    return { status: 'started', job_id: pending.id };
  }

  async cancel_current_job(): Promise<{ status: string; job_id?: string }> {
    if (!this._isProcessing || !this._activeJobId) return { status: 'idle' };
    const jid = this._activeJobId;
    if (this._simTimer) clearInterval(this._simTimer);
    const job = this._jobs.find((j) => j.id === jid);
    if (job) {
      job.state = 'pending';
    }
    this._isProcessing = false;
    this._activeJobId = null;
    this._emitLog(jid, `--- 解析中断: ${job?.video_name || ''} を待機リストに戻しました ---\n`);
    this._emitEvent('pywebview:job-progress', { jobId: jid, progress: 0, phase: 'STOPPING' });
    this._emitEvent('pywebview:job-finished', { jobId: jid, returnCode: -1 });
    this._emitQueueUpdate();
    return { status: 'stopping', job_id: jid };
  }

  async get_job_thumbnail(_jobId: string): Promise<string> {
    return '';
  }

  async get_preview_frame(_videoPathOrJobId: string): Promise<string> {
    return '';
  }

  async validate_rtmlib_settings(
    poseModel: string,
    inputSize: string
  ): Promise<{ valid: boolean; error?: string; resolved?: Record<string, any> }> {
    if (['t', 's', 'm'].includes(poseModel) && inputSize !== '256x192') {
      return { valid: false, error: `RTMPose-${poseModel.toUpperCase()} は ${inputSize} に対応していません。使用可能: 256x192` };
    }
    if (poseModel === 'x' && inputSize !== '384x288') {
      return { valid: false, error: `RTMPose-X は ${inputSize} に対応していません。使用可能: 384x288` };
    }
    return { valid: true };
  }

  async get_output_preview_names(folderPath: string): Promise<Record<string, string>> {
    const base = folderPath.split('\\').pop() || folderPath.split('/').pop() || 'output';
    return {
      OUTPUT_VIDEO_NAME: `${base}.mp4`,
      OUTPUT_CROP_VIDEO_NAME: `${base}-crop.mp4`,
      OUTPUT_CROP_SKELETON_VIDEO_NAME: `${base}-crop-skeleton.mp4`,
      OUTPUT_CSV_NAME: `${base}.csv`,
      OUTPUT_METADATA_NAME: `${base}_metadata.txt`,
    };
  }

  private _emitQueueUpdate(): void {
    this._emitEvent('pywebview:queue-update', {
      jobs: [...this._jobs],
      active_job_id: this._activeJobId,
      queue_active: this._isProcessing,
    });
  }

  private _emitLog(jobId: string, line: string): void {
    this._emitEvent('pywebview:job-log', { jobId, logLine: line });
  }

  private _emitEvent(name: string, detail: any): void {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  }
}

export const browserMockBackend = new BrowserMockBackend();
