import { Card, PageHeading } from "@/components/Layout";
import { EmptyState } from "@/components/States";
import { SimBadge } from "@/components/Status";

/**
 * `/registry` — simulated trade-registry administration (plan section 10.6).
 *
 * Skeleton. The company-grouped representative table, remove/restore controls
 * and the demo-only raw JSON panel are task `P2-04`.
 *
 * This screen is shown on a projector while a judge watches an authority get
 * revoked, so it is deliberately large-type and high-contrast, and the
 * simulated-service notice is permanent rather than dismissible (section 14:
 * a simulated integration is never presented as an unlabeled fake).
 */

export default function RegistryPage() {
  return (
    <>
      <PageHeading
        title={
          <>
            Sicil kayıtları
            <SimBadge />
          </>
        }
        subtitle="Prototipte MERSİS yerine yerel mock servis. Üretimde kurumsal entegrasyon gerekir."
      />

      <div className="mb-4.5 rounded-control bg-warn-bg px-4 py-3 text-[13.5px] text-warn">
        <span aria-hidden>! </span>
        Bu ekran gerçek MERSİS değildir. Yetkiyi düşürdüğünüzde hem yeni başvuru hem de mobil işlem
        anında bloke olur.
      </div>

      <Card className="overflow-hidden">
        <EmptyState
          title="Sicil tablosu henüz bağlanmadı."
          hint="Şirket ve temsilci listesi P2-04 ile gelir."
        />
      </Card>
    </>
  );
}
