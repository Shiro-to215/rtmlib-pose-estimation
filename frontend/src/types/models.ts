export type JobState = 'pending' | 'running' | 'done' | 'failed';

export type PhaseCode = 'IDLE' | 'STARTING' | 'YOLO' | 'RTMPose' | 'RTMLIB' | 'VITPOSE' | 'STOPPING' | 'DONE';

export type PoseEngineType = 'rtmpose' | 'vitpose';

export type ExecutionTarget = 'local' | 'colab';

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

export interface ColabConfig {
  execution_target: ExecutionTarget;
  server_url: string;
  api_token: string;
  remember_token: boolean;
  last_health?: ColabHealthInfo | null;
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
