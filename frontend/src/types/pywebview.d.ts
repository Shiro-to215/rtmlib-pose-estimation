import { InitialDataPayload, JobSettings, ReservationJob } from './models';

/**
 * Strongly typed interface representing the Python BackendApi endpoints exposed via PyWebView
 */
export interface BackendApi {
  get_initial_data(): Promise<InitialDataPayload>;
  select_video_files(): Promise<string[]>;
  select_directory(title?: string): Promise<string | null>;
  select_image_file(title?: string): Promise<string | null>;
  add_reservations(
    videos: string[],
    outputFolder?: string | null,
    isMulti?: boolean,
    settings?: Partial<JobSettings>,
    thumbnail?: string | null
  ): Promise<ReservationJob[]>;
  remove_jobs(jobIds: string[]): Promise<ReservationJob[]>;
  move_job(jobId: string, direction: 'up' | 'down' | number): Promise<ReservationJob[]>;
  update_job_settings(
    jobId: string,
    settings: Partial<JobSettings>,
    resetFailed?: boolean,
    destination?: string
  ): Promise<ReservationJob>;
  retry_job(jobId: string): Promise<ReservationJob[]>;
  save_default_settings(
    settings: Partial<JobSettings>,
    defaultRoot?: string
  ): Promise<JobSettings>;
  start_queue_processing(): Promise<{ status: string; job_id?: string; message?: string }>;
  cancel_current_job(): Promise<{ status: string; job_id?: string }>;
  get_job_thumbnail(jobId: string): Promise<string>;
  get_preview_frame(videoPathOrJobId: string, frameIdxOrTime?: number): Promise<string>;
  validate_rtmlib_settings(
    poseModel: string,
    inputSize: string
  ): Promise<{ valid: boolean; error?: string; resolved?: Record<string, any> }>;
  get_output_preview_names(folderPath: string): Promise<Record<string, string>>;
}

declare global {
  interface Window {
    pywebview?: {
      api: BackendApi;
    };
    onJobProgress?: (jobId: string, progressPct: number, phase: string) => void;
    onJobLog?: (jobId: string, logLine: string) => void;
    onJobFinished?: (jobId: string, returnCode: number) => void;
    onJobStarted?: (jobId: string, videoName: string, outputPath: string) => void;
    onQueueStatusChanged?: (isActive: boolean, activeJobId: string | null) => void;
    onQueueUpdated?: (jobs: ReservationJob[]) => void;
    onJobThumbnail?: (jobId: string, dataUrl: string, info: string) => void;
  }
}

export {};
