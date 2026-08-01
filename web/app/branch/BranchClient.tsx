"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { getApplication } from "@/lib/api";
import { branchStepForStatus } from "@/lib/branch";
import { rememberApplicationId, rememberMersis } from "@/lib/clientState";
import { APPLICATION_STATUS_LABEL } from "@/lib/format";
import type { ApplicationAggregate } from "@/lib/types";

import { Card, PageHeading, Panel } from "@/components/Layout";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { Button } from "@/components/UI";

import { CreateStep } from "./CreateStep";
import { ReviewStep } from "./ReviewStep";
import { UploadStep } from "./UploadStep";

/**
 * The `/branch` state machine. Backend state is authoritative (guide section
 * 9): the stepper, the visible step and every transition are driven by the
 * aggregate returned from `GET /api/applications/{id}` or by the aggregate a
 * mutation returned — never by a local animation or timer.
 */

const STEPS = [
  { n: 1 as const, label: "Başvuru ve kimlik" },
  { n: 2 as const, label: "Belgeyi tara" },
  { n: 3 as const, label: "İnceleme ve karar" },
];

type AggregateState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; error: unknown }
  | { kind: "ready"; aggregate: ApplicationAggregate };

export function BranchClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const applicationParam = searchParams.get("application");
  const applicationId =
    applicationParam !== null && /^\d+$/.test(applicationParam)
      ? Number(applicationParam)
      : null;
  const invalidParam = applicationParam !== null && applicationId === null;

  const [state, setState] = useState<AggregateState>({ kind: "idle" });
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async (id: number, { silent = false } = {}) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    if (!silent) setState({ kind: "loading" });
    try {
      const aggregate = await getApplication(id, controller.signal);
      setState({ kind: "ready", aggregate });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setState({ kind: "error", error });
    }
  }, []);

  useEffect(() => {
    if (applicationId === null) {
      setState({ kind: "idle" });
      return;
    }
    load(applicationId);
    return () => abortRef.current?.abort();
  }, [applicationId, load]);

  // ANALYSIS_IN_PROGRESS / refresh mid-analysis: poll conservatively while the
  // server says ANALYZING (guide section 11). The poll only refetches; it never
  // advances anything locally.
  const status = state.kind === "ready" ? state.aggregate.application.status : null;
  useEffect(() => {
    if (status !== "ANALYZING" || applicationId === null) return;
    const timer = setInterval(() => load(applicationId, { silent: true }), 2500);
    return () => clearInterval(timer);
  }, [status, applicationId, load]);

  // Navigation memory (cleared on demo reset). Never a substitute for the URL.
  useEffect(() => {
    if (applicationId !== null) rememberApplicationId(applicationId);
    if (state.kind === "ready" && state.aggregate.authority) {
      rememberMersis(state.aggregate.authority.mersis);
    }
  }, [applicationId, state]);

  /** Every mutation renders the aggregate the server returned (guide §9). */
  const handleAggregate = useCallback((aggregate: ApplicationAggregate) => {
    setState({ kind: "ready", aggregate });
  }, []);

  const refetch = useCallback(() => {
    if (applicationId !== null) load(applicationId, { silent: true });
  }, [applicationId, load]);

  const activeStep = branchStepForStatus(status);

  return (
    <>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <PageHeading
          title="Şube — kurumsal başvuru ve ön kontrol"
          subtitle="Müşteri sirkülerin aslını şubeye getirir. Görevli kimliği ve belgenin aslını görür, tarar; sistem okur ve karşılaştırır."
        />
        {status !== null ? (
          <span className="rounded-pill border border-border-strong px-3 py-1 text-[12px] text-ink-secondary">
            Durum: <b className="font-semibold text-ink">{APPLICATION_STATUS_LABEL[status]}</b>
          </span>
        ) : null}
      </div>

      <Panel className="overflow-hidden">
        <ol className="flex border-b border-border">
          {STEPS.map((step) => {
            const isActive = step.n === activeStep;
            const isDone = step.n < activeStep;
            return (
              <li
                key={step.n}
                aria-current={isActive ? "step" : undefined}
                className={`flex flex-1 items-center gap-2.5 border-r border-border px-4 py-3 text-[13px] last:border-r-0 ${
                  isActive ? "font-semibold text-ink" : "text-ink-muted"
                }`}
              >
                <span
                  className={`grid size-5 flex-none place-items-center rounded-full text-[11px] font-semibold ${
                    isDone
                      ? "bg-success-soft text-success"
                      : isActive
                        ? "bg-ink text-white"
                        : "bg-surface-subtle text-ink-secondary"
                  }`}
                  aria-hidden
                >
                  {isDone ? "✓" : step.n}
                </span>
                {step.label}
              </li>
            );
          })}
        </ol>

        {invalidParam ? (
          <EmptyState
            title="Geçersiz başvuru numarası."
            hint={
              <Link className="underline" href="/branch">
                Yeni başvuru başlatın
              </Link>
            }
          />
        ) : applicationId === null ? (
          <CreateStep
            onCreated={(view) => router.replace(`/branch?application=${view.id}`)}
          />
        ) : state.kind === "loading" || state.kind === "idle" ? (
          <LoadingState label="Başvuru sunucudan yükleniyor…" />
        ) : state.kind === "error" ? (
          <ErrorState
            error={state.error}
            onRetry={() => load(applicationId)}
            title="Başvuru yüklenemedi"
          />
        ) : (
          <BranchBody
            aggregate={state.aggregate}
            onAggregate={handleAggregate}
            onRefetch={refetch}
            onStartNew={() => router.push("/branch")}
          />
        )}
      </Panel>
    </>
  );
}

function BranchBody({
  aggregate,
  onAggregate,
  onRefetch,
  onStartNew,
}: {
  aggregate: ApplicationAggregate;
  onAggregate: (aggregate: ApplicationAggregate) => void;
  onRefetch: () => void;
  onStartNew: () => void;
}) {
  const { application } = aggregate;

  switch (application.status) {
    case "DRAFT":
      // The backend has no endpoint to attest identity after creation (guide
      // section 9) — show the record honestly and offer a corrected restart.
      return (
        <div className="p-4">
          <Card className="max-w-xl">
            <h4 className="mb-1 text-[14px] font-semibold text-ink">
              Bu başvuruda şubede kimlik doğrulaması tamamlanmamış.
            </h4>
            <p className="mb-3 text-[12.5px] leading-5 text-ink-secondary">
              #{application.id} numaralı kayıt taslak durumda. Mevcut süreçte kimlik
              doğrulaması başvuru oluşturulurken yapılır; bu kaydı ilerletmek mümkün değil.
              Doğru bilgilerle yeni bir başvuru başlatın.
            </p>
            <Button type="button" variant="primary" onClick={onStartNew}>
              Yeni başvuru başlat
            </Button>
          </Card>
        </div>
      );
    case "IDENTITY_VERIFIED":
    case "DOCUMENT_SCANNED":
    case "ANALYZING":
    case "ANALYSIS_FAILED":
      return <UploadStep aggregate={aggregate} onAggregate={onAggregate} onRefetch={onRefetch} />;
    case "ANALYZED":
    case "APPROVED":
      return <ReviewStep aggregate={aggregate} onAggregate={onAggregate} />;
    case "DOC_REQUESTED":
    case "ESCALATED":
      return (
        <TerminalResult
          aggregate={aggregate}
          onStartNew={onStartNew}
        />
      );
  }
}

function TerminalResult({
  aggregate,
  onStartNew,
}: {
  aggregate: ApplicationAggregate;
  onStartNew: () => void;
}) {
  const { application } = aggregate;
  const escalated = application.status === "ESCALATED";
  return (
    <div className="p-4">
      <Card className="max-w-xl">
        <h4 className="mb-1 text-[14px] font-semibold text-ink">
          {escalated
            ? "Başvuru uyum birimine iletildi."
            : "Müşteriden yeni belge istendi."}
        </h4>
        <p className="mb-3 text-[12.5px] leading-5 text-ink-secondary">
          {escalated
            ? `#${application.id} numaralı başvuru şube tarafında kapatıldı ve inceleme için uyum birimine devredildi.`
            : `#${application.id} numaralı başvuru bu belgeyle ilerleyemez. Okunaklı ve güncel bir nüsha geldiğinde yeni başvuru açılır.`}
        </p>
        <Button type="button" variant="primary" onClick={onStartNew}>
          Yeni başvuru başlat
        </Button>
      </Card>
    </div>
  );
}
