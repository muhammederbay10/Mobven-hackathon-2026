/**
 * The compact top bar — DESIGN_SYSTEM.md section 8.
 *
 * 54px, bottom border, breadcrumb on the left (with the mobile drawer trigger
 * ahead of it below 768px), route-relevant actions on the right. No search box
 * and no notification/settings icon: there is no real searchable content yet,
 * and the constraints explicitly rule out dead controls added just to match
 * the reference screenshot.
 */

"use client";

import { usePathname } from "next/navigation";

import { MenuIcon } from "./Icon";
import { Breadcrumb, type BreadcrumbItem } from "./UI";

const SECTION_LABEL: Array<{ prefix: string; label: string }> = [
  { prefix: "/branch", label: "Şube İnceleme" },
  { prefix: "/mobile", label: "Mobil İşlemler" },
  { prefix: "/authority", label: "Yetki Kaydı" },
  { prefix: "/registry", label: "Ticaret Sicili" },
];

function breadcrumbFor(pathname: string): BreadcrumbItem[] {
  if (pathname === "/") return [{ label: "Ana Sayfa" }];
  const section = SECTION_LABEL.find((entry) => pathname.startsWith(entry.prefix));
  return [{ label: "Ana Sayfa", href: "/" }, { label: section?.label ?? pathname }];
}

export function SiteHeader({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const pathname = usePathname();

  return (
    <header className="flex h-(--yc-topbar-height) flex-none items-center gap-3 border-b border-border px-5">
      <button
        type="button"
        onClick={onOpenMobileNav}
        aria-label="Menüyü aç"
        className="grid size-9 flex-none place-items-center rounded-control border border-border-strong text-ink-secondary hover:bg-surface-hover md:hidden"
      >
        <MenuIcon />
      </button>

      <Breadcrumb items={breadcrumbFor(pathname)} />

      <div className="ml-auto flex items-center gap-2">
        {/* Route-relevant actions land here. Intentionally empty: no page yet
            has a real primary action to place in the top bar. */}
      </div>
    </header>
  );
}
