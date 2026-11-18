export type JobState = 'pending' | 'running' | 'done' | 'failed';

export type PhaseCode = 'IDLE' | 'STARTING' | 'YOLO' | 'RTMPose' | 'RTMLIB' | 'VITPOSE' | 'STOPPING' | 'DONE';

export type PoseEngineType = 'rtmpose' | 'vitpose';

export type ExecutionTarget = 'local' | 'colab';
export type ColabMode = 'cli_ssh' | 'manual';
export type ColabGpuType = 'T4' | 'L4' | 'A100' | 'G4' | 'H100';

export interface ColabHealthInfo {
  status: string;
  gpu_name?: string | null;
  vram_free_gb?: number | null;
  vram_total_gb?: number | null;
  ram_total_gb?: number | null;
  ram_available_gb?: number | null;
  worker_ready?: boolean;
  active_job_id?: string | null;
  queued_count?: number;
  capabilities?: string[];
  latency_ms?: number;
}

export interface ColabCliUsageSummary {
  balance?: number | null;
  usage_rate?: number | null;
  active_assignments?: number | null;
}

export interface ColabCliPrereqs {
  ok: boolean;
  colab_installed: boolean;
  colab_path: string;
  uv_installed: boolean;
  ssh_installed: boolean;
  ssh_key_exists: boolean;
  ssh_key_path: string;
  auth_ok: boolean;
  usage_summary?: ColabCliUsageSummary | null;
  error?: string;
}

export interface ColabCliStatus {
  state: 'stopped' | 'starting' | 'running' | 'stopping' | 'error';
  session_name: string;
  gpu: ColabGpuType;
  high_mem: boolean;
  use_drive_cache: boolean;
  idle_timeout_minutes: number;
  idle_remaining_sec: number | null;
  server_url: string;
  last_health?: ColabHealthInfo | null;
  warnings: string[];
  error?: string | null;
  suggest_switch_to_t4?: boolean;
  status_message: string;
}

export interface ColabConfig {
  execution_target: ExecutionTarget;
  colab_mode?: ColabMode;
  server_url: string;
  api_token: string;
  remember_token: boolean;
  cli_gpu?: ColabGpuType;
  cli_high_mem?: boolean;
  cli_use_drive_cache?: boolean;
  cli_idle_timeout_minutes?: number;
  last_health?: ColabHealthInfo | null;
  cli_status?: ColabCliStatus | null;
}

export interface JobSummary {
  pose_engine?: PoseEngineType;
  pose_model: string;
  pose_input_size: string;
  vitpose_model?: string;
  vitpose_input_size?: string;
  vitpose_precision?: string;
  vitpose_flip_test?: boolean;
  yolo_model: string;
  device: string;
  capture_fps?: number | null;
}

export interface JobSettings {
  INPUT_ROOT: string;
  INPUT_VIDEO_NAME: string;
  OUTPUT_ROOT: string;
  OUTPUT_FOLDER_NAME: string;
  OUTPUT_VIDEO_NAME?: string;
  OUTPUT_CROP_VIDEO_NAME?: string;
  OUTPUT_CROP_SKELETON_VIDEO_NAME?: string;
  OUTPUT_CSV_NAME?: string;
  OUTPUT_METADATA_NAME?: string;
  OUTPUT_METADATA_JSON_NAME?: string;
  OUTPUT_NPZ_NAME?: string;
  DEVICE: string;
  CAPTURE_FPS?: number | null;
  YOLO_MODEL: string;
  YOLO_CLASSES: number[];
  YOLO_BATCH_SIZE?: number;
  POSE_ENGINE?: PoseEngineType;
  RTMLIB_POSE_MODEL: string;
  RTMLIB_POSE_INPUT_SIZE: string;
  RTMPOSE_BATCH_SIZE?: number;
  VITPOSE_MODEL?: string;
  VITPOSE_INPUT_SIZE?: string;
  VITPOSE_PRECISION?: 'fp16' | 'fp32' | string;
  VITPOSE_BATCH_SIZE?: number;
  VITPOSE_FLIP_TEST?: boolean;
  // Overlay settings
  SKELETON_LINE_WIDTH?: number;
  KEYPOINT_RADIUS?: number;
  LABEL_FONT_SCALE?: number;
  [key: string]: any;
}

export interface ReservationJob {
  id: string; // 32 hex chars
  state: JobState;
  local_rendering?: boolean;
  error: string;
  created_at: string;
  video_path: string;
  video_name: string;
  output_path: string;
  output_folder: string;
  thumbnail: string;
  thumbnail_info: string;
  settings: JobSettings;
  summary: JobSummary;
}

// Alias for convenience
export type Job = ReservationJob;

export interface SystemInfo {
  output_root: string;
  is_processing: boolean;
  current_job_id: string | null;
  queue_active: boolean;
  active_job_id: string | null;
  choices: Record<string, string[]>;
  labels: Record<string, string>;
  groups: Array<{ title: string; keys: string[] }>;
  colab?: ColabConfig;
}

export interface InitialDataPayload {
  settings: JobSettings;
  queue: ReservationJob[];
  system: SystemInfo;
  choices: Record<string, string[]>;
}

export interface LogEntry {
  id: string;
  jobId: string;
  text: string;
  tag: 'heading' | 'error' | 'system' | 'default';
  timestamp: string;
}

export type RightViewType = 'queue' | 'add' | 'basic_settings' | 'job_settings';
