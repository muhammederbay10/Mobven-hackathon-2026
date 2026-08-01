import { Card, PageHeading } from "@/components/Layout";
import { EmptyState } from "@/components/States";

/**
 * Empty state for the `/authority` segment.
 *
 * Not a sixth route (GAP-14). `/authority/[mersis]` is the frozen screen; this
 * file only gives the header's "Yetki kaydı" link somewhere to land before a
 * record exists, and holds no content of its own. Once an authority record has
 * been created, navigation goes straight to `/authority/{mersis}`.
 */

export default function AuthorityIndexPage() {
  return (
    <>
      <PageHeading
        title="Yetki kaydı — banka tarafı"
        subtitle="Şube onayıyla oluşan yapılandırılmış yetki. Tüm kanallar bu kaydı sorgular."
      />
      <Card>
        <EmptyState
          title="Henüz yetki kaydı yok."
          hint="Şubede bir başvuru onaylandığında kayıt burada görünür."
        />
      </Card>
    </>
  );
}
