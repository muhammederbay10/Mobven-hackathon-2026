/**
 * Application header and route navigation.
 *
 * The five routes are frozen (plan GAP-14): a sixth may be added only if it
 * replaces an existing one, and only before H30. Audit is a section of
 * `/authority`, and the co-signer view is a state of `/mobile` — neither gets
 * its own entry here.
 */

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ROUTES = [
  { href: "/", label: "Demo kontrol", act: null },
  { href: "/branch", label: "Şube", act: "1·" },
  { href: "/mobile", label: "Mobil şube", act: "2·" },
  { href: "/authority", label: "Yetki kaydı", act: null },
  { href: "/registry", label: "Sicil (mock)", act: null },
] as const;

export function SiteHeader() {
  const pathname = usePathname();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <header className="mb-[22px] flex flex-wrap items-center gap-5 border-b border-line py-3.5">
      <Link href="/" className="flex items-center gap-2.5 text-[17px] font-semibold tracking-[-0.01em]">
        <span className="grid size-[26px] place-items-center rounded-[7px] bg-brand text-[13px] font-bold text-white">
          Y
        </span>
        YetkiCheck
      </Link>

      {/* Section 14: simulated components stay visibly labeled, everywhere. */}
      <span className="rounded-full border border-dashed border-line-strong px-2.5 py-0.5 text-xs text-ink-3">
        demo — simüle edilmiş banka ortamı
      </span>

      <nav className="ml-auto flex flex-wrap gap-1" aria-label="Ekranlar">
        {ROUTES.map((route) => (
          <Link
            key={route.href}
            href={route.href}
            aria-current={isActive(route.href) ? "page" : undefined}
            className={
              isActive(route.href)
                ? "rounded-lg border border-line-strong bg-surface px-3.5 py-[7px] text-sm font-medium text-ink"
                : "rounded-lg border border-transparent px-3.5 py-[7px] text-sm text-ink-2 hover:bg-surface"
            }
          >
            {route.act ? <span className="mr-[3px] text-[10.5px] text-ink-3">{route.act}</span> : null}
            {route.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
