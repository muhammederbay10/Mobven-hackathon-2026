import { Card, PageHeading, SectionLabel } from "@/components/Layout";
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

      <div className="grid items-start gap-4.5 lg:grid-cols-[minmax(0,430px)_minmax(0,1fr)]">
        <Card>
          <div className="border-b border-line px-4 py-3.5">
            <div className="text-[15px] font-semibold">MERSİS {mersis}</div>
            <div className="mt-0.5 text-[12.5px] text-ink-3">Kaynak belge ve sürüm bilgisi</div>
          </div>
          <EmptyState
            title="Henüz yetki kaydı yok."
            hint="Şube onayı sonrası oluşur."
          />
        </Card>

        <Card className="overflow-hidden">
          <div className="border-b border-line px-4 py-3.5">
            <SectionLabel>İşlem geçmişi ve denetim izi</SectionLabel>
          </div>
          <EmptyState title="İşlem yok." />
        </Card>
      </div>
    </>
  );
}
