/**
 * Async view states.
 *
 * Plan section 10.1: "All async views have loading, retryable error,
 * non-retryable error, and empty states." Four states, four components — so a
 * screen that forgets one is visibly missing a component rather than silently
 * rendering nothing.
 *
 * `ErrorState` picks retryable vs terminal from the API's own `retryable` flag
 * (plan section 5.7). The client never guesses which one it is.
 */

"use client";

import type { ReactNode } from "react";

import { ApiError } from "@/lib/api";

export function LoadingState({ label = "Yükleniyor…" }: { label?: string }) {
  return (
    <div className="px-5 py-14 text-center text-sm text-ink-3" role="status" aria-live="polite">
      <span className="mr-2 inline-block size-3 animate-pulse rounded-full bg-line-strong align-middle" />
      {label}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: ReactNode }) {
  return (
    <div className="px-5 py-14 text-center text-sm text-ink-3">
      <div>{title}</div>
      {hint ? <div className="mt-1 text-[13px]">{hint}</div> : null}
    </div>
  );
}

/**
 * Retryable and terminal errors in one component, chosen by the error itself.
 *
 * A retry button on something that can never succeed is worse than no button:
 * on stage it invites the presenter to click into the same failure twice.
 */
export function ErrorState({
  error,
  onRetry,
  title,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  const apiError = error instanceof ApiError ? error : null;
  const retryable = apiError?.retryable ?? false;
  const message =
    apiError?.message ??
    (error instanceof Error ? error.message : "Beklenmeyen bir hata oluştu.");

  return (
    <div className="px-5 py-12 text-center" role="alert">
      <div className="mx-auto max-w-md rounded-[10px] border border-bad/30 bg-bad-bg px-4 py-4">
        <div className="text-sm font-semibold text-bad">
          <span aria-hidden>× </span>
          {title ?? (retryable ? "İşlem tamamlanamadı" : "Bu işlem şu anda yapılamıyor")}
        </div>
        <p className="mt-1.5 text-[13px] text-ink-2">{message}</p>

        {retryable && onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 rounded-lg border border-line-strong bg-surface px-4 py-2 text-[13.5px] font-medium text-ink hover:bg-surface-2"
          >
            Tekrar dene
          </button>
        ) : null}

        {apiError?.correlationId ? (
          // Section 15: the correlation ID ties this screen to the server log.
          <p className="mt-3 font-mono text-[11px] text-ink-3">
            İşlem no: {apiError.correlationId}
          </p>
        ) : null}
      </div>
    </div>
  );
}
