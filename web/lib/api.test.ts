/**
 * Wire-level tests for the API layer: URL/method construction, strict Zod
 * parsing of successful bodies, the standard error envelope, and the
 * network-failure path (guide sections 8, 11 and 19).
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  API_BASE_URL,
  clearExtractionCache,
  correctExtraction,
  createApplication,
  fieldErrors,
  getApplication,
  getAuditHistory,
  listTransactions,
} from "./api";

const APPLICATION_VIEW = {
  id: 12,
  company_name: "ABC Teknoloji Ltd. Şti.",
  tax_number: "1234567890",
  mersis: "0123456789000017",
  applicant_name: "Ali Yılmaz",
  applicant_tckn_masked: "123******01",
  branch_code: "kozyatagi01",
  identity_verified_at_branch: true,
  status: "IDENTITY_VERIFIED",
  version: 1,
  created_at: "2026-08-01T10:00:00Z",
  updated_at: "2026-08-01T10:00:00Z",
};

const CREATE_REQUEST = {
  company_name: "ABC Teknoloji Ltd. Şti.",
  tax_number: "1234567890",
  mersis: "0123456789000017",
  applicant_name: "Ali Yılmaz",
  applicant_tckn_masked: "123******01",
  branch_code: "kozyatagi01",
  identity_verified_at_branch: true,
};

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

function stubFetch(response: Response | Promise<Response>) {
  const mock = vi.fn().mockReturnValue(Promise.resolve(response));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("request construction", () => {
  it("POSTs createApplication to /api/applications with a JSON body", async () => {
    const mock = stubFetch(jsonResponse(APPLICATION_VIEW, { status: 201 }));
    const view = await createApplication(CREATE_REQUEST);
    expect(view.id).toBe(12);
    const [url, init] = mock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${API_BASE_URL}/api/applications`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual(CREATE_REQUEST);
  });

  it("PATCHes corrections to /api/applications/{id}/extraction", async () => {
    const aggregate = {
      application: APPLICATION_VIEW,
      document: null,
      extraction: null,
      report: null,
      corrections: [],
      authority: null,
    };
    const mock = stubFetch(jsonResponse(aggregate));
    await correctExtraction(12, {
      reason: "Noter belgesiyle tekrar kontrol edildi.",
      corrections: [
        {
          field_path: "representatives[rep-1].name",
          expected_old_value: "Ali Yilmaz",
          new_value: "Ali Yılmaz",
        },
      ],
    });
    const [url, init] = mock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${API_BASE_URL}/api/applications/12/extraction`);
    expect(init.method).toBe("PATCH");
  });

  it("builds the audit query string from the given filters only", async () => {
    const mock = stubFetch(jsonResponse({ items: [] }));
    await getAuditHistory({ entity_type: "AUTHORITY_RECORD", entity_id: "3" });
    expect((mock.mock.calls[0] as [string])[0]).toBe(
      `${API_BASE_URL}/api/audit?entity_type=AUTHORITY_RECORD&entity_id=3`,
    );

    const bare = stubFetch(jsonResponse({ items: [] }));
    await getAuditHistory();
    expect((bare.mock.calls[0] as [string])[0]).toBe(`${API_BASE_URL}/api/audit`);
  });

  it("clears only the requested document extraction cache", async () => {
    const mock = stubFetch(jsonResponse({ removed: 1 }));
    await clearExtractionCache("abc+123/sha");
    const [url, init] = mock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      `${API_BASE_URL}/api/demo/cache/clear?document_sha256=abc%2B123%2Fsha`,
    );
    expect(init.method).toBe("POST");
  });
});

describe("strict response parsing", () => {
  it("returns the parsed aggregate for a valid body", async () => {
    stubFetch(
      jsonResponse({
        application: APPLICATION_VIEW,
        document: null,
        extraction: null,
        report: null,
        corrections: [],
        authority: null,
      }),
    );
    const aggregate = await getApplication(12);
    expect(aggregate.application.status).toBe("IDENTITY_VERIFIED");
    expect(aggregate.document).toBeNull();
  });

  it("treats a 2xx body that fails its schema as non-retryable contract drift", async () => {
    stubFetch(jsonResponse({ id: 12 }, { status: 201 }));
    const failure = await createApplication(CREATE_REQUEST).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).code).toBe("INTERNAL_ERROR");
    expect((failure as ApiError).retryable).toBe(false);
  });

  it("parses transaction lists element by element", async () => {
    stubFetch(jsonResponse([{ transaction_id: "nope" }]));
    await expect(listTransactions("0123456789000017")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("standard error envelope", () => {
  it("surfaces code, retryable, correlation id and field details", async () => {
    stubFetch(
      jsonResponse(
        {
          error: {
            code: "VALIDATION_ERROR",
            message: "Gönderilen bilgiler geçersiz.",
            retryable: false,
            details: {
              fields: [{ path: "tax_number", message: "10 hane olmalı" }],
            },
            correlation_id: "corr-42",
          },
        },
        { status: 422 },
      ),
    );
    const failure = await createApplication(CREATE_REQUEST).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    const apiError = failure as ApiError;
    expect(apiError.code).toBe("VALIDATION_ERROR");
    expect(apiError.retryable).toBe(false);
    expect(apiError.correlationId).toBe("corr-42");
    expect(fieldErrors(apiError)).toEqual({ tax_number: "10 hane olmalı" });
  });

  it("maps a transport failure to a retryable NETWORK_ERROR", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("fetch failed")),
    );
    const failure = await getApplication(1).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).code).toBe("NETWORK_ERROR");
    expect((failure as ApiError).retryable).toBe(true);
  });

  it("keeps an AbortError as-is so screens can ignore it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError")),
    );
    const failure = await getApplication(1).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(DOMException);
    expect((failure as DOMException).name).toBe("AbortError");
  });
});
