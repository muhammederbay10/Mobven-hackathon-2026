/**
 * The bank API layer.
 *
 * Plan section 10.1: **this is the only file allowed to call `fetch`.** An
 * ESLint rule enforces it. Everything else imports a typed function from here,
 * so there is exactly one place where a URL, a status code or an error envelope
 * has to be understood.
 *
 * Section 1.3: the browser talks only to the bank API. There is deliberately no
 * function here that reaches the AI service — that call is server-to-server.
 *
 * Nothing in this module interprets a verdict. It moves typed payloads across
 * the wire and turns a non-2xx body into a typed error; the meaning of those
 * payloads belongs to the API (section 10.1).
 */

import type {
  ApplicationDecisionRequest,
  AuthorityRecordView,
  AuthorizeTransactionRequest,
  CosignTransactionRequest,
  CreateApplicationRequest,
  ErrorCode,
  ErrorResponse,
  OnboardingVerdict,
  Registry,
  RegistryCompany,
  RegistryRepresentativeUpdateRequest,
  TransactionDecision,
} from "./types";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

/* -------------------------------------------------------------------------- */
/* Errors                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * A typed API failure carrying the standard envelope (plan section 5.7).
 *
 * `retryable` is what the UI uses to choose between a retry affordance and a
 * terminal error state — the two are different screens, and guessing between
 * them is how a demo ends up offering "tekrar dene" on something that can never
 * succeed.
 */
export class ApiError extends Error {
  readonly code: ErrorCode | "NETWORK_ERROR";
  readonly status: number;
  readonly retryable: boolean;
  readonly details: Record<string, unknown>;
  readonly correlationId: string | null;

  constructor(init: {
    code: ErrorCode | "NETWORK_ERROR";
    message: string;
    status: number;
    retryable: boolean;
    details?: Record<string, unknown>;
    correlationId?: string | null;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.code = init.code;
    this.status = init.status;
    this.retryable = init.retryable;
    this.details = init.details ?? {};
    this.correlationId = init.correlationId ?? null;
  }
}

/** Field-level validation messages, for rendering errors beside their input. */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {};
  const fields = error.details.fields;
  if (!Array.isArray(fields)) return {};
  const result: Record<string, string> = {};
  for (const entry of fields) {
    if (
      entry &&
      typeof entry === "object" &&
      typeof (entry as { path?: unknown }).path === "string" &&
      typeof (entry as { message?: unknown }).message === "string"
    ) {
      result[(entry as { path: string }).path] = (entry as { message: string }).message;
    }
  }
  return result;
}

/* -------------------------------------------------------------------------- */
/* Transport                                                                  */
/* -------------------------------------------------------------------------- */

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT";
  body?: unknown;
  formData?: FormData;
  signal?: AbortSignal;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, formData, signal } = options;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      signal,
      headers: formData || body === undefined ? undefined : { "Content-Type": "application/json" },
      body: formData ?? (body === undefined ? undefined : JSON.stringify(body)),
    });
  } catch (cause) {
    // Section 15: on a network failure, preserve the screen and offer retry.
    // Never infer success from a request that did not complete.
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError({
      code: "NETWORK_ERROR",
      message: "Sunucuya ulaşılamadı. Bağlantıyı kontrol edip tekrar deneyin.",
      status: 0,
      retryable: true,
    });
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload: unknown = text ? safeJsonParse(text) : null;

  if (!response.ok) throw toApiError(response, payload);
  return payload as T;
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function toApiError(response: Response, payload: unknown): ApiError {
  const envelope = payload as ErrorResponse | null;
  const correlationId =
    response.headers.get("X-Correlation-Id") ?? envelope?.error?.correlation_id ?? null;

  if (envelope?.error?.code) {
    return new ApiError({
      code: envelope.error.code,
      message: envelope.error.message,
      status: response.status,
      retryable: envelope.error.retryable,
      details: envelope.error.details ?? {},
      correlationId,
    });
  }

  // A non-2xx without the standard envelope is itself a contract problem. Show
  // something honest rather than dumping whatever the body happened to contain.
  return new ApiError({
    code: "INTERNAL_ERROR",
    message: "Beklenmeyen bir hata oluştu.",
    status: response.status,
    retryable: response.status >= 500,
    correlationId,
  });
}

/* -------------------------------------------------------------------------- */
/* Infrastructure — plan section 8.1                                          */
/* -------------------------------------------------------------------------- */

export type HealthResponse = { status: string; database: boolean };

export type ReadyResponse = {
  ready: boolean;
  blocking: string[];
  checks: Record<string, unknown>;
};

export const getHealth = (signal?: AbortSignal) =>
  request<HealthResponse>("/health", { signal });

export const getReady = (signal?: AbortSignal) => request<ReadyResponse>("/ready", { signal });

/* -------------------------------------------------------------------------- */
/* Demo control — plan section 8.2                                            */
/* -------------------------------------------------------------------------- */

export type DemoCaseCard = {
  case: number;
  title: string;
  description: string;
  expected_verdict: OnboardingVerdict;
};

export const listDemoCases = (signal?: AbortSignal) =>
  request<{ cases: DemoCaseCard[] }>("/api/demo/cases", { signal });

/** Creates real server state and returns its persistent application ID. */
export const loadDemoCase = (caseNumber: number, signal?: AbortSignal) =>
  request<{ application_id: number }>(`/api/demo/load-case/${caseNumber}`, {
    method: "POST",
    signal,
  });

export const resetDemo = (signal?: AbortSignal) =>
  request<{ ok: boolean; removed_uploads: number }>("/api/demo/reset", {
    method: "POST",
    signal,
  });

/* -------------------------------------------------------------------------- */
/* Applications and documents — plan section 8.3                              */
/* -------------------------------------------------------------------------- */
/* Implemented by tasks P1-02, P1-03 and P2-02. The signatures live here now so
   feature work adds a body, not a new place that knows about `fetch`.        */

export const createApplication = (payload: CreateApplicationRequest, signal?: AbortSignal) =>
  request<{ id: number }>("/api/applications", { method: "POST", body: payload, signal });

export const uploadDocument = (
  applicationId: number,
  file: File,
  fields: { original_seen: boolean; scanned_by: string },
  signal?: AbortSignal,
) => {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("original_seen", String(fields.original_seen));
  formData.append("scanned_by", fields.scanned_by);
  return request<{ id: number }>(`/api/applications/${applicationId}/document`, {
    method: "POST",
    formData,
    signal,
  });
};

export const decideApplication = (
  applicationId: number,
  payload: ApplicationDecisionRequest,
  signal?: AbortSignal,
) =>
  request<unknown>(`/api/applications/${applicationId}/decision`, {
    method: "POST",
    body: payload,
    signal,
  });

/** Server-rendered document page image. A URL, not a fetch — used as an `<img src>`. */
export const documentPageUrl = (documentId: number, page: number) =>
  `${API_BASE_URL}/api/documents/${documentId}/page/${page}`;

/* -------------------------------------------------------------------------- */
/* Registry — plan section 8.4                                                */
/* -------------------------------------------------------------------------- */

export const getRegistry = (signal?: AbortSignal) =>
  request<Registry>("/api/registry", { signal });

/** GAP-09: representatives are addressed by stable ID, never by name. */
export const updateRegistryRepresentative = (
  mersis: string,
  repId: string,
  payload: RegistryRepresentativeUpdateRequest,
  signal?: AbortSignal,
) =>
  request<RegistryCompany>(`/api/registry/${mersis}/reps/${repId}`, {
    method: "PUT",
    body: payload,
    signal,
  });

/* -------------------------------------------------------------------------- */
/* Authority and transactions — plan section 8.5                              */
/* -------------------------------------------------------------------------- */

export const getAuthority = (mersis: string, signal?: AbortSignal) =>
  request<AuthorityRecordView>(`/api/authority/${mersis}`, { signal });

export const authorizeTransaction = (
  payload: AuthorizeTransactionRequest,
  signal?: AbortSignal,
) =>
  request<TransactionDecision>("/api/transactions/authorize", {
    method: "POST",
    body: payload,
    signal,
  });

export const cosignTransaction = (
  transactionId: number,
  payload: CosignTransactionRequest,
  signal?: AbortSignal,
) =>
  request<TransactionDecision>(`/api/transactions/${transactionId}/cosign`, {
    method: "POST",
    body: payload,
    signal,
  });

export const listTransactions = (mersis: string, signal?: AbortSignal) =>
  request<TransactionDecision[]>(
    `/api/transactions?mersis=${encodeURIComponent(mersis)}`,
    { signal },
  );
