import type { Metadata, Viewport } from "next";

import { SiteHeader } from "@/components/SiteHeader";

import "./globals.css";

export const metadata: Metadata = {
  title: "YetkiCheck",
  description:
    "İmza sirkülerini bir kez şubede doğrula, sonraki her işlemde kayıtlı yetkiyi denetle.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // Turkish is the user-facing default (plan section 10.1), so `lang` is `tr`:
  // it drives hyphenation, spell-check and screen-reader pronunciation.
  return (
    <html lang="tr">
      <body>
        <div className="mx-auto max-w-[1240px] px-5 pb-14">
          <SiteHeader />
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
