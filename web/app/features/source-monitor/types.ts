export type SourceMonitorItem = {
  id: string;
  source: string;
  account: string;
  display_name: string;
  input_path: string;
  expected_frequency: string;
  max_age_months: number;
  monitoring_active: boolean;
  alert_silenced: boolean;
  portal_url: string;
  notes: string;
  last_manual_review_at: string | null;
  last_statement_period: string | null;
  statement_age_months: number | null;
  statement_files_in_mart: number;
  rows_in_mart: number;
  files_in_mart: number;
  raw_files: number;
  raw_inventory_summary?: Record<string, number>;
  ignored_raw_count?: number;
  ignored_raw_files?: { file_name: string; status: string; reason: string; rows?: number | null }[];
  latest_raw_file: string | null;
  latest_raw_modified: string | null;
  unprocessed_raw_files: string[];
  unprocessed_raw_count: number;
  status: "ok" | "attention" | "alert" | "inactive";
  alert: boolean;
  reason: string;
};

export type SourceMonitorData = {
  generated_at: string;
  items: SourceMonitorItem[];
  summary: {
    total: number;
    alerts: number;
    status_counts: Record<string, number>;
  };
};

export type SourceMonitorProcessResult = {
  ok: boolean;
  processed_at: string;
  display_name: string;
  source: string;
  account: string;
  pending_files_before: string[];
  last_statement_before: string | null;
  last_statement_after: string | null;
  pending_files_after: string[];
  summary: { statement_period: string; rows: number; amount_usd: number; files: number }[];
  total_rows: number;
  total_amount_usd: number;
};

export type SourceMonitorPublishResult = {
  ok: boolean;
  published_at: string;
  bucket: string;
  prefix: string;
  uploaded: { file_name: string; object_name: string; size_bytes: number; size_mb: number }[];
};

export type SourceMonitorPublishJob = {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result: SourceMonitorPublishResult | null;
  error: unknown;
};
