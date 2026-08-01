"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  analyzeApplication,
  documentPageUrl,
  getApplication,
  uploadDocument,
} from "@/lib/api";
import { formatFileSize } from "@/lib/format";
import type { ApplicationAggregate, DocumentView } from "@/lib/types";

import { Card } from "@/components/Layout";
import { ErrorState } from "@/components/States";
import { Button, Checkbox, Field, Input } from "@/components/UI";

/**
 * Step 2 — original document upload and analysis (guide section 10).
 *
 * Honesty rules baked in here:
 * - upload progress is indeterminate ("Belge yükleniyor") because the fetch
 *   transport exposes no byte progress — no fabricated percentages;
 * - analysis progress is calm text without invented stages, because the
 *   backend does not stream stages;
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
  const [error, setError] = useState<unknown>(null);
  const [localPreviewUrl, setLocalPreviewUrl] = useState<string | null>(null);

  // Object URLs leak unless revoked when replaced or unmounted.
  useEffect(() => {
    return () => {
      if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl);
    };
  }, [localPreviewUrl]);

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
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

  const fileTypeInvalid = file !== null && !ACCEPTED_MIME.includes(file.type);
  const canSubmit = file !== null && !fileTypeInvalid && originalSeen && scannedBy.trim() !== "" && !pending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit || file === null) return;
    setPending(true);
    setError(null);
    try {
      await uploadDocument(applicationId, file, {
        original_seen: originalSeen,
        scanned_by: scannedBy.trim(),
      });
      // The upload returns a DocumentView; the application status moved on the
      // server. Refetch the aggregate rather than patching state locally.
      onAggregate(await getApplication(applicationId));
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(cause);
      setPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Card>
        <h4 className="mb-1 text-[13.5px] font-semibold text-ink">Belgenin aslını tarayın</h4>
        <p className="mb-3 text-[12.5px] leading-5 text-ink-secondary">
          PDF, PNG veya JPEG kabul edilir. Belgenin aslı görülmeden yükleme yapılamaz.
        </p>

        <Field htmlFor="upload-file" label="İmza sirküleri dosyası">
          <input
            id="upload-file"
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
            onChange={handleFileChange}
            className="block w-full text-[13px] text-ink file:mr-3 file:h-9 file:cursor-pointer file:rounded-control file:border file:border-border-strong file:bg-surface file:px-3.5 file:text-[13px] file:font-medium file:text-ink hover:file:bg-surface-hover"
          />
        </Field>

        {file ? (
          <p className="mt-2 text-[12px] text-ink-secondary">
            Seçilen dosya: <b className="font-medium text-ink">{file.name}</b> ·{" "}
            {formatFileSize(file.size)}
          </p>
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

        <label className="mt-4 flex items-start gap-2.5 text-[13px] text-ink">
          <Checkbox
            checked={originalSeen}
            onChange={(event) => setOriginalSeen(event.target.checked)}
          />
          <span>
            Belgenin <b className="font-semibold">aslını</b> şubede gördüm.
            <span className="block text-[11.5px] text-ink-muted">
              Fotokopi veya ekran görüntüsüyle süreç ilerletilemez.
            </span>
          </span>
        </label>

        {pending ? (
          <div className="mt-4 flex items-center gap-2.5 text-[13px] text-ink-secondary" role="status" aria-live="polite">
            <span className="h-1.5 w-40 overflow-hidden rounded-pill bg-surface-subtle">
              <span className="block h-full w-1/3 animate-pulse rounded-pill bg-info" />
            </span>
            Belge yükleniyor…
          </div>
        ) : null}

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
  return (
    <Card>
      <h4 className="mb-1 text-[13.5px] font-semibold text-ink">Belge analiz ediliyor</h4>
      <div className="mt-2 flex items-center gap-2.5 text-[13px] text-ink-secondary" role="status" aria-live="polite">
        <span className="h-1.5 w-40 overflow-hidden rounded-pill bg-surface-subtle">
          <span className="block h-full w-1/3 animate-pulse rounded-pill bg-info" />
        </span>
        Bu işlem biraz sürebilir.
      </div>
      <p className="mt-3 text-[12px] leading-5 text-ink-muted">
        Sonuç sunucudan geldiğinde inceleme ekranı açılır; sayfayı yenileseniz de kaldığı
        yerden devam eder.
      </p>
    </Card>
  );
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
