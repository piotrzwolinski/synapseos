import { getAuthHeaders, clearToken } from "./auth";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const SESSION_ID_KEY = "chat_session_id";

export function getSessionId(): string {
  if (typeof window === "undefined") return "default";
  let sessionId = sessionStorage.getItem(SESSION_ID_KEY);
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    sessionStorage.setItem(SESSION_ID_KEY, sessionId);
  }
  return sessionId;
}

export function resetSessionId(): string {
  if (typeof window === "undefined") return "default";
  sessionStorage.removeItem(SESSION_ID_KEY);
  const newId = crypto.randomUUID();
  sessionStorage.setItem(SESSION_ID_KEY, newId);
  return newId;
}

export function apiUrl(path: string): string {
  const base = API_BASE_URL.replace(/\/$/, "");
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${cleanPath}`;
}

/**
 * Merge auth headers with provided fetch options.
 * Usage: fetch(apiUrl("/endpoint"), authFetch({ method: "POST", body: ... }))
 */
export function authFetch(options: RequestInit = {}): RequestInit {
  const authHeaders = getAuthHeaders();
  return {
    ...options,
    headers: {
      ...authHeaders,
      ...options.headers,
    },
  };
}

/**
 * Authenticated fetch wrapper - fetches with auth and handles 401.
 * Usage: await apiFetch("/endpoint", { method: "POST", body: ... })
 */
export async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const url = apiUrl(path);
  const response = await fetch(url, authFetch(options));

  // If unauthorized, clear token and redirect to login
  if (response.status === 401) {
    clearToken();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }

  return response;
}

// =============================================================================
// SESSION GRAPH (Layer 4) API HELPERS
// =============================================================================

export interface SessionGraphState {
  session_id: string;
  project: {
    name?: string;
    customer?: string;
    locked_material?: string;
    detected_family?: string;
  } | null;
  tags: Array<{
    tag_id: string;
    filter_width?: number;
    filter_height?: number;
    filter_depth?: number;
    housing_width?: number;
    housing_height?: number;
    housing_length?: number;
    product_code?: string;
    weight_kg?: number;
    is_complete?: boolean;
  }>;
  tag_count: number;
  reasoning_paths?: Array<{ tag_id: string; path: string }>;
}

export async function getSessionGraphState(): Promise<SessionGraphState | null> {
  try {
    const sid = getSessionId();
    const response = await fetch(
      apiUrl(`/session/graph/${sid}`),
      authFetch()
    );
    if (response.ok) {
      return await response.json();
    }
    return null;
  } catch {
    return null;
  }
}

export async function clearSessionGraph(): Promise<void> {
  try {
    const sid = getSessionId();
    await fetch(
      apiUrl(`/session/${sid}`),
      authFetch({ method: "DELETE" })
    );
  } catch {
    // Non-fatal
  }
}

// =============================================================================
// LLM-AS-A-JUDGE API HELPERS
// =============================================================================

export async function judgeQuestion(
  question: string,
  sessionId?: string
): Promise<Response> {
  return apiFetch("/judge/run/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
  });
}

export async function runBatchJudge(
  testFilter: string = "all",
  limit: number = 0
): Promise<Response> {
  return apiFetch("/judge/batch/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ test_filter: testFilter, limit }),
  });
}

export async function getJudgeResults(): Promise<unknown> {
  const res = await apiFetch("/judge/results");
  if (!res.ok) return null;
  return res.json();
}

export async function generateJudgeQuestions(
  file: File,
  config: { target_count: number }
): Promise<Response> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("config", JSON.stringify(config));
  return apiFetch("/judge/generate/stream", {
    method: "POST",
    body: formData,
  });
}

export async function approveJudgeQuestions(
  questions: Record<string, unknown>[]
): Promise<{ status: string; added: number; total: number }> {
  const res = await apiFetch("/judge/questions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ questions }),
  });
  return res.json();
}

export interface JudgeUsage {
  prompt_tokens?: number;
  cached_tokens?: number;
  output_tokens?: number;
  duration_s?: number;
}

export interface JudgeSingleResult {
  scores: Record<string, number>;
  overall_score: number;
  explanation: string;
  dimension_explanations: Record<string, string>;
  strengths: string[];
  weaknesses: string[];
  pdf_citations: string[];
  recommendation: string;
  usage?: JudgeUsage;
}

export interface JudgeEvalResult {
  gemini: JudgeSingleResult;
  openai: JudgeSingleResult;
  anthropic: JudgeSingleResult;
}

export async function evaluateResponse(
  question: string,
  responseData: Record<string, unknown>
): Promise<JudgeEvalResult> {
  const res = await apiFetch("/judge/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, response_data: responseData }),
  });
  if (!res.ok) throw new Error("Judge evaluation failed");
  return res.json();
}

// =============================================================================
// EXPERT REVIEW API HELPERS
// =============================================================================

export interface ConversationSummary {
  session_id: string;
  project_name: string | null;
  detected_family: string | null;
  locked_material: string | null;
  turn_count: number;
  last_activity: number | null;
  has_review: boolean;
  review_score: string | null;
}

export interface ConversationTurn {
  id: string;
  role: string;
  message: string;
  turn_number: number;
  created_at: number;
  judge_results: string | null;
}

export interface ExpertReviewData {
  id: string;
  reviewer: string;
  comment: string;
  overall_score: string;
  dimension_scores: string | null;
  provider: string | null;
  turn_number: number | null;
  created_at: number;
}

export interface ConversationDetail {
  session_id: string;
  project_name: string | null;
  detected_family: string | null;
  locked_material: string | null;
  resolved_params: string | null;
  turns: ConversationTurn[];
  reviews: ExpertReviewData[];
  judge_results: Record<string, JudgeSingleResult> | null;
}

export async function getExpertConversations(
  limit = 50,
  offset = 0
): Promise<{ conversations: ConversationSummary[]; total: number }> {
  const res = await apiFetch(
    `/expert/conversations?limit=${limit}&offset=${offset}`
  );
  if (!res.ok) throw new Error("Failed to load conversations");
  return res.json();
}

export async function getExpertConversation(
  sessionId: string
): Promise<ConversationDetail> {
  const res = await apiFetch(`/expert/conversations/${sessionId}`);
  if (!res.ok) throw new Error("Failed to load conversation");
  return res.json();
}

export async function submitExpertReview(
  sessionId: string,
  review: {
    comment: string;
    overall_score: string;
    dimension_scores?: Record<string, string>;
    provider?: string;
    turn_number?: number;
  }
): Promise<{ status: string; review: ExpertReviewData }> {
  const res = await apiFetch(`/expert/review/${sessionId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(review),
  });
  if (!res.ok) throw new Error("Failed to submit review");
  return res.json();
}

export async function saveJudgeResults(
  sessionId: string,
  turnNumber: number,
  judgeResults: Record<string, unknown>
): Promise<void> {
  await apiFetch(`/session/${sessionId}/judge-results`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ turn_number: turnNumber, judge_results: judgeResults }),
  });
}

export async function getExpertReviewsSummary(): Promise<{
  total: number;
  positive: number;
  negative: number;
  recent: ExpertReviewData[];
}> {
  const res = await apiFetch("/expert/reviews");
  if (!res.ok) throw new Error("Failed to load reviews");
  return res.json();
}

// =============================================================================
// GRAPH AUDIT API HELPERS
// =============================================================================

export interface GraphAuditFinding {
  id: number;
  category: string;
  severity: string;
  product_family: string;
  description: string;
  pdf_says: string;
  graph_says: string;
  recommendation: string;
  confidence: number;
  agreed_by: string[];
  challenged_by: string[];
  final_verdict?: string;
}

export interface GraphAuditReport {
  overall_score: number;
  confidence: number;
  total_findings: number;
  findings: GraphAuditFinding[];
  recommendations: string[];
  summary: string;
}

export interface GraphAuditReportMeta {
  filename: string;
  timestamp: string;
  overall_score: number;
  total_findings: number;
  providers: string[];
  duration_s: number;
}

export async function getGraphAuditResults(): Promise<unknown> {
  const res = await apiFetch("/graph-audit/results");
  if (!res.ok) return null;
  return res.json();
}

export async function listGraphAuditReports(): Promise<GraphAuditReportMeta[]> {
  const res = await apiFetch("/graph-audit/results/list");
  if (!res.ok) return [];
  return res.json();
}
