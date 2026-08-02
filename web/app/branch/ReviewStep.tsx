"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

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
  formatActor,
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

import { ChevronDownIcon, PencilIcon } from "@/components/Icon";
import { Card, SectionLabel } from "@/components/Layout";
import { SimBadge, StatusIcon, VerdictBanner } from "@/components/Status";
import { Button, Field, Input } from "@/components/UI";

/** Step 3 — extracted information, checks, corrections, and decision. */

const SIMULATED_CHECK_IDS = new Set(["registry_status", "registry_representative_match"]);

type EvidenceSelection = {
  page: number;
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
  // Which correction target the editor is aimed at. Lifted here so the inline
  // pencil buttons on the extracted fields can aim it — the editor itself and
  // the request it sends are unchanged.
  const [targetKey, setTargetKey] = useState<string | null>(null);
  const correctionsRef = useRef<HTMLDivElement>(null);

  const editField = (key: string) => {
    setTargetKey(key);
    correctionsRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  if (document === null || extraction === null || report === null) {
    // An analyzed application cannot be reviewed without all three artifacts.
    return (
      <div className="p-4 text-[13px] text-ink-secondary">
        İnceleme verisi eksik görünüyor. Sayfayı yenileyin; sorun sürerse analiz yeniden
        çalıştırılmalıdır.
      </div>
    );
  }

  const selectPage = (page: number) => {
    const clamped = Math.min(Math.max(1, page), document.page_count);
    setSelection((current) => ({ page: clamped, key: (current?.key ?? 0) + 1 }));
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
        <DocumentViewer document={document} selection={selection} onSelectPage={selectPage} />

        <div className="flex flex-col gap-4">
          <ExtractionPanel
            extraction={extraction}
            onEditField={approved ? null : editField}
            activeTargetKey={targetKey}
          />
          <ChecksPanel checks={report.checks} />
        </div>
      </div>

      <div ref={correctionsRef}>
        <CorrectionsPanel
          applicationId={application.id}
          extraction={extraction}
          corrections={corrections}
          onAggregate={onAggregate}
          readOnly={approved}
          targetKey={targetKey}
          onTargetKeyChange={setTargetKey}
        />
      </div>

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
    <Card className="overflow-hidden p-0!">
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

/** Missing extracted values are shown as unreadable rather than guessed. */
function ValueOrUnread({ value }: { value: string | null }) {
  if (value === null || value === "") {
    return <span className="text-warning">Okunamadı</span>;
  }
  return <span className="text-ink">{value}</span>;
}

function ExtractionPanel({
  extraction,
  onEditField,
  activeTargetKey,
}: {
  extraction: ExtractionResult;
  /** `null` once the application is approved — corrections are closed then. */
  onEditField: ((targetKey: string) => void) | null;
  activeTargetKey: string | null;
}) {
  return (
    <Card>
      <SectionLabel>Belgeden okunan bilgiler</SectionLabel>

      <dl className="grid grid-cols-1 gap-x-5 gap-y-2 text-[12.5px] sm:grid-cols-2">
        <ExtractionRow
          label="Şirket unvanı"
          targetKey="company.name"
          onEditField={onEditField}
          activeTargetKey={activeTargetKey}
        >
          <ValueOrUnread value={extraction.company.name} />
        </ExtractionRow>
        <ExtractionRow
          label="Vergi numarası"
          targetKey="company.taxNumber"
          onEditField={onEditField}
          activeTargetKey={activeTargetKey}
        >
          <ValueOrUnread value={extraction.company.taxNumber} />
        </ExtractionRow>
        <ExtractionRow
          label="MERSİS"
          targetKey="company.mersisNumber"
          onEditField={onEditField}
          activeTargetKey={activeTargetKey}
        >
          <ValueOrUnread value={extraction.company.mersisNumber} />
        </ExtractionRow>
        <ExtractionRow
          label="Belge geçerliliği"
          targetKey="validUntil"
          onEditField={onEditField}
          activeTargetKey={activeTargetKey}
        >
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
      </div>

      <RepresentativesAccordion
        representatives={extraction.representatives}
        onEditField={onEditField}
        activeTargetKey={activeTargetKey}
      />
    </Card>
  );
}

function RepresentativesAccordion({
  representatives,
  onEditField,
  activeTargetKey,
}: {
  representatives: ExtractionResult["representatives"];
  onEditField: ((targetKey: string) => void) | null;
  activeTargetKey: string | null;
}) {
  const [open, setOpen] = useState(false);
  const hasActiveRepresentative = representatives.some(
    (rep) =>
      activeTargetKey === `representatives[${rep.id}].name` ||
      activeTargetKey === `representatives[${rep.id}].mode`,
  );

  // A representative selected from the correction editor must remain visible,
  // even if the parent group was previously collapsed.
  useEffect(() => {
    if (hasActiveRepresentative) setOpen(true);
  }, [hasActiveRepresentative]);

  return (
    <section
      className={`mt-3 overflow-hidden rounded-card border transition-colors ${
        hasActiveRepresentative ? "border-info" : "border-border"
      }`}
    >
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 bg-surface-subtle px-3 py-3 text-left transition-colors hover:bg-cyan-soft"
      >
        <ChevronDownIcon
          width={15}
          height={15}
          className={`flex-none text-ink-muted transition-transform duration-150 ${
            open ? "" : "-rotate-90"
          }`}
        />
        <span className="min-w-0 flex-1">
          <span className="block text-[12.5px] font-semibold text-ink">Temsilciler</span>
          <span className="mt-0.5 block text-[11px] text-ink-muted">
            Belgeden okunan yetkili kişiler
          </span>
        </span>
        <span className="flex-none rounded-pill border border-border bg-surface px-2.5 py-0.5 text-[11px] font-medium text-ink-secondary shadow-panel">
          {representatives.length} kişi
        </span>
      </button>

      {open ? (
        <div className="border-t border-border bg-surface px-2.5 py-2.5">
          {representatives.length > 0 ? (
            <ul className="flex flex-col gap-1.5">
              {representatives.map((rep) => (
                <RepresentativeAccordionItem
                  key={rep.id}
                  representative={rep}
                  onEditField={onEditField}
                  activeTargetKey={activeTargetKey}
                />
              ))}
            </ul>
          ) : (
            <p className="px-1 py-2 text-[12px] text-ink-muted">
              Belgede temsilci bilgisi okunamadı.
            </p>
          )}
        </div>
      ) : null}
    </section>
  );
}

function ExtractionRow({
  label,
  children,
  targetKey,
  onEditField,
  activeTargetKey,
}: {
  label: string;
  children: React.ReactNode;
  /** Omitted for read-only fields such as notary information. */
  targetKey?: string;
  onEditField?: ((targetKey: string) => void) | null;
  activeTargetKey?: string | null;
}) {
  const editable = targetKey !== undefined && onEditField != null;
  const isActive = editable && activeTargetKey === targetKey;
  return (
    <div
      className={`group min-w-0 border-b pb-1.5 ${
        isActive ? "border-info" : "border-border/60"
      }`}
    >
      <dt className="text-[11px] text-ink-muted">{label}</dt>
      <dd className="flex min-w-0 items-center gap-1">
        <span className="min-w-0 flex-1 truncate">{children}</span>
        {editable ? (
          <button
            type="button"
            onClick={() => onEditField(targetKey)}
            aria-label={`${label} alanını düzelt`}
            title={`${label} alanını düzelt`}
            className={`grid size-6 flex-none place-items-center rounded-control text-ink-muted transition-opacity hover:bg-surface-hover hover:text-ink focus-visible:opacity-100 ${
              isActive ? "text-info opacity-100" : "opacity-0 group-hover:opacity-100"
            }`}
          >
            <PencilIcon width={13} height={13} />
          </button>
        ) : null}
      </dd>
    </div>
  );
}

function RepresentativeAccordionItem({
  representative: rep,
  onEditField,
  activeTargetKey,
}: {
  representative: ExtractionResult["representatives"][number];
  onEditField: ((targetKey: string) => void) | null;
  activeTargetKey: string | null;
}) {
  const [open, setOpen] = useState(false);
  const nameKey = `representatives[${rep.id}].name`;
  const modeKey = `representatives[${rep.id}].mode`;
  const targeted = activeTargetKey === nameKey || activeTargetKey === modeKey;

  return (
    <li
      className={`overflow-hidden rounded-card border ${
        targeted ? "border-info" : "border-border"
      }`}
    >
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface-hover"
      >
        <ChevronDownIcon
          width={14}
          height={14}
          className={`flex-none text-ink-muted transition-transform duration-150 ${
            open ? "" : "-rotate-90"
          }`}
        />
        <span className="min-w-0 flex-1 truncate text-[12.5px] font-semibold text-ink">
          {rep.name}
        </span>
        <span className="flex-none rounded-pill bg-surface-subtle px-2 py-0.5 text-[11px] text-ink-secondary">
          {AUTHORITY_MODE_LABEL[rep.mode]}
        </span>
      </button>

      {open ? (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 border-t border-border px-3 py-2.5 text-[12px]">
          <RepDetail label="Belgedeki kayıt" value={`#${rep.id.replace(/^rep-/, "")}`} />
          <RepDetail label="Görev" value={rep.title ?? "—"} />
          <RepDetail label="TCKN" value={rep.nationalId ?? "—"} mono />
          <RepDetail
            label="Limit"
            value={rep.limits === null ? "sınırsız" : formatAmountMinor(rep.limits)}
          />
          {rep.coSigners.length > 0 ? (
            <RepDetail label="Birlikte imza" value={rep.coSigners.join(", ")} wide />
          ) : null}

          {onEditField ? (
            <div className="col-span-2 flex flex-wrap gap-1.5 pt-1">
              <button
                type="button"
                onClick={() => onEditField(nameKey)}
                className="inline-flex h-7 items-center gap-1.5 rounded-control border border-border-strong bg-surface px-2.5 text-[11.5px] font-medium text-ink hover:bg-surface-hover"
              >
                <PencilIcon width={12} height={12} />
                Adı düzelt
              </button>
              <button
                type="button"
                onClick={() => onEditField(modeKey)}
                className="inline-flex h-7 items-center gap-1.5 rounded-control border border-border-strong bg-surface px-2.5 text-[11.5px] font-medium text-ink hover:bg-surface-hover"
              >
                <PencilIcon width={12} height={12} />
                İmza şeklini düzelt
              </button>
            </div>
          ) : null}
        </dl>
      ) : null}
    </li>
  );
}

function RepDetail({
  label,
  value,
  mono = false,
  wide = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
  wide?: boolean;
}) {
  return (
    <div className={`min-w-0 ${wide ? "col-span-2" : ""}`}>
      <dt className="text-[11px] text-ink-muted">{label}</dt>
      <dd className={`truncate text-ink ${mono ? "font-mono text-[11.5px]" : ""}`} title={value}>
        {value}
      </dd>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* The nine checks                                                            */
/* -------------------------------------------------------------------------- */

function ChecksPanel({ checks }: { checks: CheckResult[] }) {
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
              <CheckEvidence check={check} />
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

/**
 * Check evidence is a flexible dictionary; render safe scalar values only.
 */
function CheckEvidence({ check }: { check: CheckResult }) {
  const entries = Object.entries(check.evidence).filter(
    ([, value]) => value !== null && value !== "",
  );
  if (entries.length === 0) return null;

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
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Corrections — append-only history + guarded form                           */
/* -------------------------------------------------------------------------- */

/** One-tap reasons for the most common review corrections. */
const QUICK_REASONS = [
  "Noter belgesiyle tekrar kontrol edildi.",
  "Belgede okunaklı biçimde farklı yazıyor.",
  "Sistem yanlış okumuş.",
];

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
      label: `Temsilci adı — ${rep.name}`,
      target: { kind: "representative", sourceId: rep.id, field: "name" },
    });
    options.push({
      key: `representatives[${rep.id}].mode`,
      label: `İmza şekli — ${rep.name}`,
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
  targetKey,
  onTargetKeyChange,
}: {
  applicationId: number;
  extraction: ExtractionResult;
  corrections: ApplicationAggregate["corrections"];
  onAggregate: (aggregate: ApplicationAggregate) => void;
  readOnly: boolean;
  targetKey: string | null;
  onTargetKeyChange: (targetKey: string | null) => void;
}) {
  const options = targetOptions(extraction);

  return (
    <Card>
      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
        <SectionLabel>Düzeltmeler</SectionLabel>
        {!readOnly && targetKey === null ? (
          <Button
            type="button"
            className="h-7! px-2.5! text-[12px]!"
            onClick={() => onTargetKeyChange(options[0]?.key ?? "company.name")}
          >
            <PencilIcon width={12} height={12} />
            Düzeltme ekle
          </Button>
        ) : null}
      </div>

      {corrections.length === 0 ? (
        <p className="text-[12.5px] text-ink-muted">
          Bu başvuruda düzeltme yapılmadı.
          {!readOnly ? " Bir alanı düzeltmek için üstteki kalem simgesini kullanın." : ""}
        </p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {corrections.map((correction) => (
            <li
              key={correction.id}
              className="rounded-card border border-border px-3 py-2 text-[12.5px]"
            >
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="rounded-pill bg-surface-subtle px-2 py-0.5 text-[11px] font-medium text-ink-secondary">
                  {options.find((option) => option.key === correction.field_path)?.label ??
                    "Düzeltilen alan"}
                </span>
                <span className="text-ink-secondary">
                  <s className="text-ink-muted">
                    {formatCorrectionValue(correction.old_value_json.value)}
                  </s>
                  <span aria-hidden> → </span>
                  <b className="font-semibold text-ink">
                    {formatCorrectionValue(correction.new_value_json.value)}
                  </b>
                </span>
              </div>
              <div className="mt-0.5 text-[11.5px] text-ink-muted">
                {formatActor(correction.reviewer)} · {formatInstant(correction.created_at)} — {correction.reason}
              </div>
            </li>
          ))}
        </ul>
      )}

      {!readOnly && targetKey !== null ? (
        <CorrectionForm
          applicationId={applicationId}
          extraction={extraction}
          onAggregate={onAggregate}
          targetKey={targetKey}
          onTargetKeyChange={onTargetKeyChange}
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
  targetKey,
  onTargetKeyChange,
}: {
  applicationId: number;
  extraction: ExtractionResult;
  onAggregate: (aggregate: ApplicationAggregate) => void;
  targetKey: string;
  onTargetKeyChange: (targetKey: string | null) => void;
}) {
  const options = targetOptions(extraction);
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
            // Prevents overwriting a correction made after this screen loaded.
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
        // Keep the proposed value while refreshing the current saved value.
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
    <form
      onSubmit={handleSubmit}
      className="mt-4 rounded-card border border-info/30 bg-info-soft/40 p-3.5"
      noValidate
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-[12.5px] font-semibold text-ink">
          <PencilIcon width={13} height={13} />
          Alanı düzelt
        </span>
        <button
          type="button"
          onClick={() => onTargetKeyChange(null)}
          className="text-[11.5px] font-medium text-ink-secondary underline-offset-2 hover:text-ink hover:underline"
        >
          Vazgeç
        </button>
      </div>

      <Field htmlFor="correction-target" label="Düzeltilecek alan">
        <select
          id="correction-target"
          value={targetKey}
          onChange={(event) => {
            onTargetKeyChange(event.target.value);
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

      {/* Before → after, so the reviewer always sees what they are replacing. */}
      <div className="mt-3 grid items-end gap-2 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
        <div className="min-w-0">
          <span className="mb-1.5 block text-[11.5px] font-medium text-ink-secondary">
            Belgeden okunan
          </span>
          <div className="flex h-9 items-center truncate rounded-control border border-border bg-surface-subtle px-3 text-[13px] text-ink-secondary">
            {formatCorrectionValue(currentValue)}
          </div>
        </div>

        <span className="hidden pb-2.5 text-ink-muted sm:block" aria-hidden>
          →
        </span>

        <div className="min-w-0">
          <label
            htmlFor="correction-new-value"
            className="mb-1.5 block text-[11.5px] font-medium text-ink-secondary"
          >
            Doğru değer
          </label>
          {isMode ? (
            <select
              id="correction-new-value"
              value={newValue}
              onChange={(event) => setNewValue(event.target.value)}
              className="h-9 w-full rounded-control border border-border-strong bg-surface px-3 text-[13px] text-ink"
            >
              <option value="">Seçin…</option>
              <option value="SOLE">Münferit</option>
              <option value="JOINT">Müşterek</option>
            </select>
          ) : (
            <Input
              id="correction-new-value"
              type={isDate ? "date" : "text"}
              value={newValue}
              autoFocus
              placeholder="Belgedeki doğru değeri yazın"
              onChange={(event) => setNewValue(event.target.value)}
            />
          )}
        </div>
      </div>

      <div className="mt-3">
        <Field htmlFor="correction-reason" label="Gerekçe">
          <Input
            id="correction-reason"
            value={reason}
            placeholder="Bu düzeltmenin nedeni"
            onChange={(event) => setReason(event.target.value)}
          />
        </Field>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {QUICK_REASONS.map((quickReason) => (
            <button
              key={quickReason}
              type="button"
              onClick={() => setReason(quickReason)}
              className="rounded-pill border border-border-strong bg-surface px-2.5 py-0.5 text-[11px] text-ink-secondary transition-colors hover:bg-surface-hover hover:text-ink"
            >
              {quickReason}
            </button>
          ))}
        </div>
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

      <div className="mt-3.5 flex flex-wrap items-center gap-2.5">
        <Button type="submit" variant="primary" disabled={!canSubmit}>
          {pending ? "Kaydediliyor…" : "Kaydet ve yeniden analiz et"}
        </Button>
        <span className="text-[11px] text-ink-muted">
          Düzeltme kaydedilir ve dokuz kontrol yeniden çalıştırılır.
        </span>
      </div>
    </form>
  );
}

/* -------------------------------------------------------------------------- */
/* Decision controls                                                          */
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
  const availability = decisionAvailability(
    aggregate.report,
    aggregate.extraction,
    aggregate.corrections.map((correction) => correction.field_path),
  );
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
