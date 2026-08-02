"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { lastMersis } from "@/lib/clientState";

import { Panel, PageHeading } from "@/components/Layout";
import { EmptyState } from "@/components/States";

/**
 * Landing state for the `/authority` segment.
 *
 * Not a sixth route (GAP-14). `/authority/[mersis]` is the frozen screen; this
 * page only gives the sidebar's "Yetki Kaydı" item somewhere to land before a
 * MERSİS is known. If this session already visited one (an approval or a
 * mobile screen), it is offered as a link — the URL stays the authority.
 */

export default function AuthorityIndexPage() {
  const [knownMersis, setKnownMersis] = useState<string | null>(null);

  // sessionStorage is browser-only; read it after mount.
  useEffect(() => {
    setKnownMersis(lastMersis());
  }, []);

  return (
    <>
      <PageHeading
        title="Yetki kaydı — banka tarafı"
        subtitle="Şube onayıyla oluşan yapılandırılmış yetki. Tüm kanallar bu kaydı sorgular."
      />
      <Panel>
        {knownMersis ? (
          <EmptyState
            title="Bu oturumda görüntülenen bir yetki kaydı var."
            hint={
              <Link href={`/authority/${knownMersis}`} className="underline">
                MERSİS {knownMersis} yetki kaydını aç
              </Link>
            }
          />
        ) : (
          <EmptyState
            title="Henüz yetki kaydı yok."
            hint="Şubede bir başvuru onaylandığında kayıt burada görünür."
          />
        )}
      </Panel>
    </>
  );
}
