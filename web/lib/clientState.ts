/**
 * Last-visited navigation context, kept in `sessionStorage`.
 *
 * Convenience only: the application ID and MERSİS that *drive* a screen always
 * live in the URL (guide section 5 — refresh must restore from URL + API).
 * This module merely remembers where the operator last was so bare `/mobile`
 * or `/authority` navigation can offer the most recent context, and so a demo
 * reset can clear it (guide section 16: after reset, old database IDs no
 * longer exist and stale navigation must be dropped).
 */

const APPLICATION_KEY = "yetkicheck.lastApplicationId";
const MERSIS_KEY = "yetkicheck.lastMersis";

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

export function rememberApplicationId(id: number): void {
  storage()?.setItem(APPLICATION_KEY, String(id));
}

export function lastApplicationId(): number | null {
  const raw = storage()?.getItem(APPLICATION_KEY);
  const parsed = raw ? Number(raw) : NaN;
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export function rememberMersis(mersis: string): void {
  storage()?.setItem(MERSIS_KEY, mersis);
}

export function lastMersis(): string | null {
  return storage()?.getItem(MERSIS_KEY) ?? null;
}

/** Called after a successful demo reset — the IDs no longer exist. */
export function clearNavigationState(): void {
  storage()?.removeItem(APPLICATION_KEY);
  storage()?.removeItem(MERSIS_KEY);
}
