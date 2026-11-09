/**
 * TypeScript declarations for PyWebView JavaScript bridge
 */
export interface BackendApi {
  get_initial_data(): Promise<{
    settings: Record<string, any>;
    queue: Array<any>;
    system: Record<string, any>;
  }>;
  select_video_files(): Promise<string[]>;
  select_directory(title?: string): Promise<string | null>;
  add_reservations(
    videos: string[],
    outputFolder: string,
    isMulti: boolean,
    settings: Record<string, any>
  ): Promise<any[]>;
  remove_jobs(jobIds: string[]): Promise<any[]>;
  move_job(jobId: string, direction: 'up' | 'down'): Promise<any[]>;
  update_job_settings(
    jobId: string,
    settings: Record<string, any>,
    resetFailed?: boolean
  ): Promise<any>;
  save_default_settings(settings: Record<string, any>): Promise<Record<string, any>>;
  start_queue_processing(): Promise<{ status: string }>;
  cancel_current_job(): Promise<{ status: string }>;
  retry_job(jobId: string): Promise<any[]>;
  get_job_thumbnail(jobId: string): Promise<string>;
  get_preview_frame(jobId: string): Promise<string>;
}

declare global {
  interface Window {
    pywebview?: {
      api: BackendApi;
    };
    onJobProgress?: (jobId: string, progressPct: number, phase: string) => void;
    onJobLog?: (jobId: string, logLine: string) => void;
    onJobFinished?: (jobId: string, returnCode: number) => void;
  }
}

export {};
