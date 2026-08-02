"use client";

import { useEffect, useRef, useState } from "react";

import {
  ApiError,
  analyzeApplication,
  documentPageUrl,
  getApplication,
  uploadDocument,
} from "@/lib/api";
import type { UploadProgress } from "@/lib/api";
import { formatFileSize } from "@/lib/format";
import type { ApplicationAggregate, DocumentView } from "@/lib/types";

import { CloseIcon, UploadIcon } from "@/components/Icon";
import { Card } from "@/components/Layout";
import { ErrorState } from "@/components/States";
import { Button, Checkbox, Field, Input } from "@/components/UI";

/**
 * Step 2 — original document upload and analysis (guide section 10).
 *
 * Honesty rules baked in here:
 * - upload uses browser byte progress, then switches to a distinct server-side
 *   processing state after the request body has arrived;
 * - analysis shows elapsed time and the real pipeline, but no fabricated
 *   percentage because the backend does not stream stage completion;
 * - the local thumbnail (images only) is replaced by the server-rendered first
 *   page once `DocumentView` exists — server data is authoritative;
 * - a retryable AI failure preserves the document and offers `/analyze` again.
 */

const ACCEPTED_MIME = ["application/pdf", "image/png", "image/jpeg"];

export function UploadStep({
  aggregate,
  onAggregate,
  onRefetch,
}: {
  aggregate: ApplicationAggregate;
  onAggregate: (aggregate: ApplicationAggregate) => void;
  onRefetch: () => void;
}) {
  const { application, document } = aggregate;
  const status = application.status;

  return (
    <div className="grid items-start gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div>
        {document === null ? (
          <UploadForm applicationId={application.id} onAggregate={onAggregate} />
        ) : (
          <ServerDocumentCard document={document} />
        )}
      </div>

      <div>
        {status === "ANALYZING" ? (
          <AnalyzingCard />
        ) : status === "DOCUMENT_SCANNED" || status === "ANALYSIS_FAILED" ? (
          <AnalyzeCard
            applicationId={application.id}
            failed={status === "ANALYSIS_FAILED"}
            onAggregate={onAggregate}
            onRefetch={onRefetch}
          />
        ) : (
          <Card>
            <h4 className="mb-1 text-[13.5px] font-semibold text-ink">Analiz</h4>
            <p className="text-[12.5px] leading-5 text-ink-secondary">
              Belge yüklendikten sonra yapay zekâ okuması ve dokuz kontrol burada başlatılır.
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Upload form (status IDENTITY_VERIFIED)                                     */
/* -------------------------------------------------------------------------- */

function UploadForm({
  applicationId,
  onAggregate,
}: {
  applicationId: number;
  onAggregate: (aggregate: ApplicationAggregate) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [originalSeen, setOriginalSeen] = useState(false);
  const [scannedBy, setScannedBy] = useState("Şube görevlisi");
  const [pending, setPending] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [localPreviewUrl, setLocalPreviewUrl] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Object URLs leak unless revoked when replaced or unmounted.
  useEffect(() => {
    return () => {
      if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl);
    };
  }, [localPreviewUrl]);

  /** Shared by the picker and the dropzone — same state either way. */
  function applyFile(selected: File | null) {
    setFile(selected);
    setError(null);
    setLocalPreviewUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      // A local thumbnail is only safe for images; PDFs wait for the
      // server-rendered page (guide section 10, step 2).
      return selected && selected.type.startsWith("image/")
        ? URL.createObjectURL(selected)
        : null;
    });
  }

  function clearFile() {
    applyFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  const fileTypeInvalid = file !== null && !ACCEPTED_MIME.includes(file.type);
  const canSubmit = file !== null && !fileTypeInvalid && originalSeen && scannedBy.trim() !== "" && !pending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit || file === null) return;
    setPending(true);
    setUploadProgress({ phase: "uploading", loadedBytes: 0, totalBytes: file.size, percent: 0 });
    setError(null);
    try {
      await uploadDocument(
        applicationId,
        file,
        {
          original_seen: originalSeen,
          scanned_by: scannedBy.trim(),
        },
        undefined,
        setUploadProgress,
      );
      // The upload returns a DocumentView; the application status moved on the
      // server. Refetch the aggregate rather than patching state locally.
      onAggregate(await getApplication(applicationId));
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(cause);
      setPending(false);
      setUploadProgress(null);
    }
  }

  if (pending && file) {
    return <UploadingCard file={file} progress={uploadProgress} />;
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Card>
        <h4 className="mb-1 text-[13.5px] font-semibold text-ink">Belgenin aslını tarayın</h4>
        <p className="mb-3 text-[12.5px] leading-5 text-ink-secondary">
          PDF, PNG veya JPEG kabul edilir. Belgenin aslı görülmeden yükleme yapılamaz.
        </p>

        {/* Dropzone: one large click/drop target instead of a bare file input.
            The hidden input keeps native keyboard and screen-reader access. */}
        <label
          htmlFor="upload-file"
          onDragOver={(event) => {
            event.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragOver(false);
            applyFile(event.dataTransfer.files?.[0] ?? null);
          }}
          className={`flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-card border-2 border-dashed px-4 py-7 text-center transition-colors ${
            dragOver
              ? "border-info bg-info-soft"
              : "border-border-strong bg-surface-subtle hover:border-info hover:bg-surface-hover"
          }`}
        >
          <span
            className="grid size-10 place-items-center rounded-full border border-border bg-surface text-ink-secondary"
            aria-hidden
          >
            <UploadIcon width={18} height={18} />
          </span>
          <span className="text-[13px] font-medium text-ink">
            Dosyayı buraya sürükleyin{" "}
            <span className="text-info underline underline-offset-2">veya seçin</span>
          </span>
          <span className="text-[11.5px] text-ink-muted">PDF, PNG veya JPEG</span>
          <input
            ref={fileInputRef}
            id="upload-file"
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
            onChange={(event) => applyFile(event.target.files?.[0] ?? null)}
            className="sr-only"
          />
        </label>

        {file ? (
          <div className="mt-3 flex items-center gap-2.5 rounded-card border border-border bg-surface px-3 py-2">
            <span
              className="grid size-8 flex-none place-items-center rounded-control bg-surface-subtle font-mono text-[9.5px] font-semibold uppercase text-ink-secondary"
              aria-hidden
            >
              {file.name.split(".").pop()?.slice(0, 4) ?? "dosya"}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[12.5px] font-medium text-ink">{file.name}</span>
              <span className="block text-[11px] text-ink-muted">{formatFileSize(file.size)}</span>
            </span>
            <button
              type="button"
              onClick={clearFile}
              aria-label="Dosyayı kaldır"
              title="Dosyayı kaldır"
              className="grid size-7 flex-none place-items-center rounded-control text-ink-muted transition-colors hover:bg-surface-hover hover:text-ink"
            >
              <CloseIcon width={14} height={14} />
            </button>
          </div>
        ) : null}
        {fileTypeInvalid ? (
          <p className="mt-1.5 text-[12px] text-danger" role="alert">
            Desteklenmeyen dosya türü. PDF, PNG veya JPEG seçin.
          </p>
        ) : null}

        {localPreviewUrl ? (
          <img
            src={localPreviewUrl}
            alt="Seçilen belgenin yerel önizlemesi"
            className="mt-3 max-h-56 rounded-card border border-border object-contain"
          />
        ) : null}

        <div className="mt-4">
          <Field htmlFor="upload-scanned-by" label="Tarayan görevli">
            <Input
              id="upload-scanned-by"
              value={scannedBy}
              onChange={(event) => setScannedBy(event.target.value)}
            />
          </Field>
        </div>

        {/* Same consent-card treatment as step 1's identity attestation: the
            whole surface is the target and the checked state reads at a glance. */}
        <label
          className={`mt-4 flex cursor-pointer items-start gap-3 rounded-card border p-3.5 transition-colors ${
            originalSeen
              ? "border-success/40 bg-success-soft"
              : "border-border-strong bg-surface hover:bg-surface-hover"
          }`}
        >
          <Checkbox
            checked={originalSeen}
            onChange={(event) => setOriginalSeen(event.target.checked)}
          />
          <span className="text-[13px] leading-5 text-ink">
            <b className="font-semibold">Belgenin aslını şubede gördüm.</b>
            <span className="mt-0.5 block text-[11.5px] leading-4 text-ink-muted">
              Fotokopi veya ekran görüntüsüyle süreç ilerletilemez.
            </span>
          </span>
        </label>

        {error ? <InlineApiError error={error} /> : null}

        <div className="mt-4">
          <Button type="submit" variant="primary" disabled={!canSubmit}>
            {pending ? "Yükleniyor…" : "Belgeyi yükle"}
          </Button>
        </div>
      </Card>
    </form>
  );
}

function UploadingCard({
  file,
  progress,
}: {
  file: File;
  progress: UploadProgress | null;
}) {
  const elapsed = useElapsedSeconds();
  const processing = progress?.phase === "processing";
  const percent = progress?.percent;

  return (
    <Card>
      <div role="status" aria-live="polite">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-info">
              Belge alımı
            </p>
            <h4 className="mt-1 text-[14px] font-semibold text-ink">
              {processing ? "Dosya aktarıldı, sunucuda hazırlanıyor" : "Belge sunucuya aktarılıyor"}
            </h4>
          </div>
          <span className="rounded-pill bg-info-soft px-2.5 py-1 font-mono text-[11px] text-info">
            {formatElapsed(elapsed)}
          </span>
        </div>

        <div className="mt-4 overflow-hidden rounded-pill bg-surface-subtle" aria-hidden>
          {percent === null || percent === undefined ? (
            <span className="operation-progress-sweep block h-2 rounded-pill bg-info" />
          ) : (
            <span
              className={`block h-2 rounded-pill bg-info transition-[width] duration-200 ${
                processing ? "operation-progress-processing" : ""
              }`}
              style={{ width: `${percent}%` }}
            />
          )}
        </div>

        <div className="mt-2 flex items-center justify-between gap-3 text-[11.5px]">
          <span className="min-w-0 truncate text-ink-secondary" title={file.name}>
            {file.name} · {formatFileSize(file.size)}
          </span>
          <b className="flex-none font-mono font-semibold text-ink">
            {processing ? "Sunucu işliyor" : percent === null || percent === undefined ? "Aktarılıyor" : `%${percent}`}
          </b>
        </div>

        <div className="mt-4 rounded-card border border-border bg-surface-subtle px-3.5 py-3">
          <p className="text-[12.5px] leading-5 text-ink-secondary">
            {processing
              ? "PDF doğrulanıyor, sayfa görüntüleri hazırlanıyor ve belge kaydı oluşturuluyor."
              : "Gerçek aktarım yüzdesi dosyanın tarayıcıdan sunucuya gönderilen baytlarından hesaplanır."}
          </p>
          <p className="mt-1 text-[11.5px] text-ink-muted">Bu işlem tamamlanana kadar sayfadan ayrılmayın.</p>
        </div>
      </div>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Server document card (authoritative metadata + first page)                 */
/* -------------------------------------------------------------------------- */

function ServerDocumentCard({ document }: { document: DocumentView }) {
  return (
    <Card>
      <h4 className="mb-2 text-[13.5px] font-semibold text-ink">Taranan belge</h4>
      <img
        src={documentPageUrl(document.id, 1)}
        alt={`${document.original_filename} — 1. sayfa`}
        className="max-h-72 rounded-card border border-border object-contain"
      />
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12px]">
        <DocMeta label="Dosya" value={document.original_filename} />
        <DocMeta label="Tür" value={document.mime_type} />
        <DocMeta label="Boyut" value={formatFileSize(document.size_bytes)} />
        <DocMeta label="Sayfa" value={String(document.page_count)} />
        <DocMeta label="Tarayan" value={document.scanned_by} />
        <DocMeta
          label="SHA-256"
          value={`${document.document_sha256.slice(0, 12)}…`}
          mono
        />
      </dl>
    </Card>
  );
}

function DocMeta({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-ink-muted">{label}</dt>
      <dd className={`truncate text-ink ${mono ? "font-mono text-[11px]" : ""}`} title={value}>
        {value}
      </dd>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Analyze / analyzing / retry                                                */
/* -------------------------------------------------------------------------- */

function AnalyzingCard() {
  const elapsed = useElapsedSeconds();

  return (
    <Card>
      <div role="status" aria-live="polite">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-info">
              Canlı analiz
            </p>
            <h4 className="mt-1 text-[14px] font-semibold text-ink">Belge AI servisinde inceleniyor</h4>
          </div>
          <span className="rounded-pill bg-info-soft px-2.5 py-1 font-mono text-[11px] text-info">
            {formatElapsed(elapsed)}
          </span>
        </div>

        <div className="mt-4 h-2 overflow-hidden rounded-pill bg-surface-subtle" aria-hidden>
          <span className="operation-progress-sweep block h-full rounded-pill bg-info" />
        </div>

        <ol className="mt-4 space-y-2">
          {[
            ["Belge okuma ve alan çıkarma", "AI /extract"],
            ["Başvuru ve simüle sicil karşılaştırması", "Bank API → AI /analyze"],
            ["Dokuz kontrol ve karar raporu", "Sonuçların kalıcı kaydı"],
          ].map(([label, detail], index) => (
            <li key={label} className="flex items-center gap-2.5 rounded-control border border-border bg-surface-subtle px-3 py-2">
              <span className="grid size-5 flex-none place-items-center rounded-full bg-info-soft text-[10px] font-semibold text-info">
                {index + 1}
              </span>
              <span className="min-w-0 flex-1 text-[12px] font-medium text-ink">{label}</span>
              <span className="hidden text-[10.5px] text-ink-muted sm:block">{detail}</span>
            </li>
          ))}
        </ol>
      </div>
      <p className="mt-3 text-[11.5px] leading-5 text-ink-muted">
        Sunucu aşama yüzdesi yayınlamadığı için sahte yüzde yerine geçen süre gösterilir. Taranmış
        veya çok sayfalı belgelerde analiz bir dakikadan uzun sürebilir.
      </p>
    </Card>
  );
}

function useElapsedSeconds(): number {
  const [elapsed, setElapsed] = useState(0);
  const startedAt = useRef(Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt.current) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  return elapsed;
}

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function AnalyzeCard({
  applicationId,
  failed,
  onAggregate,
  onRefetch,
}: {
  applicationId: number;
  failed: boolean;
  onAggregate: (aggregate: ApplicationAggregate) => void;
  onRefetch: () => void;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function handleAnalyze() {
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      onAggregate(await analyzeApplication(applicationId));
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      if (cause instanceof ApiError && cause.code === "ANALYSIS_IN_PROGRESS") {
        // Another request already started the analysis; the server state is
        // authoritative — refetch and let the ANALYZING poll take over.
        onRefetch();
        return;
      }
      setError(cause);
    } finally {
      setPending(false);
    }
  }

  if (pending) return <AnalyzingCard />;

  return (
    <Card>
      <h4 className="mb-1 text-[13.5px] font-semibold text-ink">
        {failed ? "Analiz tamamlanamadı" : "Analiz için hazır"}
      </h4>
      <p className="mb-3 text-[12.5px] leading-5 text-ink-secondary">
        {failed
          ? "Belge korunuyor; yeniden denenebilir. Karar verilmedi, hiçbir veri kaybolmadı."
          : "Yapay zekâ belgeyi okur, dokuz kontrolü çalıştırır ve insan incelemesine sunar. Kararı her zaman görevli verir."}
      </p>

      {error ? <InlineApiError error={error} /> : null}

      <Button type="button" variant="primary" onClick={handleAnalyze} disabled={pending}>
        {failed ? "Analizi yeniden dene" : "Analizi başlat"}
      </Button>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Shared inline error                                                        */
/* -------------------------------------------------------------------------- */

function InlineApiError({ error }: { error: unknown }) {
  if (error instanceof ApiError) {
    return (
      <div
        className="mb-3 mt-3 rounded-panel border border-danger/30 bg-danger-soft px-3.5 py-2.5 text-[12.5px] text-danger"
        role="alert"
      >
        {error.message}
        {error.correlationId ? (
          <span className="mt-1 block font-mono text-[11px] text-ink-muted">
            İşlem no: {error.correlationId}
          </span>
        ) : null}
      </div>
    );
  }
  return <ErrorState error={error} />;
}
