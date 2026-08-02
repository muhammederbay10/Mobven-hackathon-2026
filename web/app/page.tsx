"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  getApplication,
  getAuditHistory,
  getAuthority,
  getRegistry,
  listDemoCases,
  loadDemoCase,
  resetDemo,
  type DemoCaseCard,
} from "@/lib/api";
import { isTerminalStatus } from "@/lib/branch";
import { clearNavigationState } from "@/lib/clientState";
import {
  APPLICATION_STATUS_LABEL,
  formatInstant,
  ONBOARDING_VERDICT_LABEL,
  ONBOARDING_VERDICT_STATUS,
} from "@/lib/format";
import type {
  ApplicationAggregate,
  ApplicationStatus,
  AuditItem,
  CheckStatus,
} from "@/lib/types";

import {
  LandmarkIcon,
  ShieldCheckIcon,
  SmartphoneIcon,
} from "@/components/Icon";
import { Card, Panel, SectionLabel } from "@/components/Layout";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { StatusBadge, StatusIcon } from "@/components/Status";
import { Button } from "@/components/UI";

/**
 * `/` — the starq.dev banking operations dashboard.
 *
 * Everything numeric on this page is read from the bank API — the audit trail,
 * per-application aggregates, the registry and per-company authority records.
 * There is no list-applications endpoint, so the working set is derived from
 * recent APPLICATION audit entries and each aggregate is fetched individually;
 * when nothing exists yet the cards honestly show zero. Nothing here computes
 * a verdict or invents production data.
 *
 * The demo scenario loader is intentionally demoted to a collapsed utility
 * section at the bottom — its backend functionality is unchanged.
 */

/* How many recent applications to hydrate for the table and counters. */
const MAX_APPLICATIONS = 8;
const MAX_ACTIVITY = 8;

/** Display tone per backend status — presentation only, never a decision. */
const STATUS_TONE: Record<ApplicationStatus, CheckStatus> = {
  DRAFT: "amber",
  IDENTITY_VERIFIED: "amber",
  DOCUMENT_SCANNED: "amber",
  ANALYZING: "amber",
  ANALYZED: "amber",
  ANALYSIS_FAILED: "red",
  APPROVED: "green",
  DOC_REQUESTED: "red",
  ESCALATED: "red",
};

/** Audit actions surfaced in "Son işlemler", with Turkish labels and tones. */
const ACTIVITY_PRESENTATION: Record<
  string,
  { label: string; tone: CheckStatus }
> = {
  APPLICATION_CREATED: { label: "Yeni başvuru", tone: "amber" },
  APPLICATION_DECIDED: { label: "İnceleme tamamlandı", tone: "green" },
  APPROVAL_OVERRIDE: { label: "İstisnai onay", tone: "amber" },
  AUTHORITY_CREATED: { label: "Yetki kaydı oluşturuldu", tone: "green" },
  AUTHORITY_SUSPENDED: { label: "Yetki kaydı askıya alındı", tone: "red" },
  REGISTRY_REPRESENTATIVE_UPDATED: { label: "Sicil değişikliği", tone: "red" },
};

type DashboardData = {
  pendingApplications: ApplicationAggregate[];
  openCount: number;
  reviewCount: number;
  activeAuthorityCount: number;
  registryAlertCount: number;
  activity: AuditItem[];
};

type DashboardState =
  | { kind: "loading" }
  | { kind: "error"; error: unknown }
  | { kind: "ready"; data: DashboardData };

export default function DashboardPage() {
  const [state, setState] = useState<DashboardState>({ kind: "loading" });
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const { signal } = controller;
    setState({ kind: "loading" });

    try {
      const [audit, registry] = await Promise.all([
        getAuditHistory(undefined, signal),
        getRegistry(signal),
      ]);

      // Newest-first unique application IDs out of the audit trail.
      const applicationIds: number[] = [];
      for (const item of audit.items) {
        if (item.entity_type !== "APPLICATION" || item.entity_id === null)
          continue;
        const id = Number(item.entity_id);
        if (!Number.isInteger(id) || applicationIds.includes(id)) continue;
        applicationIds.push(id);
        if (applicationIds.length >= MAX_APPLICATIONS) break;
      }

      // A stale audit row (e.g. right after a reset) may point at a deleted
      // application; those fetches fail individually and are skipped.
      const aggregates = (
        await Promise.all(
          applicationIds.map((id) =>
            getApplication(id, signal).catch(() => null),
          ),
        )
      ).filter(
        (aggregate): aggregate is ApplicationAggregate => aggregate !== null,
      );

      const authorities = (
        await Promise.all(
          registry.companies.map((company) =>
            getAuthority(company.mersis, signal).catch(() => null),
          ),
        )
      ).filter(
        (record): record is NonNullable<typeof record> => record !== null,
      );

      const open = aggregates.filter(
        (aggregate) => !isTerminalStatus(aggregate.application.status),
      );
      const pendingApplications = [...open].sort((a, b) =>
        b.application.updated_at.localeCompare(a.application.updated_at),
      );

      const registryAlertCount =
        registry.companies.filter((company) => company.status !== "ACTIVE")
          .length +
        registry.companies
          .flatMap((company) => company.representatives)
          .filter((rep) => rep.status === "REMOVED").length;

      const activity = audit.items
        .filter((item) => ACTIVITY_PRESENTATION[item.action] !== undefined)
        .slice(0, MAX_ACTIVITY);

      setState({
        kind: "ready",
        data: {
          pendingApplications,
          openCount: open.length,
          reviewCount: open.filter((a) => a.application.status === "ANALYZED")
            .length,
          activeAuthorityCount: authorities.filter((a) => a.status === "ACTIVE")
            .length,
          registryAlertCount,
          activity,
        },
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setState({ kind: "error", error });
    }
  }, []);

  useEffect(() => {
    load();
    return () => abortRef.current?.abort();
  }, [load]);

  return (
    <>
      {state.kind === "loading" ? (
        <Panel>
          <LoadingState label="Operasyon verileri yükleniyor…" />
        </Panel>
      ) : state.kind === "error" ? (
        <Panel>
          <ErrorState
            error={state.error}
            onRetry={load}
            title="Panel verileri yüklenemedi"
          />
        </Panel>
      ) : (
        <>
          <StatRow data={state.data} />
          <div className="mt-4 grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,380px)]">
            <PendingApplicationsPanel
              applications={state.data.pendingApplications}
            />
            <div className="flex flex-col gap-4">
              <ActivityPanel activity={state.data.activity} />
              <QuickActionsCard />
            </div>
          </div>
        </>
      )}

      <DemoToolsSection onMutated={load} />
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Operational summary                                                        */
/* -------------------------------------------------------------------------- */

function StatRow({ data }: { data: DashboardData }) {
  const stats: Array<{ label: string; value: number; hint: string }> = [
    {
      label: "Açık başvurular",
      value: data.openCount,
      hint: "Henüz sonuçlanmamış başvurular",
    },
    {
      label: "İnceleme bekleyenler",
      value: data.reviewCount,
      hint: "Analizi tamamlanıp karar bekleyenler",
    },
    {
      label: "Aktif yetki kayıtları",
      value: data.activeAuthorityCount,
      hint: "Mobil işlemlere açık şirketler",
    },
    {
      label: "Sicil uyarıları",
      value: data.registryAlertCount,
      hint: "Sicilde düşürülmüş yetki veya pasif şirket",
    },
  ];

  return (
    // The soft accent wash from the reference design, carried over from the
    // previous card strip. Decorative only — outcomes still use StatusBadge.
    <div
      className="rounded-panel p-3.5"
      style={{ background: "var(--yc-gradient-wash)" }}
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((stat) => (
          <Card key={stat.label} className="shadow-panel">
            <div className="text-[12px] font-medium text-ink-secondary">
              {stat.label}
            </div>
            <div className="mt-1 text-[26px] font-semibold leading-8 tracking-[-0.01em] text-ink">
              {stat.value}
            </div>
            <div className="mt-0.5 text-[11.5px] leading-4 text-ink-muted">
              {stat.hint}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 3. İşlem bekleyen başvurular                                               */
/* -------------------------------------------------------------------------- */

function PendingApplicationsPanel({
  applications,
}: {
  applications: ApplicationAggregate[];
}) {
  return (
    <Panel title="İşlem bekleyen başvurular">
      {applications.length === 0 ? (
        <EmptyState
          title="Bekleyen başvuru yok."
          hint="Yeni bir başvuru açıldığında bu listede görünür."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-140 text-left text-[13px]">
            <thead>
              <tr className="border-b border-border text-[11px] uppercase tracking-[0.06em] text-ink-muted">
                <th className="px-4 py-2.5 font-semibold">Şirket</th>
                <th className="px-4 py-2.5 font-semibold">Başvuru</th>
                <th className="px-4 py-2.5 font-semibold">Durum</th>
                <th className="px-4 py-2.5 font-semibold">Son güncelleme</th>
                <th className="px-4 py-2.5 font-semibold">
                  <span className="sr-only">İşlem</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {applications.map(({ application }) => (
                <tr
                  key={application.id}
                  className="border-b border-border/60 last:border-b-0"
                >
                  <td className="px-4 py-2.5">
                    <div className="font-medium text-ink">
                      {application.company_name}
                    </div>
                    <div className="font-mono text-[11px] text-ink-muted">
                      MERSİS {application.mersis}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[12px] text-ink-secondary">
                    #{application.id}
                  </td>
                  <td className="px-4 py-2.5">
                    <StatusBadge
                      status={STATUS_TONE[application.status]}
                      label={APPLICATION_STATUS_LABEL[application.status]}
                    />
                  </td>
                  <td className="px-4 py-2.5 text-ink-secondary">
                    {formatInstant(application.updated_at)}
                  </td>
                  <td className="px-4 py-2.5">
                    <Link
                      href={`/branch?application=${application.id}`}
                      className="inline-flex h-7 items-center rounded-control border border-border-strong bg-surface px-2.5 text-[12px] font-medium text-ink hover:bg-surface-hover"
                    >
                      Devam et
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
/* 4. Son işlemler                                                            */
/* -------------------------------------------------------------------------- */

function ActivityPanel({ activity }: { activity: AuditItem[] }) {
  return (
    <Panel title="Son işlemler">
      {activity.length === 0 ? (
        <EmptyState title="Henüz işlem kaydı yok." />
      ) : (
        <ul className="p-2.5">
          {activity.map((item) => {
            const presentation = ACTIVITY_PRESENTATION[item.action];
            if (!presentation) return null;
            return (
              <li
                key={item.id}
                className="flex items-center gap-2.5 border-b border-border/60 px-1.5 py-2 last:border-b-0"
              >
                <StatusIcon status={presentation.tone} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12.5px] font-medium text-ink">
                    {presentation.label}
                    {item.entity_id ? (
                      <span className="ml-1.5 font-mono text-[11px] font-normal text-ink-muted">
                        #{item.entity_id}
                      </span>
                    ) : null}
                  </div>
                  <div className="text-[11px] text-ink-muted">{item.actor}</div>
                </div>
                <span className="flex-none text-[11px] text-ink-muted">
                  {formatInstant(item.created_at)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
/* 5. Quick actions                                                           */
/* -------------------------------------------------------------------------- */

function QuickActionsCard() {
  const actions = [
    {
      href: "/authority",
      label: "Yetki kaydı sorgula",
      description: "Aktif yetkiler, sürümler ve denetim izi",
      icon: ShieldCheckIcon,
    },
    {
      href: "/registry",
      label: "Ticaret sicili kontrolü",
      description: "Simüle sicilde temsilci durumları",
      icon: LandmarkIcon,
    },
    {
      href: "/mobile",
      label: "Mobil işlem simülasyonu",
      description: "Kayıtlı yetkiyle işlem ve ikinci imza",
      icon: SmartphoneIcon,
    },
  ];

  return (
    <Card className="shadow-panel">
      <SectionLabel>Hızlı işlemler</SectionLabel>
      <ul className="flex flex-col gap-1">
        {actions.map((action) => {
          const Icon = action.icon;
          return (
            <li key={action.href}>
              <Link
                href={action.href}
                className="flex items-center gap-2.5 rounded-card border border-transparent px-2 py-2 transition-colors hover:border-border hover:bg-surface-hover"
              >
                <span className="grid size-8 flex-none place-items-center rounded-control border border-border bg-surface-subtle text-ink-secondary">
                  <Icon />
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-medium text-ink">
                    {action.label}
                  </span>
                  <span className="block truncate text-[11.5px] text-ink-muted">
                    {action.description}
                  </span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Demo tools — demoted from the primary view, functionality unchanged        */
/* -------------------------------------------------------------------------- */

type DemoLoadState =
  | { kind: "idle" }
  | { kind: "pending"; case: number }
  | { kind: "error"; case: number; error: unknown };

function DemoToolsSection({ onMutated }: { onMutated: () => void }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [cases, setCases] = useState<DemoCaseCard[] | null>(null);
  const [listError, setListError] = useState<unknown>(null);
  const [loadState, setLoadState] = useState<DemoLoadState>({ kind: "idle" });
  const [resetState, setResetState] = useState<
    "idle" | "pending" | "done" | "error"
  >("idle");
  const loadAbortRef = useRef<AbortController | null>(null);

  const fetchCases = useCallback(async () => {
    setListError(null);
    setCases(null);
    try {
      const response = await listDemoCases();
      setCases(response.cases);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setListError(error);
    }
  }, []);

  // The case list loads lazily, on first expand.
  useEffect(() => {
    if (open && cases === null && listError === null) fetchCases();
  }, [open, cases, listError, fetchCases]);

  const handleLoadCase = useCallback(
    async (caseNumber: number) => {
      loadAbortRef.current?.abort();
      const controller = new AbortController();
      loadAbortRef.current = controller;
      setLoadState({ kind: "pending", case: caseNumber });
      try {
        const { application_id } = await loadDemoCase(
          caseNumber,
          controller.signal,
        );
        router.push(`/branch?application=${application_id}`);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        setLoadState({ kind: "error", case: caseNumber, error });
      }
    },
    [router],
  );

  // Keyboard shortcuts 1-4 stay scoped to the expanded demo section so number
  // keys never hijack the professional dashboard by surprise.
  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      const target = event.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName;
        if (
          tag === "INPUT" ||
          tag === "TEXTAREA" ||
          tag === "SELECT" ||
          tag === "BUTTON" ||
          target.isContentEditable
        ) {
          return;
        }
      }
      const caseNumber = Number(event.key);
      if (!cases || !Number.isInteger(caseNumber)) return;
      if (!cases.some((demoCase) => demoCase.case === caseNumber)) return;
      if (loadState.kind === "pending") return;
      void handleLoadCase(caseNumber);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, cases, loadState, handleLoadCase]);

  async function handleReset() {
    setResetState("pending");
    try {
      await resetDemo();
      clearNavigationState();
      setLoadState({ kind: "idle" });
      setResetState("done");
      await fetchCases();
      onMutated();
    } catch {
      setResetState("error");
    }
  }

  return (
    <div className="mt-6">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex items-center gap-1.5 text-[12.5px] font-medium text-ink-secondary hover:text-ink"
      >
        <span aria-hidden>{open ? "▾" : "▸"}</span>
        Demo araçları
      </button>

      {open ? (
        <Panel className="mt-2.5">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
            <p className="text-[12px] text-ink-muted">
              Hazır senaryolar gerçek, kalıcı başvurular oluşturur; sonuçları
              her zaman sunucu belirler. Klavyeden 1–4 ile de yüklenebilir.
            </p>
            <Button
              type="button"
              variant="secondary"
              onClick={handleReset}
              disabled={resetState === "pending"}
            >
              {resetState === "pending" ? "Sıfırlanıyor…" : "Demoyu sıfırla"}
            </Button>
          </div>

          {resetState === "done" ? (
            <p className="px-4 pt-3 text-[12.5px] text-success" role="status">
              Demo temel duruma döndürüldü. Eski başvuru numaraları artık
              geçersiz.
            </p>
          ) : resetState === "error" ? (
            <p className="px-4 pt-3 text-[12.5px] text-danger" role="alert">
              Sıfırlama tamamlanamadı. Tekrar deneyin.
            </p>
          ) : null}

          {cases === null && listError === null ? (
            <LoadingState label="Senaryolar yükleniyor…" />
          ) : null}
          {listError ? (
            <ErrorState error={listError} onRetry={fetchCases} />
          ) : null}

          {cases && cases.length === 0 ? (
            <EmptyState title="Tanımlı demo senaryosu yok." />
          ) : null}

          {cases && cases.length > 0 ? (
            <div className="grid grid-cols-1 gap-2.5 p-4 sm:grid-cols-2 xl:grid-cols-4">
              {cases.map((demoCase) => {
                const pending =
                  loadState.kind === "pending" &&
                  loadState.case === demoCase.case;
                const failed =
                  loadState.kind === "error" &&
                  loadState.case === demoCase.case;
                return (
                  <div
                    key={demoCase.case}
                    className="flex h-full flex-col gap-1.5"
                  >
                    <button
                      type="button"
                      onClick={() => handleLoadCase(demoCase.case)}
                      disabled={loadState.kind === "pending"}
                      aria-keyshortcuts={String(demoCase.case)}
                      className="flex h-full flex-col rounded-card border border-border bg-surface p-3 text-left transition-colors hover:border-border-strong hover:bg-surface-hover disabled:pointer-events-none disabled:opacity-50"
                    >
                      <span className="flex w-full items-center justify-between gap-2">
                        <span className="truncate text-[12.5px] font-semibold text-ink">
                          {demoCase.title}
                        </span>
                        <kbd className="flex-none rounded-md border border-border bg-surface-subtle px-1.5 py-px font-mono text-[10px] text-ink-muted">
                          {demoCase.case}
                        </kbd>
                      </span>
                      <span className="mt-1 block text-[11.5px] leading-4 text-ink-secondary">
                        {demoCase.description}
                      </span>
                      <span className="mt-auto block pt-2">
                        <StatusBadge
                          status={
                            ONBOARDING_VERDICT_STATUS[demoCase.expected_verdict]
                          }
                          label={
                            ONBOARDING_VERDICT_LABEL[demoCase.expected_verdict]
                          }
                        />
                      </span>
                    </button>
                    {pending ? (
                      <p
                        className="px-1 text-[11.5px] text-ink-muted"
                        role="status"
                      >
                        Vaka {demoCase.case} yükleniyor…
                      </p>
                    ) : null}
                    {failed ? (
                      <div className="px-1">
                        <ErrorState
                          error={loadState.error}
                          onRetry={() => handleLoadCase(demoCase.case)}
                        />
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : null}
        </Panel>
      ) : null}
    </div>
  );
}
