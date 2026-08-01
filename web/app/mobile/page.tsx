import { PageHeading, PhoneFrame } from "@/components/Layout";
import { EmptyState } from "@/components/States";
import { SimBadge } from "@/components/Status";

/**
 * `/mobile` — Act 2: transactions and co-signature (plan section 10.4).
 *
 * Skeleton. The person switcher, preset transactions, decision cards and the
 * co-sign flow are task `P4-03`.
 *
 * Two rules this screen exists to honour, both from section 10.4:
 * the route is **gated** until a server-side authority record exists, and a
 * co-signature is completed by the backend — never by client state. The
 * co-signer view is a state of this route, not a route of its own (GAP-14).
 */

export default function MobilePage() {
  return (
    <>
      <PageHeading
        title={
          <>
            Mobil şube — sonraki işlemler
            <SimBadge label="simüle edilmiş banka uygulaması" />
          </>
        }
        subtitle="Belge bir daha istenmez. Her işlemde kayıtlı yetki sorgulanır: kişi, limit, konu, süre ve sicil durumu."
      />

      <div className="flex flex-wrap items-start gap-8">
        <PhoneFrame company="ABC Teknoloji Ltd. Şti." title="Mobil şube">
          <EmptyState
            title="Henüz yetki kaydı yok."
            hint="Şubede bir başvuru onaylandığında bu ekran açılır."
          />
        </PhoneFrame>

        <div className="max-w-95 text-[13px] text-ink-2">
          <h3 className="mb-2 text-[13.5px] text-ink">Bu ekranda ne oluyor?</h3>
          <ul className="mb-4 list-disc pl-4">
            <li className="mb-1.5">
              Belge yeniden okunmuyor — yalnızca yetki kaydı sorgulanıyor.
            </li>
            <li className="mb-1.5">
              Limit aşımında ikinci imza, ikinci yetkilinin telefonuna düşüyor.
            </li>
            <li className="mb-1.5">
              Yetki her işlemde yeniden doğrulanıyor; sicilde düşen yetki anında bloke oluyor.
            </li>
          </ul>
          <p>
            Kararı sunucu verir; bu ekran yalnızca sunucudan gelen kontrolleri gösterir.
          </p>
        </div>
      </div>
    </>
  );
}
