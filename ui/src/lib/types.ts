export type ApiResponse<T> = {
  success: boolean;
  message: string;
  data: T;
};

export type AuthLoginResponse = {
  access_token: string;
  token_type: string;
  role: "uploader" | "moderator" | "admin";
  username: string;
};

export type VideoUploadResponse = {
  video_id: string;
  job_id: string;
  storage_uri?: string;
  thumbnail_uri?: string | null;
  content_type?: string;
  queued: boolean;
  phase_a_task_id?: string;
  enqueue_error?: string | null;
  deduplicated?: boolean;
};

export type JobStatus = {
  job_id: string;
  video_id: string;
  state: string;
  priority: string;
  attempts: number;
  last_error?: string | null;
  updated_at: string;
};

export type ReviewTask = {
  task_id: string;
  job_id: string;
  video_id: string;
  gate: "GATE_1" | "GATE_2";
  priority: string;
  status: string;
  reviewer_ref?: string | null;
  created_at: string;
};
