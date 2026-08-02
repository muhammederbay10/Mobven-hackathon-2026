"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  authorizeTransaction,
  cosignTransaction,
  getAuthority,
  getRegistry,
  listTransactions,
} from "@/lib/api";
import { lastMersis, rememberMersis } from "@/lib/clientState";
import {
  formatAmountMinor,
  formatInstant,
  parseAmountToMinor,
  TRANSACTION_SUBJECT_LABEL,
  TRANSACTION_VERDICT_LABEL,
} from "@/lib/format";
import type {
  AuthorityRecordView,
  Registry,
  TransactionDecision,
  TransactionSubject,
} from "@/lib/types";

import { PageHeading, Panel, PhoneFrame, SectionLabel } from "@/components/Layout";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { SimBadge, StatusBadge, StatusIcon } from "@/components/Status";
import { Button, Field, Input } from "@/components/UI";

/** Authority-controlled mobile transactions and co-signing. */

type Loadable<T> =
  | { kind: "loading" }
  | { kind: "error"; error: unknown }
  | { kind: "ready"; data: T };

const loading = { kind: "loading" } as const;

type RequestContext = {
  subject: TransactionSubject;
  amountMinor: number;
  initiator: string;
};

const PRESETS: Array<{ label: string; subject: TransactionSubject; amountMinor: number }> = [
  { label: "250.000 ₺ genel işlem", subject: "GENERAL", amountMinor: 25_000_000 },
  { label: "1.200.000 ₺ genel işlem", subject: "GENERAL", amountMinor: 120_000_000 },
  { label: "750.000 ₺ kredi", subject: "CREDIT", amountMinor: 75_000_000 },
  { label: "Gayrimenkul işlemi", subject: "REAL_ESTATE", amountMinor: 0 },
];

export function MobileClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const mersis = searchParams.get("mersis");

  const [authority, setAuthority] = useState<Loadable<AuthorityRecordView>>(loading);
  const [history, setHistory] = useState<Loadable<TransactionDecision[]>>(loading);
  const [registry, setRegistry] = useState<Loadable<Registry>>(loading);
  const [selectedPersonId, setSelectedPersonId] = useState<string | null>(null);
  const [decision, setDecision] = useState<TransactionDecision | null>(null);
  const [requestContext, setRequestContext] = useState<RequestContext | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Bare `/mobile` navigation: fall back to the last MERSİS this session saw.
  useEffect(() => {
    if (mersis === null) {
      const known = lastMersis();
      if (known) router.replace(`/mobile?mersis=${known}`);
    }
  }, [mersis, router]);

  const load = useCallback(async () => {
    if (mersis === null) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const { signal } = controller;

    setAuthority(loading);
    setHistory(loading);
    setRegistry(loading);

    const track = <T,>(promise: Promise<T>, set: (value: Loadable<T>) => void) =>
      promise
        .then((data) => set({ kind: "ready", data }))
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") return;
          set({ kind: "error", error });
        });

    void track(getAuthority(mersis, signal), setAuthority);
    void track(listTransactions(mersis, signal), setHistory);
    void track(getRegistry(signal), setRegistry);
  }, [mersis]);

  useEffect(() => {
    load();
    return () => abortRef.current?.abort();
  }, [load]);

  useEffect(() => {
    if (mersis !== null && authority.kind === "ready") rememberMersis(mersis);
  }, [mersis, authority.kind]);

  // Default the switcher to the first authority person once known.
  useEffect(() => {
    if (authority.kind === "ready" && selectedPersonId === null) {
      setSelectedPersonId(authority.data.persons[0]?.id ?? null);
    }
  }, [authority, selectedPersonId]);

  const refreshHistory = useCallback(async () => {
    if (mersis === null) return;
    try {
      setHistory({ kind: "ready", data: await listTransactions(mersis) });
      setRegistry({ kind: "ready", data: await getRegistry() });
    } catch {
      /* Keep the completed decision visible if history refresh fails. */
    }
  }, [mersis]);

  if (mersis === null) {
    return (
      <MobileShell mersis={null}>
        <Panel>
          <EmptyState
            title="MERSİS numarası olmadan mobil şube açılamaz."
            hint={
              <>
                İşlem yapmak istediğiniz şirketin yetki kaydını seçin.{" "}
                <Link href="/" className="underline">
                  Kontrol paneline dön
                </Link>
              </>
            }
          />
        </Panel>
      </MobileShell>
    );
  }

  const gated =
    authority.kind === "error" &&
    authority.error instanceof ApiError &&
    (authority.error.code === "AUTHORITY_NOT_FOUND" || authority.error.code === "NOT_FOUND");

  const companyName =
    registry.kind === "ready"
      ? (registry.data.companies.find((company) => company.mersis === mersis)?.legal_name ??
        `MERSİS ${mersis}`)
      : `MERSİS ${mersis}`;

  const pendingDecision =
    decision?.verdict === "PENDING_COSIGN"
      ? decision
      : (decision ?? null) === null && history.kind === "ready"
        ? (history.data.find((item) => item.verdict === "PENDING_COSIGN") ?? null)
        : null;

  return (
    <MobileShell mersis={mersis}>
      {authority.kind === "loading" ? (
        <Panel>
          <LoadingState label="Yetki kaydı sorgulanıyor…" />
        </Panel>
      ) : gated ? (
        <Panel>
          <EmptyState
            title={`MERSİS ${mersis} için yetki kaydı yok.`}
            hint={
              <>
                Mobil işlemler ancak şubede bir başvuru onaylandıktan sonra açılır.{" "}
                <Link href="/branch" className="underline">
                  Şube akışına git
                </Link>
              </>
            }
          />
        </Panel>
      ) : authority.kind === "error" ? (
        <Panel>
          <ErrorState error={authority.error} onRetry={load} title="Yetki kaydı sorgulanamadı" />
        </Panel>
      ) : (
        <div className="flex flex-wrap items-start gap-8">
          <PhoneFrame company={companyName} title="Mobil şube">
            <PhoneScreen
              authority={authority.data}
              registry={registry}
              mersis={mersis}
              selectedPersonId={selectedPersonId}
              onSelectPerson={setSelectedPersonId}
              decision={decision}
              requestContext={requestContext}
              pendingDecision={pendingDecision}
              onDecision={(next, context) => {
                setDecision(next);
                if (context !== undefined) setRequestContext(context);
                void refreshHistory();
              }}
            />
          </PhoneFrame>

          <div className="min-w-[320px] max-w-[460px] flex-1">
            <HistoryPanel history={history} authority={authority.data} />
          </div>
        </div>
      )}
    </MobileShell>
  );
}

function MobileShell({ mersis, children }: { mersis: string | null; children: React.ReactNode }) {
  return (
    <>
      <PageHeading
        title={
          <>
            Mobil şube — sonraki işlemler
            <SimBadge label="test ortamı" />
          </>
        }
        subtitle={
          mersis
            ? `Belge bir daha istenmez. Her işlemde MERSİS ${mersis} için güncel yetki ve sicil kayıtları doğrulanır.`
            : "Belge bir daha istenmez. Her işlemde kayıtlı yetki sorgulanır: kişi, limit, konu, süre ve sicil durumu."
        }
      />
      {children}
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Phone screen: person switcher + request + decision + co-sign               */
/* -------------------------------------------------------------------------- */

function PhoneScreen({
  authority,
  registry,
  mersis,
  selectedPersonId,
  onSelectPerson,
  decision,
  requestContext,
  pendingDecision,
  onDecision,
}: {
  authority: AuthorityRecordView;
  registry: Loadable<Registry>;
  mersis: string;
  selectedPersonId: string | null;
  onSelectPerson: (id: string) => void;
  decision: TransactionDecision | null;
  requestContext: RequestContext | null;
  pendingDecision: TransactionDecision | null;
  onDecision: (decision: TransactionDecision, context?: RequestContext | null) => void;
}) {
  const persons = authority.persons;
  const selected = persons.find((person) => person.id === selectedPersonId) ?? persons[0] ?? null;

  const registryReps =
    registry.kind === "ready"
      ? (registry.data.companies.find((company) => company.mersis === mersis)?.representatives ??
        [])
      : [];

  return (
    <div className="flex flex-1 flex-col gap-3.5">
      <div>
        <SectionLabel>Kimin telefonu?</SectionLabel>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Yetkili kişi seçimi">
          {persons.map((person) => {
            const isSelected = person.id === selected?.id;
            const needsSignature = pendingDecision?.required_cosigner === person.id;
            const registryStatus = registryReps.find((rep) => rep.id === person.id)?.status;
            return (
              <button
                key={person.id}
                type="button"
                aria-pressed={isSelected}
                onClick={() => onSelectPerson(person.id)}
                className={`relative rounded-pill border px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
                  isSelected
                    ? "border-ink bg-ink text-white"
                    : "border-border-strong bg-surface text-ink hover:bg-surface-hover"
                }`}
              >
                {person.name}
                {needsSignature ? (
                  <span
                    className="absolute -right-1 -top-1 grid size-4 place-items-center rounded-full bg-danger text-[9px] font-bold text-white"
                    title="İmza bekleyen işlem var"
                  >
                    1
                  </span>
                ) : null}
                {registryStatus === "REMOVED" ? (
                  <span className="ml-1.5 text-[10px] font-normal opacity-80">(sicilde düşürüldü)</span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>

      {selected === null ? (
        <EmptyState title="Yetki kaydında kişi yok." />
      ) : pendingDecision !== null && pendingDecision.required_cosigner === selected.id ? (
        <CosignCard
          pending={pendingDecision}
          cosignerId={selected.id}
          onDecision={onDecision}
        />
      ) : (
        <>
          <TransactionForm
            initiator={selected.id}
            mersis={mersis}
            onDecision={onDecision}
          />
          {decision !== null ? (
            <DecisionCard
              decision={decision}
              persons={persons}
              requestContext={requestContext}
            />
          ) : pendingDecision !== null ? (
            <div className="rounded-card border border-warning/25 bg-warning-soft px-3 py-2.5 text-[12px] text-ink-secondary">
              <b className="font-semibold text-warning">
                <span aria-hidden>! </span>İkinci imza bekleyen işlem var.
              </b>{" "}
              {personName(persons, pendingDecision.required_cosigner)} telefonuna geçin ve imzayı
              tamamlayın.
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function personName(
  persons: AuthorityRecordView["persons"],
  personId: string | null,
): string {
  if (personId === null) return "—";
  return persons.find((person) => person.id === personId)?.name ?? personId;
}

/* -------------------------------------------------------------------------- */
/* Transaction request                                                        */
/* -------------------------------------------------------------------------- */

function TransactionForm({
  initiator,
  mersis,
  onDecision,
}: {
  initiator: string;
  mersis: string;
  onDecision: (decision: TransactionDecision, context: RequestContext) => void;
}) {
  const [subject, setSubject] = useState<TransactionSubject>("GENERAL");
  const [amountText, setAmountText] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const parsedAmount = parseAmountToMinor(amountText);
  const amountInvalid = amountText.trim() !== "" && parsedAmount === null;

  const submit = useCallback(
    async (request: { subject: TransactionSubject; amountMinor: number }) => {
      if (pending) return;
      setPending(true);
      setError(null);
      try {
        const decision = await authorizeTransaction({
          mersis,
          subject: request.subject,
          currency: "TRY",
          amount_minor: request.amountMinor,
          initiator,
        });
        onDecision(decision, { ...request, initiator });
      } catch (cause) {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setError(cause);
      } finally {
        setPending(false);
      }
    },
    [pending, mersis, initiator, onDecision],
  );

  return (
    <div>
      <SectionLabel>Yeni işlem</SectionLabel>

      <div className="mb-2.5 grid grid-cols-2 gap-1.5">
        {PRESETS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            disabled={pending}
            onClick={() => {
              setSubject(preset.subject);
              setAmountText(
                (preset.amountMinor / 100).toLocaleString("tr-TR", {
                  minimumFractionDigits: 0,
                  maximumFractionDigits: 2,
                }),
              );
              void submit({ subject: preset.subject, amountMinor: preset.amountMinor });
            }}
            className="rounded-card border border-border px-2.5 py-2 text-left text-[12px] font-medium text-ink transition-colors hover:border-border-strong hover:bg-surface-hover disabled:opacity-50"
          >
            {preset.label}
            <span className="block text-[10.5px] font-normal text-ink-muted">
              {TRANSACTION_SUBJECT_LABEL[preset.subject]}
            </span>
          </button>
        ))}
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (parsedAmount === null) return;
          void submit({ subject, amountMinor: parsedAmount });
        }}
        className="flex flex-col gap-2.5"
        noValidate
      >
        <Field htmlFor="tx-subject" label="İşlem konusu">
          <select
            id="tx-subject"
            value={subject}
            onChange={(event) => setSubject(event.target.value as TransactionSubject)}
            className="h-9 w-full rounded-control border border-border-strong bg-surface px-3 text-[13px] text-ink"
          >
            {(Object.keys(TRANSACTION_SUBJECT_LABEL) as TransactionSubject[]).map((key) => (
              <option key={key} value={key}>
                {TRANSACTION_SUBJECT_LABEL[key]}
              </option>
            ))}
          </select>
        </Field>

        <Field
          htmlFor="tx-amount"
          label="Tutar (₺)"
          error={amountInvalid ? "Tutar okunamadı. Örn. 250.000 veya 250000,50" : undefined}
        >
          <Input
            id="tx-amount"
            inputMode="decimal"
            placeholder="250.000"
            value={amountText}
            onChange={(event) => setAmountText(event.target.value)}
          />
        </Field>

        {error instanceof ApiError ? (
          <div
            className="rounded-card border border-danger/30 bg-danger-soft px-3 py-2 text-[12px] text-danger"
            role="alert"
          >
            {error.message}
            {error.correlationId ? (
              <span className="mt-0.5 block font-mono text-[10.5px] text-ink-muted">
                İşlem no: {error.correlationId}
              </span>
            ) : null}
          </div>
        ) : null}

        <Button type="submit" variant="primary" disabled={pending || parsedAmount === null}>
          {pending ? "Yetki sorgulanıyor…" : "İşlemi gönder"}
        </Button>
      </form>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Decision and co-sign cards                                                 */
/* -------------------------------------------------------------------------- */

function DecisionCard({
  decision,
  persons,
  requestContext,
}: {
  decision: TransactionDecision;
  persons: AuthorityRecordView["persons"];
  requestContext: RequestContext | null;
}) {
  const tone =
    decision.verdict === "ALLOWED" ? "green" : decision.verdict === "PENDING_COSIGN" ? "amber" : "red";

  return (
    <div
      className={`rounded-card border px-3 py-2.5 ${
        tone === "green"
          ? "border-success/25 bg-success-soft"
          : tone === "amber"
            ? "border-warning/25 bg-warning-soft"
            : "border-danger/25 bg-danger-soft"
      }`}
    >
      <div className="mb-1 flex items-center gap-2">
        <StatusBadge status={tone} label={TRANSACTION_VERDICT_LABEL[decision.verdict]} />
        <span className="text-[11px] text-ink-muted">#{decision.transaction_id}</span>
      </div>

      {requestContext ? (
        <p className="mb-1.5 text-[12px] text-ink-secondary">
          {TRANSACTION_SUBJECT_LABEL[requestContext.subject]} ·{" "}
          {formatAmountMinor(requestContext.amountMinor)} ·{" "}
          {personName(persons, requestContext.initiator)}
        </p>
      ) : null}

      <ul className="flex flex-col gap-1">
        {decision.checks.map((check, index) => (
          <li key={index} className="flex items-start gap-1.5 text-[12px]">
            <StatusIcon status={check.status} />
            <span>
              <b className="font-medium text-ink">{check.title}.</b>{" "}
              <span className="text-ink-secondary">{check.reason}</span>
            </span>
          </li>
        ))}
      </ul>

      {decision.verdict === "ALLOWED" && decision.authorization_code ? (
        <div className="mt-2 rounded-card border border-border bg-surface px-3 py-2">
          <div className="text-[10.5px] uppercase tracking-[0.06em] text-ink-muted">
            Onay kodu
          </div>
          <div className="font-mono text-[15px] font-semibold text-ink">
            {decision.authorization_code}
          </div>
          <div className="mt-0.5 text-[10.5px] text-ink-muted">
            Şubede doğrulanan belge esas alındı · {formatInstant(decision.source.verified_at)}
          </div>
        </div>
      ) : null}

      {decision.verdict === "PENDING_COSIGN" ? (
        <p className="mt-2 text-[12px] text-ink-secondary">
          <span aria-hidden>🔔 </span>
          Bildirim <b className="font-semibold text-ink">{personName(persons, decision.required_cosigner)}</b>{" "}
          telefonuna gönderildi. İmza için yukarıdan o kişinin telefonuna geçin.
        </p>
      ) : null}

      {decision.verdict === "DENIED" ? (
        <p className="mt-2 text-[12px] text-ink-secondary">
          Sonraki adım: işlem kayıtlı yetkiyle yapılamıyor. Yetki değiştiyse şubeye yeni imza
          sirküleriyle başvurun.
        </p>
      ) : null}
    </div>
  );
}

function CosignCard({
  pending: pendingDecision,
  cosignerId,
  onDecision,
}: {
  pending: TransactionDecision;
  cosignerId: string;
  onDecision: (decision: TransactionDecision, context?: RequestContext | null) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function handleCosign() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const decision = await cosignTransaction(pendingDecision.transaction_id, {
        cosigner: cosignerId,
      });
      onDecision(decision, null);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(cause);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-card border border-warning/25 bg-warning-soft px-3 py-2.5">
      <div className="mb-1 flex items-center gap-2">
        <StatusBadge status="amber" label="İmza bekleyen işlem" />
        <span className="text-[11px] text-ink-muted">#{pendingDecision.transaction_id}</span>
      </div>

      <ul className="mb-2 flex flex-col gap-1">
        {pendingDecision.checks.map((check, index) => (
          <li key={index} className="flex items-start gap-1.5 text-[12px]">
            <StatusIcon status={check.status} />
            <span>
              <b className="font-medium text-ink">{check.title}.</b>{" "}
              <span className="text-ink-secondary">{check.reason}</span>
            </span>
          </li>
        ))}
      </ul>

      {error instanceof ApiError ? (
        <div
          className="mb-2 rounded-card border border-danger/30 bg-danger-soft px-3 py-2 text-[12px] text-danger"
          role="alert"
        >
          {error.message}
          {error.correlationId ? (
            <span className="mt-0.5 block font-mono text-[10.5px] text-ink-muted">
              İşlem no: {error.correlationId}
            </span>
          ) : null}
        </div>
      ) : null}

      <Button type="button" variant="primary" disabled={busy} onClick={handleCosign}>
        {busy ? "İmzalanıyor…" : "İkinci imzayı ver"}
      </Button>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Transaction history                                                        */
/* -------------------------------------------------------------------------- */

function HistoryPanel({
  history,
  authority,
}: {
  history: Loadable<TransactionDecision[]>;
  authority: AuthorityRecordView;
}) {
  return (
    <Panel title="İşlem geçmişi">
      {history.kind === "loading" ? (
        <LoadingState label="İşlemler yükleniyor…" />
      ) : history.kind === "error" ? (
        <ErrorState error={history.error} title="İşlem geçmişi yüklenemedi" />
      ) : history.data.length === 0 ? (
        <EmptyState title="Henüz işlem yapılmadı." />
      ) : (
        <ul className="p-3">
          {history.data.map((item) => (
            <li
              key={item.transaction_id}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border/60 px-1 py-2 text-[12.5px] last:border-b-0"
            >
              <span className="font-mono text-[11px] text-ink-muted">#{item.transaction_id}</span>
              <StatusBadge
                status={
                  item.verdict === "ALLOWED"
                    ? "green"
                    : item.verdict === "PENDING_COSIGN"
                      ? "amber"
                      : "red"
                }
                label={TRANSACTION_VERDICT_LABEL[item.verdict]}
              />
              {item.authorization_code ? (
                <span className="font-mono text-[11.5px] text-ink">{item.authorization_code}</span>
              ) : null}
              {item.verdict === "PENDING_COSIGN" ? (
                <span className="text-[11.5px] text-ink-secondary">
                  bekleyen imza: {personName(authority.persons, item.required_cosigner)}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
