import type {
  CaseDetail,
  CaseProgress,
  CaseSubmissionResult,
  ErrorCode,
  Rule,
  UserSummary,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const CSRF_HEADERS = { "X-CSRF-Protection": "1" };

export class ApiError extends Error {
  code: ErrorCode | "NETWORK_ERROR";
  status: number;
  details: Record<string, unknown>;

  constructor(
    code: ErrorCode | "NETWORK_ERROR",
    message: string,
    status: number,
    details: Record<string, unknown> = {},
  ) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const isStateChanging = method !== "GET" && method !== "HEAD";

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      method,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(isStateChanging ? CSRF_HEADERS : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new ApiError(
      "NETWORK_ERROR",
      "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
      0,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    const error = body?.error;
    throw new ApiError(
      error?.code ?? "NETWORK_ERROR",
      error?.message ?? "요청을 처리하지 못했습니다.",
      response.status,
      error?.details ?? {},
    );
  }

  return body as T;
}

export function register(
  email: string,
  password: string,
): Promise<UserSummary> {
  return request("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function login(email: string, password: string): Promise<UserSummary> {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function listRules(): Promise<Rule[]> {
  return request("/rules");
}

export function createCase(
  payload:
    | { code: string; language: string; force_retrial?: boolean }
    | { repo_url: string; force_retrial?: boolean },
): Promise<CaseSubmissionResult> {
  return request("/cases", { method: "POST", body: JSON.stringify(payload) });
}

export function getCase(caseId: string): Promise<CaseDetail> {
  return request(`/cases/${caseId}`);
}

export function getCaseProgress(caseId: string): Promise<CaseProgress> {
  return request(`/cases/${caseId}/progress`);
}

export function appealCase(
  caseId: string,
  rebuttal: string,
): Promise<CaseProgress> {
  return request(`/cases/${caseId}/appeal`, {
    method: "POST",
    body: JSON.stringify({ rebuttal }),
  });
}

export function toggleSentence(
  sentenceId: string,
  completed: boolean,
): Promise<{
  sentence_id: string;
  completed_at: string | null;
  progress: { done: number; total: number };
}> {
  return request(`/sentences/${sentenceId}`, {
    method: "PATCH",
    body: JSON.stringify({ completed }),
  });
}
