import { Card, PageHeading } from "@/components/Layout";
import { EmptyState } from "@/components/States";

/**
 * `/` — demo control panel (plan section 10.2).
 *
 * Skeleton. The four case cards, the keyboard shortcuts, skip-to-Act-2 and the
 * reset button are task `P1-04`; each of them creates real server state through
 * `lib/api.ts` rather than any client-side flag.
 */

const FLOW = [
  "1 · Senaryo yükle",
  "2 · Şube: aslını gör, tara, analiz",
  "3 · Onayla → yetki kaydı oluşur",
  "4 · Mobil şube: işlem yap",
  "5 · Sicil: yetkiyi düşür, tekrar dene",
];

export default function ControlPanelPage() {
  return (
    <>
      <PageHeading
        title="Demo senaryoları"
        subtitle="İmza sirkülerinin aslı yalnızca ilk seferde şubede görülür. Sonrasındaki tüm işlemler mobil şubeden, kayıtlı yetki üzerinden yürür."
      />

      <Card>
        <EmptyState
          title="Senaryo kartları henüz bağlanmadı."
          hint="Dört vaka kartı ve sıfırlama kontrolü P1-04 ile gelir."
        />
      </Card>

      <div className="mt-[22px] flex flex-wrap items-center gap-2 text-[13px] text-ink-2">
        {FLOW.map((step, index) => (
          <span key={step} className="contents">
            <span className="rounded-full border border-line bg-surface px-3 py-1.5">{step}</span>
            {index < FLOW.length - 1 ? (
              <span className="text-ink-3" aria-hidden>
                →
              </span>
            ) : null}
          </span>
        ))}
      </div>
    </>
  );
}
