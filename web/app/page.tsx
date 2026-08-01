"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { listDemoCases, loadDemoCase, resetDemo, type DemoCaseCard } from "@/lib/api";
import { ONBOARDING_VERDICT_LABEL, ONBOARDING_VERDICT_STATUS } from "@/lib/format";

import { CardButton, PageHeading, Panel } from "@/components/Layout";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { StatusBadge } from "@/components/Status";
import { Button, Pill } from "@/components/UI";

/**
 * `/` — demo control panel (plan section 10.2, task P1-04).
 *
 * Loading a case calls the real backend endpoint and routes using the
 * persistent application ID it returns; nothing about the outcome is decided
 * here. `application_service`, the comparison engine and the authority
 * services never see a case number (plan sections 1.4 and 18) — this page is
 * the one place that number is allowed to exist, exactly as fixture-loading
 * demo routing.
 *
 * Not yet implemented: keyboard shortcuts 1-4 (Phase 4 frontend step 1) and
 * skip-to-Act-2 (plan section 10.2 — needs a backend endpoint or committed
 * pre-approved fixture that does not exist yet).
 */

const FLOW = [
  "1 · Senaryo yükle",
  "2 · Şube: aslını gör, tara, analiz",
  "3 · Onayla → yetki kaydı oluşur",
  "4 · Mobil şube: işlem yap",
  "5 · Sicil: yetkiyi düşür, tekrar dene",
];

type LoadState = { kind: "idle" } | { kind: "pending"; case: number } | { kind: "error"; case: number; error: unknown };

export default function ControlPanelPage() {
  const router = useRouter();
  const [cases, setCases] = useState<DemoCaseCard[] | null>(null);
  const [listError, setListError] = useState<unknown>(null);
  const [loadState, setLoadState] = useState<LoadState>({ kind: "idle" });
  const [resetState, setResetState] = useState<"idle" | "pending" | "done" | "error">("idle");

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

  async function handleLoadCase(caseNumber: number) {
    setLoadState({ kind: "pending", case: caseNumber });
    try {
      const { application_id } = await loadDemoCase(caseNumber);
      router.push(`/branch?application=${application_id}`);
    } catch (error) {
      setLoadState({ kind: "error", case: caseNumber, error });
    }
  }

  async function handleReset() {
    setResetState("pending");
    try {
      await resetDemo();
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
        <p className="mb-4 text-[13px] text-success">Demo temel duruma döndürüldü.</p>
      ) : resetState === "error" ? (
        <p className="mb-4 text-[13px] text-danger">Sıfırlama tamamlanamadı. Tekrar deneyin.</p>
      ) : null}

      <Panel>
        {cases === null && listError === null ? <LoadingState label="Senaryolar yükleniyor…" /> : null}
        {listError ? <ErrorState error={listError} onRetry={() => fetchCases()} /> : null}
        {cases !== null && cases.length === 0 ? (
          <EmptyState title="Tanımlı demo senaryosu yok." />
        ) : null}

        {cases && cases.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4">
            {cases.map((demoCase) => {
              const pending = loadState.kind === "pending" && loadState.case === demoCase.case;
              const failed = loadState.kind === "error" && loadState.case === demoCase.case;
              return (
                <div key={demoCase.case} className="flex flex-col gap-2">
                  <CardButton
                    onClick={() => handleLoadCase(demoCase.case)}
                    disabled={loadState.kind === "pending"}
                  >
                    <div className="mb-1.5 text-[11px] text-ink-muted">Vaka {demoCase.case}</div>
                    <div className="mb-1.5 text-[14px] font-semibold text-ink">{demoCase.title}</div>
                    <p className="text-[12.5px] leading-5 text-ink-secondary">
                      {demoCase.description}
                    </p>
                    <div className="mt-2.5">
                      <StatusBadge
                        status={ONBOARDING_VERDICT_STATUS[demoCase.expected_verdict]}
                        label={ONBOARDING_VERDICT_LABEL[demoCase.expected_verdict]}
                      />
                    </div>
                  </CardButton>
                  {pending ? (
                    <p className="px-1 text-[12px] text-ink-muted">Yükleniyor…</p>
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
        ) : null}
      </Panel>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        {FLOW.map((step) => (
          <Pill key={step} tone="neutral">
            {step}
          </Pill>
        ))}
      </div>
    </>
  );
}
