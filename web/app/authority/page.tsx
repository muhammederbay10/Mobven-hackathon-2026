import { Panel, PageHeading } from "@/components/Layout";
import { EmptyState } from "@/components/States";

/**
 * Landing state for the `/authority` segment.
 *
 * Not a sixth route (GAP-14). `/authority/[mersis]` is the frozen screen; this
 * file only gives the sidebar's "Yetki Kaydı" item somewhere to land before any
 * MERSİS is known — the sidebar itself must not guess one (DESIGN_SYSTEM.md
 * section 7). Once an authority record exists, navigation goes straight to
 * `/authority/{mersis}`.
 */

export default function AuthorityIndexPage() {
  return (
    <>
      <PageHeading
        title="Yetki kaydı — banka tarafı"
        subtitle="Şube onayıyla oluşan yapılandırılmış yetki. Tüm kanallar bu kaydı sorgular."
      />
      <Panel>
        <EmptyState
          title="Henüz yetki kaydı yok."
          hint="Şubede bir başvuru onaylandığında kayıt burada görünür."
        />
      </Panel>
    </>
  );
}
