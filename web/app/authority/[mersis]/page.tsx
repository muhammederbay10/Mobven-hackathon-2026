import { Panel, PageHeading } from "@/components/Layout";
import { EmptyState } from "@/components/States";

/**
 * `/authority/[mersis]` — the bank-side authority record (plan section 10.5).
 *
 * Skeleton. The source metadata, version/status, people with their current
 * registry status, the rules table and the transaction/audit history are task
 * `P4-04`.
 *
 * Audit is a **section of this route**, not a route of its own (GAP-14) — hence
 * the two-column layout below rather than a separate screen.
 */

export default async function AuthorityRecordPage({
  params,
}: {
  params: Promise<{ mersis: string }>;
}) {
  const { mersis } = await params;

  return (
    <>
      <PageHeading
        title="Yetki kaydı — banka tarafı"
        subtitle="Şube onayıyla oluşan yapılandırılmış yetki. Tüm kanallar bu kaydı sorgular."
      />

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,430px)_minmax(0,1fr)]">
        <Panel title={`MERSİS ${mersis}`}>
          <EmptyState
            title="Henüz yetki kaydı yok."
            hint="Şube onayı sonrası oluşur."
          />
        </Panel>

        <Panel title="İşlem geçmişi ve denetim izi">
          <EmptyState title="İşlem yok." />
        </Panel>
      </div>
    </>
  );
}
