import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";

import { AppShell } from "@/components/Layout";

import "./globals.css";

/**
 * Self-hosted Inter (DESIGN_SYSTEM.md section 4) — two files, not one.
 *
 * fontsource's plain "latin" subset covers ASCII, Latin-1 Supplement and the
 * dotless ı (U+0131), but not ğ, Ş, or İ — those live in Latin Extended-A,
 * covered only by the "latin-ext" subset. Loading both as ordinary next/font
 * fonts and chaining their generated CSS variables in `--font-sans`
 * (app/globals.css) lets the browser's normal per-character font fallback
 * fill in the missing Turkish glyphs, the same outcome unicode-range
 * subsetting gives — without depending on next/font/local's single
 * `declarations` array being applicable per source file.
 *
 * Files are committed at app/fonts/ (SIL OFL 1.1, see app/fonts/INTER-LICENSE.txt),
 * extracted once from @fontsource-variable/inter — no runtime font CDN.
 */
const interLatin = localFont({
  src: "./fonts/inter-latin-variable.woff2",
  variable: "--font-inter-latin",
  weight: "100 900",
  style: "normal",
  display: "swap",
  preload: true,
});

const interLatinExt = localFont({
  src: "./fonts/inter-latin-ext-variable.woff2",
  variable: "--font-inter-latin-ext",
  weight: "100 900",
  style: "normal",
  display: "swap",
  // Only a handful of Turkish letters ever need this file; preloading it
  // unconditionally on every route would cost more than it saves.
  preload: false,
});

export const metadata: Metadata = {
  title: "starq.dev",
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
    <html lang="tr" className={`${interLatin.variable} ${interLatinExt.variable}`}>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
