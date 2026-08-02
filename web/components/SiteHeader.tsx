/**
 * The compact top bar — DESIGN_SYSTEM.md section 8, aligned to the reference
 * PNG: icon breadcrumb on the left (with the mobile drawer trigger below
 * 768px), then a search field with a ⌘K hint, a notification bell, and the
 * single gradient primary action on the right. The accent gradient is
 * reserved for exactly this one control (section 3).
 */

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import type { ComponentType } from "react";

import {
  BellIcon,
  DocumentCheckIcon,
  HomeIcon,
  LandmarkIcon,
  MenuIcon,
  PlusIcon,
  SearchIcon,
  ShieldCheckIcon,
  SmartphoneIcon,
} from "./Icon";
import { Breadcrumb, type BreadcrumbItem } from "./UI";

const SECTION_LABEL: Array<{
  prefix: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
}> = [
  { prefix: "/branch", label: "Şube İnceleme", icon: DocumentCheckIcon },
  { prefix: "/mobile", label: "Mobil İşlemler", icon: SmartphoneIcon },
  { prefix: "/authority", label: "Yetki Kaydı", icon: ShieldCheckIcon },
  { prefix: "/registry", label: "Ticaret Sicili", icon: LandmarkIcon },
];

function breadcrumbFor(pathname: string): BreadcrumbItem[] {
  const home: BreadcrumbItem = { label: "Ana Sayfa", href: "/", icon: <HomeIcon /> };
  if (pathname === "/") return [home];
  const section = SECTION_LABEL.find((entry) => pathname.startsWith(entry.prefix));
  if (!section) return [home, { label: pathname }];
  const Icon = section.icon;
  return [home, { label: section.label, icon: <Icon /> }];
}

export function SiteHeader({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const pathname = usePathname();
  const searchRef = useRef<HTMLInputElement>(null);

  // ⌘K / Ctrl+K focuses the search field, matching the hint chip.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

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
        {/* Search — hidden on very narrow widths to keep the bar one line. */}
        <label className="relative hidden items-center sm:flex">
          <span className="pointer-events-none absolute left-2.5 text-ink-muted" aria-hidden>
            <SearchIcon />
          </span>
          <input
            ref={searchRef}
            type="search"
            placeholder="Kayıtlarda ara…"
            aria-label="Kayıtlarda ara"
            className="h-8.5 w-52 rounded-control border border-border-strong bg-surface pl-8.5 pr-11 text-[12.5px] text-ink placeholder:text-ink-muted focus-visible:border-info"
          />
          <kbd className="pointer-events-none absolute right-2 rounded-[6px] border border-border bg-surface-subtle px-1.5 py-px font-mono text-[10px] text-ink-muted">
            ⌘K
          </kbd>
        </label>

        <button
          type="button"
          aria-label="Bildirimler"
          title="Bildirimler"
          className="grid size-8.5 flex-none place-items-center rounded-control text-ink-secondary transition-colors hover:bg-surface-hover"
        >
          <BellIcon />
        </button>

        {/* The one sanctioned gradient action (DESIGN_SYSTEM.md section 3). */}
        <Link
          href="/branch"
          className="inline-flex h-8.5 flex-none items-center gap-1.5 rounded-pill px-3.5 text-[12.5px] font-semibold text-white shadow-panel transition-opacity hover:opacity-90"
          style={{ background: "var(--yc-gradient-action)" }}
        >
          <PlusIcon />
          Yeni başvuru
        </Link>
      </div>
    </header>
  );
}
