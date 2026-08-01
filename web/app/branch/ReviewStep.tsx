"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import {
  ApiError,
  correctExtraction,
  decideApplication,
  documentPageUrl,
  getApplication,
} from "@/lib/api";
import {
  correctionCurrentValue,
  correctionFieldPath,
  decisionAvailability,
  type CorrectionTarget,
} from "@/lib/branch";
import {
  AUTHORITY_MODE_LABEL,
  formatAmountMinor,
  formatDate,
  formatInstant,
  ONBOARDING_VERDICT_LABEL,
  ONBOARDING_VERDICT_STATUS,
} from "@/lib/format";
import type {
  ApplicationAggregate,
  CheckResult,
  DocumentView,
  ExtractionResult,
} from "@/lib/types";

import { Card, SectionLabel } from "@/components/Layout";
import { SimBadge, StatusIcon, VerdictBanner } from "@/components/Status";
import { Button, Field, Input } from "@/components/UI";

/**
 * Step 3 — extraction, evidence, checks, corrections and decision (guide
 * section 10). Fixed layout order: verdict banner, document viewer, extracted
 * fields, review warnings, the nine checks in backend order (never sorted,
 * reason/evidence verbatim), correction history, decision controls.
 *
 * Nothing here derives a verdict: every status, check and decision is rendered
 * exactly as the backend returned it.
 */

const SIMULATED_CHECK_IDS = new Set(["registry_status", "registry_representative_match"]);

type EvidenceSelection = {
  page: number;
  quote: string | null;
  /** monotonically increasing, so re-selecting the same page re-flashes */
  key: number;
};

export function ReviewStep({
  aggregate,
  onAggregate,
}: {
  aggregate: ApplicationAggregate;
  onAggregate: (aggregate: ApplicationAggregate) => void;
}) {
  const { application, document, extraction, report, corrections, authority } = aggregate;
  const approved = application.status === "APPROVED";
  const [selection, setSelection] = useState<EvidenceSelection | null>(null);

  if (document === null || extraction === null || report === null) {
    // ANALYZED without its artifacts is a server-side inconsistency; render it
    // honestly instead of inventing content.
    return (
      <div className="p-4 text-[13px] text-ink-secondary">
        İnceleme verisi eksik görünüyor. Sayfayı yenileyin; sorun sürerse analiz yeniden
        çalıştırılmalıdır.
      </div>
    );
  }

  const showEvidence = (page: number, quote: string | null = null) => {
    const clamped = Math.min(Math.max(1, page), document.page_count);
    setSelection((current) => ({ page: clamped, quote, key: (current?.key ?? 0) + 1 }));
  };

  return (
    <div className="flex flex-col gap-4 p-4">
      {approved && authority ? (
        <ApprovalHinge mersis={application.mersis} authorityId={authority.id} />
      ) : null}

      <VerdictBanner
        status={ONBOARDING_VERDICT_STATUS[report.verdict]}
        title={ONBOARDING_VERDICT_LABEL[report.verdict]}
        detail={`Başvuru #${application.id} · ${application.company_name}`}
      />

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,440px)_minmax(0,1fr)]">
        <DocumentViewer document={document} selection={selection} onSelectPage={showEvidence} />

        <div className="flex flex-col gap-4">
          <ExtractionPanel extraction={extraction} onShowEvidence={showEvidence} />
          <ChecksPanel checks={report.checks} onShowEvidence={showEvidence} />
        </div>
      </div>

      <CorrectionsPanel
        applicationId={application.id}
        extraction={extraction}
        corrections={corrections}
        onAggregate={onAggregate}
        readOnly={approved}
      />

      {!approved ? (
        <DecisionControls
          applicationId={application.id}
          aggregate={aggregate}
          onAggregate={onAggregate}
        />
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Approval hinge — the bridge from Act 1 to Act 2                            */
/* -------------------------------------------------------------------------- */

function ApprovalHinge({ mersis, authorityId }: { mersis: string; authorityId: number }) {
  return (
    <div className="rounded-panel border border-success/25 bg-success-soft px-4 py-3.5">
      <div className="text-[13.5px] font-semibold text-success">
        <span aria-hidden>✓ </span>Başvuru onaylandı — yetki kaydı #{authorityId} oluşturuldu.
      </div>
      <p className="mt-1 text-[12.5px] text-ink-secondary">
        Belge bir daha istenmez. Sonraki tüm işlemler bu yetki kaydı üzerinden doğrulanır.
      </p>
      <div className="mt-2.5 flex flex-wrap gap-2">
        <Link
          href={`/authority/${mersis}`}
          className="inline-flex h-9 items-center rounded-control border border-ink bg-ink px-3.5 text-[13.5px] font-medium text-white hover:opacity-90"
        >
          Yetki kaydını gör
        </Link>
        <Link
          href={`/mobile?mersis=${mersis}`}
          className="inline-flex h-9 items-center rounded-control border border-border-strong bg-surface px-3.5 text-[13.5px] font-medium text-ink hover:bg-surface-hover"
        >
          Mobil şubeye geç
        </Link>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Document viewer with page tabs                                             */
/* -------------------------------------------------------------------------- */

function DocumentViewer({
  document,
  selection,
  onSelectPage,
}: {
  document: DocumentView;
  selection: EvidenceSelection | null;
  onSelectPage: (page: number) => void;
}) {
  const page = selection?.page ?? 1;
  const pages = Array.from({ length: document.page_count }, (_, index) => index + 1);

  return (
    <Card className="overflow-hidden !p-0">
      <div className="flex items-center gap-1 overflow-x-auto border-b border-border px-2 py-1.5" role="tablist" aria-label="Belge sayfaları">
        {pages.map((n) => (
          <button
            key={n}
            type="button"
            role="tab"
            aria-selected={n === page}
            onClick={() => onSelectPage(n)}
            className={`h-7 flex-none rounded-control px-2.5 text-[12px] font-medium transition-colors ${
              n === page ? "bg-ink text-white" : "text-ink-secondary hover:bg-surface-hover"
            }`}
          >
            Sayfa {n}
          </button>
        ))}
        <span className="ml-auto flex-none px-2 text-[11px] text-ink-muted">
          {document.original_filename}
        </span>
      </div>
      <div key={selection?.key ?? 0} className={selection ? "viewer-flash" : undefined}>
        <img
          src={documentPageUrl(document.id, page)}
          alt={`${document.original_filename} — ${page}. sayfa`}
          className="w-full bg-white object-contain"
        />
      </div>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Extracted fields                                                           */
/* -------------------------------------------------------------------------- */

/** Nulls render as "Okunamadı" and are never replaced by guesses (guide §11). */
function ValueOrUnread({ value }: { value: string | null }) {
  if (value === null || value === "") {
    return <span className="text-warning">Okunamadı</span>;
  }
  return <span className="text-ink">{value}</span>;
}

function ExtractionPanel({
  extraction,
  onShowEvidence,
}: {
  extraction: ExtractionResult;
  onShowEvidence: (page: number, quote?: string | null) => void;
}) {
  return (
    <Card>
      <SectionLabel>Belgeden okunan bilgiler</SectionLabel>

      <dl className="grid grid-cols-1 gap-x-5 gap-y-2 text-[12.5px] sm:grid-cols-2">
        <ExtractionRow label="Şirket unvanı">
          <ValueOrUnread value={extraction.company.name} />
        </ExtractionRow>
        <ExtractionRow label="Vergi numarası">
          <ValueOrUnread value={extraction.company.taxNumber} />
        </ExtractionRow>
        <ExtractionRow label="MERSİS">
          <ValueOrUnread value={extraction.company.mersisNumber} />
        </ExtractionRow>
        <ExtractionRow label="Belge geçerliliği">
          {extraction.validUntil === null ? (
            <ValueOrUnread value={null} />
          ) : (
            <span className="text-ink">{formatDate(extraction.validUntil)}</span>
          )}
        </ExtractionRow>
        <ExtractionRow label="Noter">
          <ValueOrUnread value={extraction.notary.name} />
        </ExtractionRow>
        <ExtractionRow label="Noter tarihi / yevmiye">
          <span className="text-ink">
            {extraction.notary.date ? formatDate(extraction.notary.date) : <ValueOrUnread value={null} />}
            {" · "}
            {extraction.notary.yevmiye ?? "—"}
          </span>
        </ExtractionRow>
      </dl>

      <div className="mt-3 rounded-card border border-border bg-surface-subtle px-3 py-2.5">
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-muted">
          Yetki hükmü
        </div>
        <blockquote className="font-paper text-[12px] italic leading-5 text-ink">
          “{extraction.evidence.authorityClause}”
        </blockquote>
        <button
          type="button"
          onClick={() => onShowEvidence(extraction.evidence.page, extraction.evidence.authorityClause)}
          className="mt-1.5 text-[12px] font-medium text-info underline-offset-2 hover:underline"
        >
          Belgede göster (sayfa {extraction.evidence.page})
        </button>
      </div>

      <div className="mt-3">
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-muted">
          Temsilciler
        </div>
        <ul className="flex flex-col gap-2">
          {extraction.representatives.map((rep) => (
            <li key={rep.id} className="rounded-card border border-border px-3 py-2 text-[12.5px]">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <b className="font-semibold text-ink">{rep.name}</b>
                <span className="text-[11px] text-ink-muted">({rep.id})</span>
                {rep.title ? <span className="text-ink-secondary">{rep.title}</span> : null}
              </div>
              <div className="mt-0.5 flex flex-wrap gap-x-4 gap-y-0.5 text-[12px] text-ink-secondary">
                <span>İmza: {AUTHORITY_MODE_LABEL[rep.mode]}</span>
                <span>TCKN: {rep.nationalId ?? "—"}</span>
                <span>Limit: {rep.limits === null ? "sınırsız" : formatAmountMinor(rep.limits)}</span>
                {rep.coSigners.length > 0 ? (
                  <span>Birlikte imza: {rep.coSigners.join(", ")}</span>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      </div>

      {extraction.fieldsNeedingReview.length > 0 ? (
        <div
          className="mt-3 rounded-card border border-warning/25 bg-warning-soft px-3 py-2.5 text-[12.5px] text-warning"
          role="alert"
        >
          <b className="font-semibold">
            <span aria-hidden>! </span>İncelenmesi gereken alanlar:
          </b>
          <ul className="mt-1 list-disc pl-5 text-ink-secondary">
            {extraction.fieldsNeedingReview.map((field) => (
              <li key={field} className="font-mono text-[11.5px]">
                {field}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Card>
  );
}

function ExtractionRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 border-b border-border/60 pb-1.5">
      <dt className="text-[11px] text-ink-muted">{label}</dt>
      <dd className="truncate">{children}</dd>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* The nine checks — backend order, verbatim content                          */
/* -------------------------------------------------------------------------- */

function ChecksPanel({
  checks,
  onShowEvidence,
}: {
  checks: CheckResult[];
  onShowEvidence: (page: number, quote?: string | null) => void;
}) {
  return (
    <Card>
      <SectionLabel>Dokuz kontrol</SectionLabel>
      <ol className="flex flex-col">
        {checks.map((check, index) => (
          <li
            key={check.id}
            className="flex items-start gap-2.5 border-b border-border/60 py-2 last:border-b-0"
          >
            <span className="mt-0.5 w-4 flex-none text-right text-[11px] text-ink-muted" aria-hidden>
              {index + 1}
            </span>
            <StatusIcon status={check.status} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-1.5 text-[13px] font-medium text-ink">
                {check.title}
                {SIMULATED_CHECK_IDS.has(check.id) ? <SimBadge label="simüle sicil" /> : null}
              </div>
              <p className="mt-0.5 text-[12.5px] leading-5 text-ink-secondary">{check.reason}</p>
              <CheckEvidence check={check} onShowEvidence={onShowEvidence} />
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

/**
 * Check evidence is a flexible dictionary (guide section 10): render known
 * safe scalars, link a valid page reference, and never assume a bounding box.
 */
function CheckEvidence({
  check,
  onShowEvidence,
}: {
  check: CheckResult;
  onShowEvidence: (page: number, quote?: string | null) => void;
}) {
  const entries = Object.entries(check.evidence).filter(
    ([, value]) => value !== null && value !== "",
  );
  if (entries.length === 0) return null;

  const pageEntry = entries.find(
    ([key, value]) => key === "page" && typeof value === "number" && Number.isInteger(value) && value >= 1,
  );
  const quoteEntry = entries.find(([key]) => key === "quote");

  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11.5px] text-ink-muted">
      {entries
        .filter(([key]) => key !== "page" && key !== "quote")
        .map(([key, value]) => (
          <span key={key} className="max-w-full truncate">
            {key}: <span className="text-ink-secondary">{String(value)}</span>
          </span>
        ))}
      {quoteEntry ? (
        <span className="max-w-full truncate italic text-ink-secondary">“{String(quoteEntry[1])}”</span>
      ) : null}
      {pageEntry ? (
        <button
          type="button"
          onClick={() =>
            onShowEvidence(pageEntry[1] as number, quoteEntry ? String(quoteEntry[1]) : null)
          }
          className="font-medium text-info underline-offset-2 hover:underline"
        >
          Belgede göster (sayfa {String(pageEntry[1])})
        </button>
      ) : null}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Corrections — append-only history + guarded form                           */
/* -------------------------------------------------------------------------- */

type TargetOption = { key: string; label: string; target: CorrectionTarget };

function targetOptions(extraction: ExtractionResult): TargetOption[] {
  const options: TargetOption[] = [
    { key: "company.name", label: "Şirket unvanı", target: { kind: "company", field: "name" } },
    {
      key: "company.taxNumber",
      label: "Vergi numarası",
      target: { kind: "company", field: "taxNumber" },
    },
    {
      key: "company.mersisNumber",
      label: "MERSİS numarası",
      target: { kind: "company", field: "mersisNumber" },
    },
    { key: "validUntil", label: "Belge geçerlilik tarihi", target: { kind: "validUntil" } },
  ];
  for (const rep of extraction.representatives) {
    options.push({
      key: `representatives[${rep.id}].name`,
      label: `Temsilci adı — ${rep.name} (${rep.id})`,
      target: { kind: "representative", sourceId: rep.id, field: "name" },
    });
    options.push({
      key: `representatives[${rep.id}].mode`,
      label: `İmza şekli — ${rep.name} (${rep.id})`,
      target: { kind: "representative", sourceId: rep.id, field: "mode" },
    });
  }
  return options;
}

function CorrectionsPanel({
  applicationId,
  extraction,
  corrections,
  onAggregate,
  readOnly,
}: {
  applicationId: number;
  extraction: ExtractionResult;
  corrections: ApplicationAggregate["corrections"];
  onAggregate: (aggregate: ApplicationAggregate) => void;
  readOnly: boolean;
}) {
  return (
    <Card>
      <SectionLabel>Düzeltme geçmişi</SectionLabel>

      {corrections.length === 0 ? (
        <p className="text-[12.5px] text-ink-muted">Bu başvuruda düzeltme yapılmadı.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {corrections.map((correction) => (
            <li
              key={correction.id}
              className="rounded-card border border-border px-3 py-2 text-[12.5px]"
            >
              <div className="flex flex-wrap items-baseline gap-x-2">
                <code className="font-mono text-[11.5px] text-ink">{correction.field_path}</code>
                <span className="text-ink-secondary">
                  <s>{formatCorrectionValue(correction.old_value_json.value)}</s>
                  {" → "}
                  <b className="font-semibold text-ink">
                    {formatCorrectionValue(correction.new_value_json.value)}
                  </b>
                </span>
              </div>
              <div className="mt-0.5 text-[11.5px] text-ink-muted">
                {correction.reviewer} · {formatInstant(correction.created_at)} — {correction.reason}
              </div>
            </li>
          ))}
        </ul>
      )}

      {!readOnly ? (
        <CorrectionForm
          applicationId={applicationId}
          extraction={extraction}
          onAggregate={onAggregate}
        />
      ) : null}
    </Card>
  );
}

function formatCorrectionValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Okunamadı";
  return String(value);
}

function CorrectionForm({
  applicationId,
  extraction,
  onAggregate,
}: {
  applicationId: number;
  extraction: ExtractionResult;
  onAggregate: (aggregate: ApplicationAggregate) => void;
}) {
  const options = targetOptions(extraction);
  const [targetKey, setTargetKey] = useState(options[0]?.key ?? "company.name");
  const [newValue, setNewValue] = useState("");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [stale, setStale] = useState(false);

  const selected = options.find((option) => option.key === targetKey) ?? options[0];
  if (!selected) return null;
  const target = selected.target;
  const currentValue =
    correctionCurrentValue(extraction, target) as string | null | undefined;
  const isMode = target.kind === "representative" && target.field === "mode";
  const isDate = target.kind === "validUntil";

  const canSubmit = !pending && reason.trim() !== "" && newValue.trim() !== "";

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    setPending(true);
    setError(null);
    try {
      const result = await correctExtraction(applicationId, {
        reason: reason.trim(),
        corrections: [
          {
            field_path: correctionFieldPath(target),
            // Always the currently *displayed* value (guide section 10) — the
            // backend rejects the write with 409 STALE_CORRECTION if it moved.
            expected_old_value: currentValue ?? null,
            new_value: newValue.trim(),
          },
        ],
      });
      onAggregate(result);
      setNewValue("");
      setReason("");
      setStale(false);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      if (cause instanceof ApiError && cause.code === "STALE_CORRECTION") {
        // Refetch so the comparison below shows the *new* server value while
        // the operator's proposed value stays in the input (guide section 10).
        setStale(true);
        setError(cause);
        try {
          onAggregate(await getApplication(applicationId));
        } catch {
          /* the visible STALE_CORRECTION error already asks for a reload */
        }
      } else {
        setError(cause);
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-4 border-t border-border pt-3.5" noValidate>
      <div className="mb-2 text-[12.5px] font-semibold text-ink">Düzeltme ekle</div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Field htmlFor="correction-target" label="Alan">
          <select
            id="correction-target"
            value={targetKey}
            onChange={(event) => {
              setTargetKey(event.target.value);
              setNewValue("");
              setStale(false);
              setError(null);
            }}
            className="h-9 w-full rounded-control border border-border-strong bg-surface px-3 text-[13px] text-ink"
          >
            {options.map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>

        <Field
          htmlFor="correction-new-value"
          label="Yeni değer"
          hint={`Ekranda görünen değer: ${formatCorrectionValue(currentValue)}`}
        >
          {isMode ? (
            <select
              id="correction-new-value"
              value={newValue}
              onChange={(event) => setNewValue(event.target.value)}
              className="h-9 w-full rounded-control border border-border-strong bg-surface px-3 text-[13px] text-ink"
            >
              <option value="">Seçin…</option>
              <option value="SOLE">SOLE — münferit</option>
              <option value="JOINT">JOINT — müşterek</option>
            </select>
          ) : (
            <Input
              id="correction-new-value"
              type={isDate ? "date" : "text"}
              value={newValue}
              onChange={(event) => setNewValue(event.target.value)}
            />
          )}
        </Field>
      </div>

      <div className="mt-3">
        <Field
          htmlFor="correction-reason"
          label="Gerekçe"
          hint="Örn. Noter belgesiyle tekrar kontrol edildi."
        >
          <Input
            id="correction-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </Field>
      </div>

      {stale ? (
        <div
          className="mt-3 rounded-card border border-warning/25 bg-warning-soft px-3 py-2.5 text-[12.5px] text-ink-secondary"
          role="alert"
        >
          <b className="font-semibold text-warning">
            <span aria-hidden>! </span>Değer bu sırada değişti.
          </b>{" "}
          Sunucudaki güncel değer: <b className="font-semibold text-ink">{formatCorrectionValue(currentValue)}</b>.
          Önerdiğiniz değer alanda korunuyor; güncel değerle karşılaştırıp gerekiyorsa yeniden
          gönderin.
        </div>
      ) : error instanceof ApiError ? (
        <div className="mt-3 rounded-card border border-danger/30 bg-danger-soft px-3 py-2.5 text-[12.5px] text-danger" role="alert">
          {error.message}
          {error.correlationId ? (
            <span className="mt-1 block font-mono text-[11px] text-ink-muted">
              İşlem no: {error.correlationId}
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="mt-3">
        <Button type="submit" disabled={!canSubmit}>
          {pending ? "Kaydediliyor…" : "Düzeltmeyi kaydet ve yeniden analiz et"}
        </Button>
      </div>
    </form>
  );
}

/* -------------------------------------------------------------------------- */
/* Decision controls — usability filter over a backend-enforced matrix        */
/* -------------------------------------------------------------------------- */

type DecisionPending = "approve" | "override" | "request_document" | "escalate" | null;

function DecisionControls({
  applicationId,
  aggregate,
  onAggregate,
}: {
  applicationId: number;
  aggregate: ApplicationAggregate;
  onAggregate: (aggregate: ApplicationAggregate) => void;
}) {
  const availability = decisionAvailability(aggregate.report, aggregate.extraction);
  const [note, setNote] = useState("");
  const [justification, setJustification] = useState("");
  const [showOverride, setShowOverride] = useState(false);
  const [pending, setPending] = useState<DecisionPending>(null);
  const [error, setError] = useState<unknown>(null);
  const justificationRef = useRef<HTMLTextAreaElement>(null);

  async function decide(
    action: "approve" | "request_document" | "escalate",
    kind: Exclude<DecisionPending, null>,
    extras: { note?: string; override_justification?: string } = {},
  ) {
    if (pending) return;
    setPending(kind);
    setError(null);
    try {
      onAggregate(await decideApplication(applicationId, { action, ...extras }));
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(cause);
      if (cause instanceof ApiError) {
        if (cause.code === "OVERRIDE_JUSTIFICATION_REQUIRED") {
          setShowOverride(true);
          setTimeout(() => justificationRef.current?.focus(), 0);
        }
        if (cause.code === "INVALID_STATE_TRANSITION" || cause.code === "APPROVAL_NOT_ALLOWED") {
          // Another state is authoritative — refetch and re-render from it.
          try {
            onAggregate(await getApplication(applicationId));
          } catch {
            /* keep the original, more meaningful error on screen */
          }
        }
      }
    } finally {
      setPending(null);
    }
  }

  return (
    <Card>
      <SectionLabel>Karar</SectionLabel>

      {availability.approveBlockedReason ? (
        <p className="mb-3 text-[12.5px] text-ink-secondary">
          <span className="font-semibold text-danger">
            <span aria-hidden>× </span>Onay kapalı.
          </span>{" "}
          {availability.approveBlockedReason}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        {availability.approve === "normal" ? (
          <Button
            type="button"
            variant="primary"
            disabled={pending !== null}
            onClick={() => decide("approve", "approve")}
          >
            {pending === "approve" ? "Onaylanıyor…" : "Onayla ve yetki kaydı oluştur"}
          </Button>
        ) : null}

        {availability.requestDocument ? (
          <Button
            type="button"
            disabled={pending !== null}
            onClick={() => decide("request_document", "request_document", { note: note.trim() || undefined })}
          >
            {pending === "request_document" ? "Gönderiliyor…" : "Yeni belge iste"}
          </Button>
        ) : null}

        {availability.escalate ? (
          <Button
            type="button"
            disabled={pending !== null}
            onClick={() => decide("escalate", "escalate", { note: note.trim() || undefined })}
          >
            {pending === "escalate" ? "Gönderiliyor…" : "Uyum birimine gönder"}
          </Button>
        ) : null}
      </div>

      <div className="mt-3 max-w-xl">
        <Field htmlFor="decision-note" label="Not (isteğe bağlı)">
          <Input
            id="decision-note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Örn. Okunaklı yeni nüsha istendi"
          />
        </Field>
      </div>

      {availability.approve === "override" ? (
        <div className="mt-4 rounded-card border border-warning/25 bg-warning-soft px-3.5 py-3">
          <div className="text-[12.5px] font-semibold text-warning">
            <span aria-hidden>! </span>İstisnai onay — ikinci imza şartına rağmen
          </div>
          <p className="mt-1 text-[12px] leading-5 text-ink-secondary">
            Normal akış yeni belge istemek veya uyum birimine göndermektir. İstisnai onay
            yazılı gerekçe ister ve denetim izine geçer.
          </p>
          {!showOverride ? (
            <Button type="button" className="mt-2" onClick={() => setShowOverride(true)}>
              İstisnai onayı aç
            </Button>
          ) : (
            <div className="mt-2">
              <label
                htmlFor="override-justification"
                className="mb-1.5 block text-[11.5px] font-medium text-ink-secondary"
              >
                Onay gerekçesi (zorunlu)
              </label>
              <textarea
                id="override-justification"
                ref={justificationRef}
                value={justification}
                onChange={(event) => setJustification(event.target.value)}
                rows={2}
                className="w-full rounded-control border border-border-strong bg-surface px-3 py-2 text-[13px] text-ink placeholder:text-ink-muted focus-visible:border-info"
                placeholder="Gerekçeyi yazın…"
              />
              <Button
                type="button"
                variant="danger"
                className="mt-2"
                disabled={pending !== null || justification.trim() === ""}
                onClick={() =>
                  decide("approve", "override", {
                    override_justification: justification.trim(),
                    note: note.trim() || undefined,
                  })
                }
              >
                {pending === "override" ? "Onaylanıyor…" : "Gerekçeyle onayla"}
              </Button>
            </div>
          )}
        </div>
      ) : null}

      {error instanceof ApiError ? (
        <div
          className="mt-3 rounded-card border border-danger/30 bg-danger-soft px-3.5 py-2.5 text-[12.5px] text-danger"
          role="alert"
        >
          {error.message}
          {error.correlationId ? (
            <span className="mt-1 block font-mono text-[11px] text-ink-muted">
              İşlem no: {error.correlationId}
            </span>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
