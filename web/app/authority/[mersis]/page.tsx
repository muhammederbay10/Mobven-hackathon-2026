"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  getAuditHistory,
  getAuthority,
  getAuthorityHistory,
  getRegistry,
  listTransactions,
} from "@/lib/api";
import { rememberMersis } from "@/lib/clientState";
import {
  AUTHORITY_MODE_LABEL,
  formatAmountMinor,
  formatActor,
  formatAuditAction,
  formatDate,
  formatInstant,
  formatRuleScope,
  TRANSACTION_VERDICT_LABEL,
} from "@/lib/format";
import type {
  AuditItem,
  AuthorityRecordView,
  Registry,
  TransactionDecision,
} from "@/lib/types";

import { Card, Panel, PageHeading, SectionLabel } from "@/components/Layout";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { SimBadge, StatusBadge } from "@/components/Status";

/** Authority record, version history, transactions, and audit activity. */

type Loadable<T> =
  | { kind: "loading" }
  | { kind: "error"; error: unknown }
  | { kind: "ready"; data: T };

const loading = { kind: "loading" } as const;

export default function AuthorityRecordPage({
  params,
}: {
  params: Promise<{ mersis: string }>;
}) {
  const { mersis } = use(params);

  const [authority, setAuthority] = useState<Loadable<AuthorityRecordView>>(loading);
  const [history, setHistory] = useState<Loadable<AuthorityRecordView[]>>(loading);
  const [transactions, setTransactions] = useState<Loadable<TransactionDecision[]>>(loading);
  const [registry, setRegistry] = useState<Loadable<Registry>>(loading);
  const [audit, setAudit] = useState<Loadable<AuditItem[]>>(loading);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const { signal } = controller;

    setAuthority(loading);
    setHistory(loading);
    setTransactions(loading);
    setRegistry(loading);
    setAudit(loading);

    const track = <T,>(
      promise: Promise<T>,
      set: (value: Loadable<T>) => void,
    ) =>
      promise
        .then((data) => set({ kind: "ready", data }))
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") return;
          set({ kind: "error", error });
        });

    const authorityPromise = getAuthority(mersis, signal);
    void track(authorityPromise, setAuthority);
    void track(getAuthorityHistory(mersis, signal).then((r) => r.items), setHistory);
    void track(listTransactions(mersis, signal), setTransactions);
    void track(getRegistry(signal), setRegistry);
    // The audit filter needs the authority ID, so it chains on the first fetch.
    void track(
      authorityPromise.then((record) =>
        getAuditHistory(
          { entity_type: "AUTHORITY_RECORD", entity_id: String(record.id) },
          signal,
        ).then((r) => r.items),
      ),
      setAudit,
    );
  }, [mersis]);

  useEffect(() => {
    load();
    return () => abortRef.current?.abort();
  }, [load]);

  useEffect(() => {
    if (authority.kind === "ready") rememberMersis(mersis);
  }, [authority.kind, mersis]);

  const gated =
    authority.kind === "error" &&
    authority.error instanceof ApiError &&
    (authority.error.code === "AUTHORITY_NOT_FOUND" || authority.error.code === "NOT_FOUND");

  return (
    <>
      <PageHeading
        title="Yetki kaydı — banka tarafı"
        subtitle="Şube onayıyla oluşan yapılandırılmış yetki. Tüm kanallar bu kaydı sorgular."
      />

      {authority.kind === "loading" ? (
        <Panel>
          <LoadingState label="Yetki kaydı yükleniyor…" />
        </Panel>
      ) : gated ? (
        <Panel>
          <EmptyState
            title={`MERSİS ${mersis} için aktif yetki kaydı yok.`}
            hint={
              <>
                Şubede bir başvuru onaylandığında kayıt burada görünür.{" "}
                <Link href="/branch" className="underline">
                  Şube akışına git
                </Link>
              </>
            }
          />
        </Panel>
      ) : authority.kind === "error" ? (
        <Panel>
          <ErrorState error={authority.error} onRetry={load} title="Yetki kaydı yüklenemedi" />
        </Panel>
      ) : (
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,480px)_minmax(0,1fr)]">
          <div className="flex flex-col gap-5">
            <AuthorityRecordPanel record={authority.data} registry={registry} />
            <HistoryPanel history={history} activeId={authority.data.id} />
          </div>
          <div className="flex flex-col gap-5">
            <TransactionsPanel transactions={transactions} />
            <AuditPanel audit={audit} />
          </div>
        </div>
      )}
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Active record                                                              */
/* -------------------------------------------------------------------------- */

function AuthorityRecordPanel({
  record,
  registry,
}: {
  record: AuthorityRecordView;
  registry: Loadable<Registry>;
}) {
  const registryReps =
    registry.kind === "ready"
      ? (registry.data.companies.find((company) => company.mersis === record.mersis)
          ?.representatives ?? [])
      : [];

  return (
    <Panel
      title={
        <span className="flex flex-wrap items-center gap-2">
          Yetki kaydı #{record.id}
          <StatusBadge
            status={record.status === "ACTIVE" ? "green" : "amber"}
            label={record.status === "ACTIVE" ? "Aktif" : "Askıda"}
          />
        </span>
      }
      actions={<span className="text-[12px] text-ink-muted">v{record.version}</span>}
    >
      <div className="p-4">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[12.5px]">
          <MetaRow label="MERSİS" value={record.mersis} mono />
          <MetaRow label="Geçerlilik" value={record.valid_until ? formatDate(record.valid_until) : "Süresiz"} />
          <MetaRow label="Kaynak başvuru" value={`#${record.source_application_id}`} />
          <MetaRow label="Kaynak belge" value={`#${record.source_document_id}`} />
          <MetaRow label="Doğrulayan" value={formatActor(record.verified_by)} />
          <MetaRow label="Doğrulama zamanı" value={formatInstant(record.verified_at)} />
        </dl>

        <div className="mt-4">
          <SectionLabel>Yetkili kişiler</SectionLabel>
          <ul className="flex flex-col gap-2">
            {record.persons.map((person) => {
              const registryStatus = registryReps.find((rep) => rep.id === person.id)?.status;
              return (
                <li key={person.id} className="rounded-card border border-border px-3 py-2 text-[12.5px]">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <b className="font-semibold text-ink">{person.name}</b>
                    <span className="text-ink-secondary">{person.title}</span>
                    {registryStatus ? (
                      <span className="ml-auto flex items-center">
                        <StatusBadge
                          status={registryStatus === "ACTIVE" ? "green" : "red"}
                          label={
                            registryStatus === "ACTIVE" ? "Sicilde yetkili" : "Sicilde düşürüldü"
                          }
                        />
                        <SimBadge label="güncel sicil" />
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-x-4 gap-y-0.5 text-[12px] text-ink-secondary">
                    <span className="font-mono text-[11px]">{person.id}</span>
                    <span>Belge kimliği: {person.source_id}</span>
                    <span>TCKN: {person.tckn_masked}</span>
                    {person.degree ? <span>Derece: {person.degree}</span> : null}
                    <span>
                      {person.valid_from ? formatDate(person.valid_from) : "—"} –{" "}
                      {person.valid_until ? formatDate(person.valid_until) : "süresiz"}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>

        <div className="mt-4">
          <SectionLabel>Yetki kuralları</SectionLabel>
          <ul className="flex flex-col gap-1.5">
            {record.rules.map((rule, index) => (
              <li key={index} className="rounded-card border border-border px-3 py-2 text-[12.5px]">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <b className="font-semibold text-ink">{formatRuleScope(rule.scope)}</b>
                  {rule.blocked ? (
                    <StatusBadge status="red" label="Kapsam dışı" />
                  ) : (
                    <span className="text-ink-secondary">
                      {rule.threshold === null
                        ? "Tutar sınırı yok"
                        : `${formatAmountMinor(rule.threshold)} üzeri ikinci imza`}
                      {" · "}
                      {rule.mode ? AUTHORITY_MODE_LABEL[rule.mode] : "—"}
                    </span>
                  )}
                </div>
                {rule.coSigners.length > 0 ? (
                  <div className="mt-0.5 text-[12px] text-ink-secondary">
                    Birlikte imza: <span className="font-mono text-[11px]">{rule.coSigners.join(", ")}</span>
                  </div>
                ) : null}
                <div className="mt-0.5 text-[11.5px] italic text-ink-muted">
                  “{rule.evidence.quote}” (sayfa {rule.evidence.page})
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Panel>
  );
}

function MetaRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] text-ink-muted">{label}</dt>
      <dd className={`truncate text-ink ${mono ? "font-mono text-[12px]" : ""}`} title={value}>
        {value}
      </dd>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Version history                                                            */
/* -------------------------------------------------------------------------- */

function HistoryPanel({
  history,
  activeId,
}: {
  history: Loadable<AuthorityRecordView[]>;
  activeId: number;
}) {
  return (
    <Panel title="Sürüm geçmişi">
      {history.kind === "loading" ? (
        <LoadingState label="Geçmiş yükleniyor…" />
      ) : history.kind === "error" ? (
        <ErrorState error={history.error} title="Geçmiş yüklenemedi" />
      ) : history.data.length === 0 ? (
        <EmptyState title="Sürüm geçmişi yok." />
      ) : (
        <ul className="p-3">
          {history.data.map((item) => (
            <li
              key={item.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border/60 px-1 py-2 text-[12.5px] last:border-b-0"
            >
              <b className="font-semibold text-ink">v{item.version}</b>
              <StatusBadge
                status={item.status === "ACTIVE" ? "green" : "amber"}
                label={item.status === "ACTIVE" ? "Aktif" : "Askıda"}
              />
              <span className="text-ink-secondary">{formatInstant(item.verified_at)}</span>
              <span className="text-ink-muted">başvuru #{item.source_application_id}</span>
              {item.id === activeId ? (
                <span className="text-[11px] font-semibold text-info">görüntülenen</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
/* Transactions and audit                                                     */
/* -------------------------------------------------------------------------- */

function TransactionsPanel({
  transactions,
}: {
  transactions: Loadable<TransactionDecision[]>;
}) {
  return (
    <Panel title="İşlem geçmişi">
      {transactions.kind === "loading" ? (
        <LoadingState label="İşlemler yükleniyor…" />
      ) : transactions.kind === "error" ? (
        <ErrorState error={transactions.error} title="İşlemler yüklenemedi" />
      ) : transactions.data.length === 0 ? (
        <EmptyState title="Henüz mobil işlem yapılmadı." />
      ) : (
        <ul className="p-3">
          {transactions.data.map((decision) => (
            <li
              key={decision.transaction_id}
              className="border-b border-border/60 px-1 py-2 text-[12.5px] last:border-b-0"
            >
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-mono text-[11px] text-ink-muted">
                  #{decision.transaction_id}
                </span>
                <StatusBadge
                  status={
                    decision.verdict === "ALLOWED"
                      ? "green"
                      : decision.verdict === "PENDING_COSIGN"
                        ? "amber"
                        : "red"
                  }
                  label={TRANSACTION_VERDICT_LABEL[decision.verdict]}
                />
                {decision.authorization_code ? (
                  <span className="font-mono text-[11.5px] text-ink">
                    {decision.authorization_code}
                  </span>
                ) : null}
              </div>
              <Card className="mt-1.5 !p-2.5">
                <ul className="flex flex-col gap-0.5">
                  {decision.checks.map((check, index) => (
                    <li key={index} className="flex items-baseline gap-1.5 text-[12px]">
                      <StatusBadge status={check.status} label={check.title} />
                      <span className="text-ink-secondary">{check.reason}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function AuditPanel({ audit }: { audit: Loadable<AuditItem[]> }) {
  return (
    <Panel title="Denetim izi (yetki kaydı)">
      {audit.kind === "loading" ? (
        <LoadingState label="Denetim izi yükleniyor…" />
      ) : audit.kind === "error" ? (
        <ErrorState error={audit.error} title="Denetim izi yüklenemedi" />
      ) : audit.data.length === 0 ? (
        <EmptyState title="Denetim kaydı yok." />
      ) : (
        <ul className="p-3">
          {audit.data.map((item) => (
            <li
              key={item.id}
              className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 border-b border-border/60 px-1 py-2 text-[12.5px] last:border-b-0"
            >
              <span className="font-medium text-ink">{formatAuditAction(item.action)}</span>
              <span className="text-ink-secondary">{formatActor(item.actor)}</span>
              <span className="ml-auto text-[11.5px] text-ink-muted">
                {formatInstant(item.created_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
