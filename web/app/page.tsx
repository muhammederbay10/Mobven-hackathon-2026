"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { listDemoCases, loadDemoCase, resetDemo, type DemoCaseCard } from "@/lib/api";
import { clearNavigationState } from "@/lib/clientState";
import { ONBOARDING_VERDICT_LABEL, ONBOARDING_VERDICT_STATUS } from "@/lib/format";

import { CardButton, PageHeading, Panel } from "@/components/Layout";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { StatusBadge } from "@/components/Status";
import { Button, Pill } from "@/components/UI";

/**
 * `/` — demo control panel (plan section 10.2, task P1-04 + Phase 4 polish).
 *
 * Loading a case calls the real backend endpoint and routes using the
 * persistent application ID it returns; nothing about the outcome is decided
 * here. This page is the only place a case number is allowed to exist.
 *
 * "Skip to Act 2" stays a disabled control: no backend endpoint can create a
 * pre-approved authority, and faking one client-side is exactly what the
 * alignment guide forbids (section 10.2 / blocker 1).
 */

const FLOW = [
  "1 · Senaryo yükle",
  "2 · Şube: aslını gör, tara, analiz",
  "3 · Onayla → yetki kaydı oluşur",
  "4 · Mobil şube: işlem yap",
  "5 · Sicil: yetkiyi düşür, tekrar dene",
];

type LoadState =
  | { kind: "idle" }
  | { kind: "pending"; case: number }
  | { kind: "error"; case: number; error: unknown };

export default function ControlPanelPage() {
  const router = useRouter();
  const [cases, setCases] = useState<DemoCaseCard[] | null>(null);
  const [listError, setListError] = useState<unknown>(null);
  const [loadState, setLoadState] = useState<LoadState>({ kind: "idle" });
  const [resetState, setResetState] = useState<"idle" | "pending" | "done" | "error">("idle");
  const loadAbortRef = useRef<AbortController | null>(null);

  const fetchCases = useCallback(async (signal?: AbortSignal) => {
    setListError(null);
    setCases(null);
    try {
      const response = await listDemoCases(signal);
      setCases(response.cases);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setListError(error);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchCases(controller.signal);
    return () => controller.abort();
  }, [fetchCases]);

  const handleLoadCase = useCallback(
    async (caseNumber: number) => {
      // Loading a different case aborts the old request and clears its result
      // visually; server state remains authoritative (guide section 10).
      loadAbortRef.current?.abort();
      const controller = new AbortController();
      loadAbortRef.current = controller;
      setLoadState({ kind: "pending", case: caseNumber });
      try {
        const { application_id } = await loadDemoCase(caseNumber, controller.signal);
        router.push(`/branch?application=${application_id}`);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setLoadState({ kind: "error", case: caseNumber, error });
      }
    },
    [router],
  );

  // Keyboard shortcuts 1-4 — only when focus is not inside an interactive
  // element (guide section 10). Same handler as clicking the card.
  useEffect(() => {
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
  }, [cases, loadState, handleLoadCase]);

  async function handleReset() {
    setResetState("pending");
    try {
      await resetDemo();
      // Old database IDs no longer exist — drop remembered navigation and any
      // stale case-load result (guide section 16).
      clearNavigationState();
      setLoadState({ kind: "idle" });
      setResetState("done");
      await fetchCases();
    } catch {
      setResetState("error");
    }
  }

  return (
    <>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <PageHeading
          title="Demo senaryoları"
          subtitle="İmza sirkülerinin aslı yalnızca ilk seferde şubede görülür. Sonrasındaki tüm işlemler mobil şubeden, kayıtlı yetki üzerinden yürür."
        />
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
        <p className="mb-4 text-[13px] text-success" role="status">
          Demo temel duruma döndürüldü. Eski başvuru numaraları artık geçersiz.
        </p>
      ) : resetState === "error" ? (
        <p className="mb-4 text-[13px] text-danger" role="alert">
          Sıfırlama tamamlanamadı. Tekrar deneyin.
        </p>
      ) : null}

      {cases === null && listError === null ? (
        <Panel>
          <LoadingState label="Senaryolar yükleniyor…" />
        </Panel>
      ) : null}
      {listError ? (
        <Panel>
          <ErrorState error={listError} onRetry={() => fetchCases()} />
        </Panel>
      ) : null}
      {cases !== null && cases.length === 0 ? (
        <Panel>
          <EmptyState title="Tanımlı demo senaryosu yok." />
        </Panel>
      ) : null}

      {cases && cases.length > 0 ? (
        // The KPI strip from the reference: cards on a soft accent wash.
        // Decorative only — verdict colors still come from StatusBadge.
        <div
          className="rounded-panel p-3.5"
          style={{ background: "var(--yc-gradient-wash)" }}
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {cases.map((demoCase) => {
              const pending = loadState.kind === "pending" && loadState.case === demoCase.case;
              const failed = loadState.kind === "error" && loadState.case === demoCase.case;
              return (
                <div key={demoCase.case} className="flex h-full flex-col gap-2">
                  {/* h-full + flex-1 chain: every card stretches to the row's
                      height, so a longer description never makes one card
                      taller than its neighbors. */}
                  <CardButton
                    onClick={() => handleLoadCase(demoCase.case)}
                    disabled={loadState.kind === "pending"}
                    aria-keyshortcuts={String(demoCase.case)}
                    className="flex flex-1 flex-col !p-0 shadow-panel"
                  >
                    <div className="flex items-center justify-between gap-2 px-3.5 pb-2 pt-3">
                      <span className="truncate text-[13px] font-semibold text-ink">
                        {demoCase.title}
                      </span>
                      <kbd className="flex-none rounded-[6px] border border-border bg-surface-subtle px-1.5 py-px font-mono text-[10px] text-ink-muted">
                        {demoCase.case}
                      </kbd>
                    </div>
                    <div className="mx-2.5 mb-2.5 flex-1 rounded-card border border-border bg-surface px-3 py-2.5 shadow-panel">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[24px] font-semibold leading-7 tracking-[-0.01em] text-ink">
                          {demoCase.case}
                        </span>
                        <StatusBadge
                          status={ONBOARDING_VERDICT_STATUS[demoCase.expected_verdict]}
                          label={ONBOARDING_VERDICT_LABEL[demoCase.expected_verdict]}
                        />
                      </div>
                      <p className="mt-1.5 text-[12px] leading-[18px] text-ink-secondary">
                        {demoCase.description}
                      </p>
                    </div>
                  </CardButton>
                  {pending ? (
                    <p className="px-1 text-[12px] text-ink-muted" role="status">
                      Vaka {demoCase.case} yükleniyor…
                    </p>
                  ) : null}
                  {failed ? (
                    <div className="px-1">
                      <ErrorState error={loadState.error} onRetry={() => handleLoadCase(demoCase.case)} />
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      <div className="mt-5 flex flex-wrap items-center gap-2">
        {FLOW.map((step) => (
          <Pill key={step} tone="neutral">
            {step}
          </Pill>
        ))}
      </div>

      <div className="mt-4">
        <Button
          type="button"
          disabled
          title="Sunucu tarafında ön onaylı yetki oluşturan bir uç nokta henüz yok; istemci tarafında taklit edilmez."
        >
          Doğrudan 2. perdeye geç (backend bekliyor)
        </Button>
        <p className="mt-1.5 max-w-xl text-[11.5px] text-ink-muted">
          Geliştirici notu: bu kontrol, onaylı bir başvuru + yetki kaydını sunucuda oluşturan bir
          demo uç noktası eklenene kadar devre dışıdır. Yerel durumla “onaylanmış gibi” yapmak
          hizalama rehberince yasak.
        </p>
      </div>
    </>
  );
}
