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

import { z } from "zod";

import {
  applicationAggregateSchema,
  applicationViewSchema,
  auditHistoryResponseSchema,
  authorityHistoryResponseSchema,
  authorityRecordViewSchema,
  documentViewSchema,
  registryCompanySchema,
  registrySchema,
  transactionDecisionSchema,
} from "./contracts";
import type {
  ApplicationAggregate,
  ApplicationDecisionRequest,
  ApplicationView,
  AuditHistoryResponse,
  AuthorityHistoryResponse,
  AuthorityRecordView,
  AuthorizeTransactionRequest,
  CosignTransactionRequest,
  CreateApplicationRequest,
  DocumentView,
  ErrorCode,
  ErrorResponse,
  ExtractionCorrectionRequest,
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

/**
 * `request` plus strict Zod validation of the successful body (alignment guide
 * section 8: "Parse successful JSON with the corresponding Zod schema inside
 * lib/api.ts. Do not defer response validation to page components.").
 *
 * A 2xx body that fails its schema is contract drift, which the standard error
 * flow treats as a non-retryable internal problem — retrying cannot produce a
 * differently-shaped response.
 */
async function requestParsed<Schema extends z.ZodTypeAny>(
  path: string,
  schema: Schema,
  options: RequestOptions = {},
): Promise<z.infer<Schema>> {
  const payload = await request<unknown>(path, options);
  return parseSuccessfulPayload(schema, payload);
}

function parseSuccessfulPayload<Schema extends z.ZodTypeAny>(
  schema: Schema,
  payload: unknown,
): z.infer<Schema> {
  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ApiError({
      code: "INTERNAL_ERROR",
      message: "Sunucu yanıtı beklenen sözleşmeye uymuyor.",
      status: 200,
      retryable: false,
      details: { zod_issues: parsed.error.issues.slice(0, 20) },
    });
  }
  return parsed.data as z.infer<Schema>;
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function toApiError(response: Response, payload: unknown): ApiError {
  return toApiErrorParts(response.status, payload, response.headers.get("X-Correlation-Id"));
}

function toApiErrorParts(
  status: number,
  payload: unknown,
  headerCorrelationId: string | null,
): ApiError {
  const envelope = payload as ErrorResponse | null;
  const correlationId =
    headerCorrelationId ?? envelope?.error?.correlation_id ?? null;

  if (envelope?.error?.code) {
    return new ApiError({
      code: envelope.error.code,
      message: envelope.error.message,
      status,
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
    status,
    retryable: status >= 500,
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

/** Clears either one document's extraction cache or, when omitted, the full AI cache. */
export const clearExtractionCache = (documentSha256?: string, signal?: AbortSignal) => {
  const params = new URLSearchParams();
  if (documentSha256) params.set("document_sha256", documentSha256);
  const query = params.toString();
  return request<{ removed: number }>(`/api/demo/cache/clear${query ? `?${query}` : ""}`, {
    method: "POST",
    signal,
  });
};

/* -------------------------------------------------------------------------- */
/* Applications and documents — plan section 8.3                              */
/* -------------------------------------------------------------------------- */

export const createApplication = (
  payload: CreateApplicationRequest,
  signal?: AbortSignal,
): Promise<ApplicationView> =>
  requestParsed("/api/applications", applicationViewSchema, {
    method: "POST",
    body: payload,
    signal,
  });

/** The one server-backed read that restores the whole branch screen. */
export const getApplication = (
  applicationId: number,
  signal?: AbortSignal,
): Promise<ApplicationAggregate> =>
  requestParsed(`/api/applications/${applicationId}`, applicationAggregateSchema, { signal });

export type UploadProgress = {
  phase: "uploading" | "processing";
  loadedBytes: number;
  totalBytes: number;
  percent: number | null;
};

export const uploadDocument = (
  applicationId: number,
  file: File,
  fields: { original_seen: boolean; scanned_by: string },
  signal?: AbortSignal,
  onProgress?: (progress: UploadProgress) => void,
): Promise<DocumentView> => {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("original_seen", String(fields.original_seen));
  formData.append("scanned_by", fields.scanned_by);

  // Fetch intentionally remains the default transport. When the screen asks
  // for genuine byte progress, XHR is used because fetch does not expose
  // browser upload progress events. Both paths stay inside this API module.
  if (onProgress && typeof XMLHttpRequest !== "undefined") {
    return uploadDocumentWithProgress(applicationId, formData, signal, onProgress);
  }

  return requestParsed(`/api/applications/${applicationId}/document`, documentViewSchema, {
    method: "POST",
    formData,
    signal,
  });
};

function uploadDocumentWithProgress(
  applicationId: number,
  formData: FormData,
  signal: AbortSignal | undefined,
  onProgress: (progress: UploadProgress) => void,
): Promise<DocumentView> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    const cleanup = () => signal?.removeEventListener("abort", abort);

    xhr.open("POST", `${API_BASE_URL}/api/applications/${applicationId}/document`);
    xhr.upload.addEventListener("progress", (event) => {
      const totalBytes = event.lengthComputable ? event.total : 0;
      onProgress({
        phase: "uploading",
        loadedBytes: event.loaded,
        totalBytes,
        percent: totalBytes > 0 ? Math.min(100, Math.round((event.loaded / totalBytes) * 100)) : null,
      });
    });
    xhr.upload.addEventListener("load", () => {
      onProgress({
        phase: "processing",
        loadedBytes: formData.get("file") instanceof File ? (formData.get("file") as File).size : 0,
        totalBytes: formData.get("file") instanceof File ? (formData.get("file") as File).size : 0,
        percent: 100,
      });
    });
    xhr.addEventListener("load", () => {
      cleanup();
      const payload: unknown = xhr.responseText ? safeJsonParse(xhr.responseText) : null;
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(
          toApiErrorParts(
            xhr.status,
            payload,
            xhr.getResponseHeader("X-Correlation-Id"),
          ),
        );
        return;
      }
      try {
        resolve(parseSuccessfulPayload(documentViewSchema, payload));
      } catch (error) {
        reject(error);
      }
    });
    xhr.addEventListener("error", () => {
      cleanup();
      reject(
        new ApiError({
          code: "NETWORK_ERROR",
          message: "Sunucuya ulaşılamadı. Bağlantıyı kontrol edip tekrar deneyin.",
          status: 0,
          retryable: true,
        }),
      );
    });
    xhr.addEventListener("abort", () => {
      cleanup();
      reject(new DOMException("aborted", "AbortError"));
    });

    if (signal?.aborted) {
      reject(new DOMException("aborted", "AbortError"));
      return;
    }
    signal?.addEventListener("abort", abort, { once: true });
    onProgress({ phase: "uploading", loadedBytes: 0, totalBytes: 0, percent: 0 });
    xhr.send(formData);
  });
}

/**
 * Runs (or retries) the AI analysis. Idempotent for an already-ANALYZED
 * application: the backend returns the existing report.
 */
export const analyzeApplication = (
  applicationId: number,
  signal?: AbortSignal,
): Promise<ApplicationAggregate> =>
  requestParsed(`/api/applications/${applicationId}/analyze`, applicationAggregateSchema, {
    method: "POST",
    signal,
  });

/** 409 STALE_CORRECTION when `expected_old_value` no longer matches. */
export const correctExtraction = (
  applicationId: number,
  payload: ExtractionCorrectionRequest,
  signal?: AbortSignal,
): Promise<ApplicationAggregate> =>
  requestParsed(`/api/applications/${applicationId}/extraction`, applicationAggregateSchema, {
    method: "PATCH",
    body: payload,
    signal,
  });

export const decideApplication = (
  applicationId: number,
  payload: ApplicationDecisionRequest,
  signal?: AbortSignal,
): Promise<ApplicationAggregate> =>
  requestParsed(`/api/applications/${applicationId}/decision`, applicationAggregateSchema, {
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

export const getRegistry = (signal?: AbortSignal): Promise<Registry> =>
  requestParsed("/api/registry", registrySchema, { signal });

/** GAP-09: representatives are addressed by stable ID, never by name. */
export const updateRegistryRepresentative = (
  mersis: string,
  repId: string,
  payload: RegistryRepresentativeUpdateRequest,
  signal?: AbortSignal,
): Promise<RegistryCompany> =>
  requestParsed(`/api/registry/${mersis}/reps/${repId}`, registryCompanySchema, {
    method: "PUT",
    body: payload,
    signal,
  });

/* -------------------------------------------------------------------------- */
/* Authority and transactions — plan section 8.5                              */
/* -------------------------------------------------------------------------- */

export const getAuthority = (mersis: string, signal?: AbortSignal): Promise<AuthorityRecordView> =>
  requestParsed(`/api/authority/${mersis}`, authorityRecordViewSchema, { signal });

export const getAuthorityHistory = (
  mersis: string,
  signal?: AbortSignal,
): Promise<AuthorityHistoryResponse> =>
  requestParsed(`/api/authority/${mersis}/history`, authorityHistoryResponseSchema, { signal });

export const getAuditHistory = (
  filters?: { entity_type?: string; entity_id?: string },
  signal?: AbortSignal,
): Promise<AuditHistoryResponse> => {
  const params = new URLSearchParams();
  if (filters?.entity_type) params.set("entity_type", filters.entity_type);
  if (filters?.entity_id) params.set("entity_id", filters.entity_id);
  const query = params.toString();
  return requestParsed(`/api/audit${query ? `?${query}` : ""}`, auditHistoryResponseSchema, {
    signal,
  });
};

export const authorizeTransaction = (
  payload: AuthorizeTransactionRequest,
  signal?: AbortSignal,
): Promise<TransactionDecision> =>
  requestParsed("/api/transactions/authorize", transactionDecisionSchema, {
    method: "POST",
    body: payload,
    signal,
  });

export const cosignTransaction = (
  transactionId: number,
  payload: CosignTransactionRequest,
  signal?: AbortSignal,
): Promise<TransactionDecision> =>
  requestParsed(`/api/transactions/${transactionId}/cosign`, transactionDecisionSchema, {
    method: "POST",
    body: payload,
    signal,
  });

export const listTransactions = (
  mersis: string,
  signal?: AbortSignal,
): Promise<TransactionDecision[]> =>
  requestParsed(
    `/api/transactions?mersis=${encodeURIComponent(mersis)}`,
    z.array(transactionDecisionSchema),
    { signal },
  );
