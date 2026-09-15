export type Severity = "HIGH" | "MEDIUM" | "LOW";
export type Effort = "SMALL" | "MEDIUM" | "LARGE";
export type VerdictValue = "SUSTAINED" | "REDUCED" | "DISMISSED";
export type PleaValue = "ADMIT" | "DENY" | "NO_RESPONSE";

export type CaseStatus =
  | "QUEUED_PROSECUTION"
  | "PROSECUTING"
  | "QUEUED_DEFENSE"
  | "DEFENDING"
  | "QUEUED_JUDGMENT"
  | "JUDGING"
  | "SENTENCED"
  | "DISMISSED"
  | "QUEUED_REJUDGMENT"
  | "REJUDGING"
  | "FAILED";

export type FailedStage = "PROSECUTION" | "DEFENSE" | "JUDGMENT" | null;
export type FailureReason = "SCHEMA_INVALID" | "TIMEOUT" | "API_ERROR" | null;

export type ErrorCode =
  | "VALIDATION_ERROR"
  | "EMPTY_CODE"
  | "CODE_TOO_LONG"
  | "INVALID_LANGUAGE"
  | "REBUTTAL_TOO_SHORT"
  | "UNAUTHORIZED"
  | "INVALID_CREDENTIALS"
  | "CASE_NOT_FOUND"
  | "SENTENCE_NOT_FOUND"
  | "EMAIL_ALREADY_REGISTERED"
  | "APPEAL_ALREADY_USED"
  | "RETRIAL_BLOCKED"
  | "RATE_LIMITED"
  | "INVALID_REPO_URL"
  | "REPO_FILE_UNAVAILABLE"
  | "GITHUB_UNAVAILABLE"
  | "FETCH_RATE_LIMITED"
  | "CSRF_CHECK_FAILED";

export interface UserSummary {
  user_id: string;
  email: string;
}

export interface Rule {
  rule_id: string;
  category: string;
  title: string;
  description: string;
  default_severity: Severity;
  typical_effort: Effort;
  languages: string[];
  active: boolean;
}

export interface CaseOrigin {
  type: "paste" | "github";
  repo_url: string | null;
  commit_sha: string | null;
  file_path: string | null;
}

export interface CaseSubmissionResult {
  case_id: string;
  cached: boolean;
  in_progress?: boolean;
  origin?: CaseOrigin | null;
  origin_label?: string | null;
  previous_case_id?: string;
}

export interface Charge {
  charge_index: number;
  rule_id: string;
  rule_title: string;
  evidence_start: number;
  evidence_end: number;
  charged_severity: Severity;
  severity_adjusted: boolean;
  severity_reason: string | null;
  description: string;
}

export interface Plea {
  charge_index: number;
  plea: PleaValue;
  argument: string;
}

export interface Verdict {
  charge_index: number;
  verdict: VerdictValue;
  final_severity: Severity | null;
  reasoning: string;
}

export interface Sentence {
  sentence_id: string;
  charge_index: number;
  task: string;
  target_start: number;
  target_end: number;
  effort: Effort;
  effort_adjusted: boolean;
  effort_reason: string | null;
  effort_clamped: boolean;
  advisory: boolean;
  rationale: string;
  completed_at: string | null;
}

export interface Judgment {
  revision: 0 | 1;
  opinion: string;
  rebuttal_accepted: boolean | null;
  precedent_verdict_ids: number[];
  verdicts: Verdict[];
  sentences: Sentence[];
}

export interface Appeal {
  rebuttal: string;
  created_at: string;
}

export interface CaseDetail {
  case_id: string;
  language: string;
  status: CaseStatus;
  revision: 0 | 1;
  appeal_used: boolean;
  charges_truncated: boolean;
  total_lines: number;
  failed_stage: FailedStage;
  failure_reason: FailureReason;
  origin: CaseOrigin;
  created_at: string;
  updated_at: string;
  charges: Charge[];
  pleas: Plea[];
  judgment: Judgment | null;
  appeal: Appeal | null;
  code: string;
}

export interface CaseProgress {
  status: CaseStatus;
  revision: 0 | 1;
  appeal_used: boolean;
}

export interface CaseSummary {
  case_id: string;
  language: string;
  status: CaseStatus;
  origin_label: string;
  charges_count: number;
  sustained_count: number;
  sentence_progress: { done: number; total: number };
  created_at: string;
}
