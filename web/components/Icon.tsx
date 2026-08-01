/**
 * A minimal outline icon set matching DESIGN_SYSTEM.md section 10: "one
 * outline icon family consistently, preferably Lucide-style icons at 16px
 * with 1.5px stroke." Hand-drawn rather than imported: the plan (section
 * "Constraints") only permits a new dependency the repository already has or
 * the plan explicitly allows, and an icon set is easy to reproduce faithfully
 * at this size without adding one.
 *
 * Every icon shares the same viewBox, stroke width and cap/join style so
 * nothing drifts into a second visual language.
 */

import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function base(props: IconProps) {
  return {
    width: 16,
    height: 16,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    ...props,
  };
}

/** Kontrol Paneli — grid/dashboard glyph. */
export function DashboardIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
    </svg>
  );
}

/** Şube İnceleme — document with a check mark. */
export function DocumentCheckIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M7 3.5h7l4 4V19a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 19V5A1.5 1.5 0 0 1 7 3.5Z" />
      <path d="M14 3.5V8h4.5" />
      <path d="M9 13.5l2 2 4-4.5" />
    </svg>
  );
}

/** Mobil İşlemler — phone glyph. */
export function SmartphoneIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="6.5" y="2.5" width="11" height="19" rx="2" />
      <path d="M10.5 18.25h3" />
    </svg>
  );
}

/** Yetki Kaydı — shield with a check mark. */
export function ShieldCheckIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 3l7 3v5.2c0 4.6-3 8.4-7 9.8-4-1.4-7-5.2-7-9.8V6l7-3Z" />
      <path d="M9 12l2 2 4-4.5" />
    </svg>
  );
}

/** Ticaret Sicili — a small building/registry glyph. */
export function LandmarkIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M3.5 9.5 12 4l8.5 5.5" />
      <path d="M5 10v8.5M9.5 10v8.5M14.5 10v8.5M19 10v8.5" />
      <path d="M3 20.5h18" />
    </svg>
  );
}

/** Mobile drawer trigger. */
export function MenuIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 6.5h16M4 12h16M4 17.5h16" />
    </svg>
  );
}

/** Mobile drawer close. */
export function CloseIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M5.5 5.5l13 13M18.5 5.5l-13 13" />
    </svg>
  );
}

/** Breadcrumb separator. */
export function ChevronRightIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M9 5.5l6.5 6.5-6.5 6.5" />
    </svg>
  );
}

/** Sidebar collapse/expand toggle — a bordered panel with a left divider. */
export function PanelLeftIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 3v18" />
    </svg>
  );
}

/** Breadcrumb "Ana Sayfa" glyph. */
export function HomeIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 10.5 12 4l8 6.5" />
      <path d="M5.5 9.5V19a1.5 1.5 0 0 0 1.5 1.5h10a1.5 1.5 0 0 0 1.5-1.5V9.5" />
      <path d="M10 20.5v-5.5h4v5.5" />
    </svg>
  );
}

/** Top-bar search field glyph. */
export function SearchIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M15.8 15.8 20.5 20.5" />
    </svg>
  );
}

/** Top-bar notification bell. */
export function BellIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 3.5a5.5 5.5 0 0 0-5.5 5.5c0 4.5-1.5 6-2 6.5h15c-.5-.5-2-2-2-6.5A5.5 5.5 0 0 0 12 3.5Z" />
      <path d="M10 18.5a2 2 0 0 0 4 0" />
    </svg>
  );
}

/** Gradient primary-action plus. */
export function PlusIcon(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}
