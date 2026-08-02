"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, getRegistry, updateRegistryRepresentative } from "@/lib/api";
import { AUTHORITY_MODE_LABEL, formatDate } from "@/lib/format";
import type { Registry, RegistryCompany, RegistryRepresentative } from "@/lib/types";

import { Panel, PageHeading } from "@/components/Layout";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { SimBadge, StatusBadge } from "@/components/Status";
import { Button } from "@/components/UI";

/** Test-registry administration for company representatives. */

type RegistryState =
  | { kind: "loading" }
  | { kind: "error"; error: unknown }
  | { kind: "ready"; registry: Registry };

export default function RegistryPage() {
  const [state, setState] = useState<RegistryState>({ kind: "loading" });
  const [demoDisabled, setDemoDisabled] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setState({ kind: "loading" });
    try {
      const registry = await getRegistry(controller.signal);
      setState({ kind: "ready", registry });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setState({ kind: "error", error });
    }
  }, []);

  useEffect(() => {
    load();
    return () => abortRef.current?.abort();
  }, [load]);

  function replaceCompany(company: RegistryCompany) {
    setState((current) =>
      current.kind === "ready"
        ? {
            kind: "ready",
            registry: {
              ...current.registry,
              companies: current.registry.companies.map((existing) =>
                existing.mersis === company.mersis ? company : existing,
              ),
            },
          }
        : current,
    );
  }

  return (
    <>
      <PageHeading
        title={
          <>
            Sicil kayıtları
            <SimBadge label="test ortamı" />
          </>
        }
        subtitle="Yetki kontrollerinde kullanılan şirket ve temsilci durumlarını görüntüleyin."
      />

      <div className="mb-5 rounded-panel border border-warning/20 bg-warning-soft px-4 py-3 text-[13px] text-warning">
        <span aria-hidden>! </span>
        Bu ekran test ortamındaki sicil kayıtlarını gösterir. Bir temsilcinin yetkisini
        kaldırdığınızda yeni başvurular ve mobil işlemler güncel duruma göre değerlendirilir.
      </div>

      {demoDisabled ? (
        <div className="mb-5 rounded-panel border border-border bg-surface-subtle px-4 py-3 text-[13px] text-ink-secondary">
          Sicil kayıtları şu anda yalnızca görüntülenebilir. Değişiklik işlemleri bu ortamda kapalıdır.
        </div>
      ) : null}

      {state.kind === "loading" ? (
        <Panel>
          <LoadingState label="Sicil kayıtları yükleniyor…" />
        </Panel>
      ) : state.kind === "error" ? (
        <Panel>
          <ErrorState error={state.error} onRetry={load} title="Sicil yüklenemedi" />
        </Panel>
      ) : state.kind === "ready" && state.registry.companies.length === 0 ? (
        <Panel>
          <EmptyState title="Sicilde kayıtlı şirket yok." />
        </Panel>
      ) : (
        <div className="flex flex-col gap-5">
          {state.registry.companies.map((company) => (
            <CompanyPanel
              key={company.mersis}
              company={company}
              readOnly={demoDisabled}
              onCompany={replaceCompany}
              onDemoDisabled={() => setDemoDisabled(true)}
            />
          ))}
        </div>
      )}
    </>
  );
}

function CompanyPanel({
  company,
  readOnly,
  onCompany,
  onDemoDisabled,
}: {
  company: RegistryCompany;
  readOnly: boolean;
  onCompany: (company: RegistryCompany) => void;
  onDemoDisabled: () => void;
}) {
  return (
    <Panel
      title={
        <span className="flex flex-wrap items-center gap-x-2">
          {company.legal_name}
          <StatusBadge
            status={company.status === "ACTIVE" ? "green" : "red"}
            label={company.status === "ACTIVE" ? "Şirket aktif" : "Şirket pasif"}
          />
        </span>
      }
      actions={
        <span className="text-[12px] text-ink-muted">
          MERSİS <span className="font-mono">{company.mersis}</span> · VKN{" "}
          <span className="font-mono">{company.tax_number}</span>
        </span>
      }
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-[13px]">
          <thead>
            <tr className="border-b border-border text-[11px] uppercase tracking-[0.06em] text-ink-muted">
              <th className="px-4 py-2.5 font-semibold">Temsilci</th>
              <th className="px-4 py-2.5 font-semibold">TCKN</th>
              <th className="px-4 py-2.5 font-semibold">İmza şekli</th>
              <th className="px-4 py-2.5 font-semibold">Geçerlilik</th>
              <th className="px-4 py-2.5 font-semibold">Durum</th>
              <th className="px-4 py-2.5 font-semibold">İşlem</th>
            </tr>
          </thead>
          <tbody>
            {company.representatives.map((rep) => (
              <RepresentativeRow
                key={rep.id}
                mersis={company.mersis}
                representative={rep}
                readOnly={readOnly}
                onCompany={onCompany}
                onDemoDisabled={onDemoDisabled}
              />
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function RepresentativeRow({
  mersis,
  representative,
  readOnly,
  onCompany,
  onDemoDisabled,
}: {
  mersis: string;
  representative: RegistryRepresentative;
  readOnly: boolean;
  onCompany: (company: RegistryCompany) => void;
  onDemoDisabled: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const removed = representative.status === "REMOVED";
  const nextStatus = removed ? "ACTIVE" : "REMOVED";

  async function applyChange() {
    setPending(true);
    setError(null);
    try {
      const company = await updateRegistryRepresentative(mersis, representative.id, {
        status: nextStatus,
      });
      onCompany(company);
      setConfirming(false);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      if (cause instanceof ApiError && cause.code === "DEMO_MODE_DISABLED") {
        onDemoDisabled();
        setConfirming(false);
      }
      setError(cause);
    } finally {
      setPending(false);
    }
  }

  return (
    <tr className={`border-b border-border/60 last:border-b-0 ${pending ? "opacity-60" : ""}`}>
      <td className="px-4 py-2.5">
        <div className="font-medium text-ink">{representative.name}</div>
        <div className="font-mono text-[11px] text-ink-muted">{representative.id}</div>
      </td>
      <td className="px-4 py-2.5 font-mono text-[12px] text-ink-secondary">
        {representative.tckn}
      </td>
      <td className="px-4 py-2.5 text-ink-secondary">
        {AUTHORITY_MODE_LABEL[representative.mode]}
      </td>
      <td className="px-4 py-2.5 text-ink-secondary">{formatDate(representative.effective_at)}</td>
      <td className="px-4 py-2.5">
        <StatusBadge
          status={removed ? "red" : "green"}
          label={removed ? "Yetki düşürüldü" : "Yetkili"}
        />
      </td>
      <td className="px-4 py-2.5">
        {readOnly ? (
          <span className="text-[12px] text-ink-muted">Salt okunur</span>
        ) : confirming ? (
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="text-[12px] text-ink-secondary">
              {removed ? "Yetki geri verilsin mi?" : "Yetki düşürülsün mü?"}
            </span>
            <Button
              type="button"
              variant={removed ? "primary" : "danger"}
              className="!h-7 !px-2.5 !text-[12px]"
              disabled={pending}
              onClick={applyChange}
            >
              {pending ? "Kaydediliyor…" : "Evet"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="!h-7 !px-2.5 !text-[12px]"
              disabled={pending}
              onClick={() => setConfirming(false)}
            >
              Vazgeç
            </Button>
          </span>
        ) : (
          <Button
            type="button"
            variant={removed ? "secondary" : "danger"}
            className="!h-7 !px-2.5 !text-[12px]"
            onClick={() => setConfirming(true)}
          >
            {removed ? "Geri yükle" : "Yetkiyi düşür"}
          </Button>
        )}
        {error instanceof ApiError && error.code !== "DEMO_MODE_DISABLED" ? (
          <div className="mt-1 text-[11.5px] text-danger" role="alert">
            {error.message}
          </div>
        ) : null}
      </td>
    </tr>
  );
}
