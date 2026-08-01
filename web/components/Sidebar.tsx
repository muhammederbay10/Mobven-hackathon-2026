/**
 * The grouped, persistent navigation rail — DESIGN_SYSTEM.md section 7.
 *
 * Three responsive states, driven by the `nav:` breakpoint (1100px, defined in
 * app/globals.css because Tailwind's built-in `lg` at 1024px does not match
 * the documented threshold) and the ordinary `md:` breakpoint (768px):
 *
 * - `>= 1100px` — full-width column with labels (--yc-sidebar-width, widened
 *   from the documented 216px per direct feedback), rendered in normal flow.
 * - `768–1099px` — the same column, compacted to an icon rail; labels move to
 *   `aria-label`/`title` instead of visible text.
 * - `< 768px` — no persistent column at all; this component instead renders
 *   as a modal drawer, shown only while `open` is true.
 *
 * The active item comes from `usePathname()` alone. Per section 7: "The
 * sidebar does not create business state or guess the active application" —
 * `activeMersis` is an optional prop for a future task to supply once a route
 * actually knows one; until then the Yetki Kaydı item falls back to the
 * `/authority` placeholder rather than guessing a MERSİS.
 *
 * Cascade note: the generated stylesheet places the custom `nav:` breakpoint's
 * media block before the built-in `md:`/`lg:` blocks rather than in ascending
 * width order, so a `nav:` utility only reliably overrides an *unwrapped* base
 * utility (which Tailwind always emits before every media block) — never a
 * same-property `md:`/`lg:` utility on the same element, since which of two
 * media-wrapped rules wins would then depend on that block order. Every
 * `nav:` use below follows the safe pattern (bare base + one `nav:` override);
 * keep it that way rather than adding a competing `md:`/`lg:` on the same
 * property.
 */

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import {
  CloseIcon,
  DashboardIcon,
  DocumentCheckIcon,
  LandmarkIcon,
  PanelLeftIcon,
  ShieldCheckIcon,
  SmartphoneIcon,
} from "./Icon";

type NavItem = {
  label: string;
  href: string;
  icon: (props: { className?: string }) => React.ReactElement;
  /** Used to match both `/authority` and `/authority/[mersis]` as one item. */
  match: (pathname: string) => boolean;
};

type NavGroup = {
  label: string;
  items: NavItem[];
};

function buildNavGroups(activeMersis: string | null | undefined): NavGroup[] {
  return [
    {
      label: "İş Akışı",
      items: [
        {
          label: "Kontrol Paneli",
          href: "/",
          icon: DashboardIcon,
          match: (pathname) => pathname === "/",
        },
        {
          label: "Şube İnceleme",
          href: "/branch",
          icon: DocumentCheckIcon,
          match: (pathname) => pathname.startsWith("/branch"),
        },
      ],
    },
    {
      label: "Yetki ve İşlem",
      items: [
        {
          label: "Mobil İşlemler",
          href: "/mobile",
          icon: SmartphoneIcon,
          match: (pathname) => pathname.startsWith("/mobile"),
        },
        {
          label: "Yetki Kaydı",
          href: activeMersis ? `/authority/${activeMersis}` : "/authority",
          icon: ShieldCheckIcon,
          match: (pathname) => pathname.startsWith("/authority"),
        },
      ],
    },
    {
      label: "Simülasyon",
      items: [
        {
          label: "Ticaret Sicili",
          href: "/registry",
          icon: LandmarkIcon,
          match: (pathname) => pathname.startsWith("/registry"),
        },
      ],
    },
  ];
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';

function BrandMark() {
  return (
    <span
      className="grid size-7 flex-none place-items-center rounded-control text-[13px] font-bold text-white"
      style={{ background: "var(--yc-gradient-action)" }}
      aria-hidden
    >
      Y
    </span>
  );
}

function NavLinks({
  groups,
  pathname,
  compact,
  onNavigate,
}: {
  groups: NavGroup[];
  pathname: string;
  compact: boolean;
  onNavigate?: () => void;
}) {
  return (
    <nav aria-label="Ana gezinme" className="flex flex-1 flex-col gap-5 overflow-y-auto px-3.5 py-4">
      {groups.map((group) => (
        <div key={group.label}>
          {!compact ? (
            <div className="mb-1.5 px-2.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
              {group.label}
            </div>
          ) : null}
          <ul className="flex flex-col gap-0.5">
            {group.items.map((item) => {
              const active = item.match(pathname);
              const Icon = item.icon;
              return (
                <li key={item.label}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    aria-label={item.label}
                    title={compact ? item.label : undefined}
                    className={[
                      "flex h-9 items-center gap-2.5 rounded-[11px] px-2.5 text-[13px] transition-colors duration-150",
                      compact ? "justify-center" : "",
                      active
                        ? "border border-border bg-surface font-bold text-ink shadow-panel"
                        : "border border-transparent text-ink-secondary hover:bg-surface-hover",
                    ].join(" ")}
                  >
                    <Icon className="flex-none" />
                    {!compact ? <span className="truncate">{item.label}</span> : null}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export function Sidebar({
  open,
  onClose,
  collapsed,
  onToggleCollapsed,
  activeMersis,
}: {
  /** Mobile drawer visibility. Ignored at `md:` and above, where the rail/full
   *  column render unconditionally in normal flow. */
  open: boolean;
  onClose: () => void;
  /** Manual override at `md:` and above: forces the icon-only rail even at the
   *  `nav:` breakpoint where it would otherwise expand to full labels. Icons
   *  stay real links and remain clickable either way — collapsing only hides
   *  the text, never the navigation itself. Has no effect on the mobile
   *  drawer, which always shows full labels once explicitly opened. */
  collapsed: boolean;
  onToggleCollapsed: () => void;
  activeMersis?: string | null;
}) {
  const pathname = usePathname();
  const groups = buildNavGroups(activeMersis);
  const drawerRef = useRef<HTMLDivElement>(null);

  // Focus trap + Escape-to-close for the mobile drawer only (DESIGN_SYSTEM.md
  // section 7: "Keyboard focus is trapped inside the open mobile drawer").
  useEffect(() => {
    if (!open) return;
    const drawer = drawerRef.current;
    if (!drawer) return;

    const focusables = () =>
      Array.from(drawer.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));

    focusables()[0]?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusables();
      const first = items[0];
      const last = items[items.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  // `collapsed` is a manual override that forces the rail regardless of width;
  // when it is false the ordinary `nav:` breakpoint (see the cascade note
  // above) decides. Each pair below is chosen with a plain ternary rather than
  // composed with the CSS variant, since "expand at nav: unless collapsed" is
  // JS state ANDed with a media query, which Tailwind classes alone can't express.
  const railWidthClass = collapsed
    ? "w-(--yc-sidebar-rail-width)"
    : "w-(--yc-sidebar-rail-width) nav:w-(--yc-sidebar-width)";
  const wordmarkClass = collapsed
    ? "hidden"
    : "hidden truncate text-[14px] font-semibold tracking-[-0.01em] text-ink nav:inline";
  const railLinksClass = collapsed ? "flex flex-1 flex-col" : "nav:hidden flex flex-1 flex-col";
  const fullLinksClass = collapsed ? "hidden" : "hidden flex-1 flex-col nav:flex";

  return (
    <>
      {/* Desktop / tablet: persistent column. Hidden below md (768px); the
          drawer below takes over entirely at that width. `overflow-hidden`
          keeps the full-width labels from spilling out and wrapping visibly
          while the column is mid-animation on a manual collapse/expand;
          `prefers-reduced-motion` collapses the transition duration globally
          (see app/globals.css). */}
      <div
        className={`hidden flex-none flex-col overflow-hidden border-r border-border bg-shell transition-[width] duration-200 ease-in-out md:flex ${railWidthClass}`}
      >
        {/* Logo at the far left, collapse toggle at the far right. Below
            nav: (1100px) the toggle is not rendered — the rail is already
            forced by width alone there — so this row falls back to centering
            the logo alone, matching the rail's other icon-only rows. */}
        <div className="flex h-(--yc-topbar-height) flex-none items-center justify-center gap-2 border-b border-border px-3.5 nav:justify-between">
          <span className="flex min-w-0 items-center gap-2">
            <BrandMark />
            <span className={wordmarkClass}>YetkiCheck</span>
          </span>
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-expanded={!collapsed}
            aria-label={collapsed ? "Menüyü genişlet" : "Menüyü daralt"}
            title={collapsed ? "Menüyü genişlet" : "Menüyü daralt"}
            className="hidden size-7 flex-none place-items-center rounded-control text-ink-secondary hover:bg-surface-hover nav:grid"
          >
            <PanelLeftIcon />
          </button>
        </div>
        {/* Two renders (rail vs full) rather than one that reflows: switching
            between them should show/hide group labels and item text cleanly,
            not fade/wrap awkwardly mid-transition. */}
        <div className={railLinksClass}>
          <NavLinks groups={groups} pathname={pathname} compact />
        </div>
        <div className={fullLinksClass}>
          <NavLinks groups={groups} pathname={pathname} compact={false} />
        </div>
      </div>

      {/* Mobile: modal drawer. */}
      {open ? (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            aria-label="Menüyü kapat"
            onClick={onClose}
            className="absolute inset-0 bg-ink/30"
          />
          <div
            ref={drawerRef}
            role="dialog"
            aria-modal="true"
            aria-label="Ana gezinme"
            className="relative flex h-full w-[min(84vw,300px)] flex-col bg-shell shadow-shell"
          >
            <div className="flex h-(--yc-topbar-height) flex-none items-center gap-2 border-b border-border px-3.5">
              <BrandMark />
              <span className="flex-1 truncate text-[14px] font-semibold tracking-[-0.01em] text-ink">
                YetkiCheck
              </span>
              <button
                type="button"
                onClick={onClose}
                aria-label="Menüyü kapat"
                className="grid size-8 flex-none place-items-center rounded-control border border-border-strong text-ink-secondary hover:bg-surface-hover"
              >
                <CloseIcon />
              </button>
            </div>
            <NavLinks groups={groups} pathname={pathname} compact={false} onNavigate={onClose} />
          </div>
        </div>
      ) : null}
    </>
  );
}
