import { Panel, PageHeading } from "@/components/Layout";
import { EmptyState } from "@/components/States";

/**
 * `/branch` — Act 1: intake, scan, review, decision (plan section 10.3).
 *
 * Skeleton. The three-step flow is tasks `P1-05` (intake and scan) and `P2-01`
 * to `P2-03` (review, correction, decision).
 *
 * The application ID lives in the URL query, never only in component memory
 * (section 10.3) — that is what lets a refresh restore progress from the server
 * instead of dropping the presenter back to step 1. The stepper below is driven
 * by the backend application status, not by local completion guesses.
 */

const STEPS = [
  { n: 1, label: "Başvuru ve kimlik" },
  { n: 2, label: "Belgeyi tara" },
  { n: 3, label: "İnceleme ve karar" },
];

export default async function BranchPage({
  searchParams,
}: {
  searchParams: Promise<{ application?: string }>;
}) {
  const { application } = await searchParams;
  const applicationId = application ? Number(application) : null;
  const hasApplication = applicationId !== null && Number.isInteger(applicationId);

  return (
    <>
      <PageHeading
        title="Şube — kurumsal başvuru ve ön kontrol"
        subtitle="Müşteri sirkülerin aslını şubeye getirir. Görevli kimliği ve belgenin aslını görür, tarar; sistem okur ve karşılaştırır."
      />

      <Panel className="overflow-hidden">
        <ol className="flex border-b border-border">
          {STEPS.map((step) => (
            <li
              key={step.n}
              className="flex flex-1 items-center gap-2.5 border-r border-border px-4 py-3 text-[13px] text-ink-muted last:border-r-0"
            >
              <span className="grid size-5 flex-none place-items-center rounded-full bg-surface-subtle text-[11px] font-semibold text-ink-secondary">
                {step.n}
              </span>
              {step.label}
            </li>
          ))}
        </ol>

        {hasApplication ? (
          <EmptyState
            title={`Başvuru #${applicationId} yüklendi.`}
            hint="Adım ekranları P1-05 ve P2-01 ile gelir."
          />
        ) : (
          <EmptyState
            title="Demo kontrol ekranından bir senaryo yükleyin."
            hint="Başvuru numarası adres satırında taşınır; sayfa yenilense de ilerleme sunucudan geri gelir."
          />
        )}
      </Panel>
    </>
  );
}
