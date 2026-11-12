export type JobState = 'pending' | 'running' | 'done' | 'failed';

export type PhaseCode = 'IDLE' | 'STARTING' | 'YOLO' | 'RTMPose' | 'RTMLIB' | 'VITPOSE' | 'STOPPING' | 'DONE';

export type PoseEngineType = 'rtmpose' | 'vitpose';

export interface JobSummary {
  pose_engine?: PoseEngineType;
  pose_model: string;
  pose_input_size: string;
  vitpose_model?: string;
  vitpose_input_size?: string;
  vitpose_flip_test?: boolean;
  yolo_model: string;
  device: string;
  track_id: number | null;
  csv_max_persons: number;
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
  DEVICE: string;
  YOLO_MODEL: string;
  YOLO_CLASSES: number[];
  YOLO_BATCH_SIZE?: number;
  YOLO_TRACK_ID: number | null;
  CSV_MAX_PERSONS: number;
  POSE_ENGINE?: PoseEngineType;
  RTMLIB_POSE_MODEL: string;
  RTMLIB_POSE_INPUT_SIZE: string;
  RTMPOSE_BATCH_SIZE?: number;
  VITPOSE_MODEL?: string;
  VITPOSE_INPUT_SIZE?: string;
  VITPOSE_BATCH_SIZE?: number;
  VITPOSE_FLIP_TEST?: boolean;
  // Overlay settings
  DRAW_SKELETON?: boolean;
  DRAW_BBOX?: boolean;
  SKELETON_LINE_WIDTH?: number;
  KEYPOINT_RADIUS?: number;
  LABEL_FONT_SCALE?: number;
  [key: string]: any;
}

export interface ReservationJob {
  id: string; // 32 hex chars
  state: JobState;
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
