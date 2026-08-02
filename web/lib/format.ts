/**
 * Display formatting — the only place money is converted out of minor units.
 *
 * Plan GAP-12 and section 10.1: `amount_minor` is integer kuruş everywhere in
 * code, APIs and the database. It is formatted **only at the display edge**,
 * via `Intl.NumberFormat('tr-TR', {style:'currency', currency:'TRY'})`.
 * Components must never divide or format money ad hoc — that is how a rounding
 * bug reaches a limit comparison.
 *
 * Nothing here is a business rule. These functions describe values; they never
 * decide anything.
 */

import type {
  ApplicationStatus,
  AuthorityMode,
  CheckStatus,
  OnboardingVerdict,
  TransactionSubject,
  TransactionVerdict,
} from "./types";

const TRY_FORMAT = new Intl.NumberFormat("tr-TR", {
  style: "currency",
  currency: "TRY",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const DATE_FORMAT = new Intl.DateTimeFormat("tr-TR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const TIME_FORMAT = new Intl.DateTimeFormat("tr-TR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** Integer kuruş -> `1.200.000,50 ₺`. The one sanctioned division by 100. */
export function formatAmountMinor(amountMinor: number | null | undefined): string {
  if (amountMinor === null || amountMinor === undefined) return "—";
  return TRY_FORMAT.format(amountMinor / 100);
}

/**
 * An inclusive authority-rule range, e.g. `500.000,00 ₺ üzeri`.
 * `null` means unbounded on that side (plan section 5.2).
 */
export function formatAmountRange(
  minAmountMinor: number | null,
  maxAmountMinor: number | null,
): string {
  if (minAmountMinor === null && maxAmountMinor === null) return "Tutar sınırı yok";
  if (minAmountMinor === null) return `${formatAmountMinor(maxAmountMinor)} ve altı`;
  if (maxAmountMinor === null) return `${formatAmountMinor(minAmountMinor)} ve üzeri`;
  return `${formatAmountMinor(minAmountMinor)} – ${formatAmountMinor(maxAmountMinor)}`;
}

/** ISO calendar date (`2027-03-15`) -> `15.03.2027`. */
export function formatDate(isoDate: string | null | undefined): string {
  if (!isoDate) return "—";
  const parsed = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return isoDate;
  return DATE_FORMAT.format(parsed);
}

/** ISO UTC instant (`2026-08-01T10:00:00Z`) -> `01.08.2026 13:00` in local time. */
export function formatInstant(isoInstant: string | null | undefined): string {
  if (!isoInstant) return "—";
  const parsed = new Date(isoInstant);
  if (Number.isNaN(parsed.getTime())) return isoInstant;
  return TIME_FORMAT.format(parsed);
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Turkish-formatted TL input -> integer kuruş, or `null` when unparseable.
 * Accepts `1.200.000`, `1.200.000,50`, `250000` and optional `₺`/`TL` noise.
 * String arithmetic only — no float division that could shave a kuruş off a
 * limit comparison (the comparison itself always happens on the backend).
 */
export function parseAmountToMinor(input: string): number | null {
  const cleaned = input.replace(/\s|₺/g, "").replace(/TL$/i, "");
  if (!cleaned) return null;
  const normalized = cleaned.replace(/\./g, "").replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) return null;
  const [lira = "0", kurus = ""] = normalized.split(".");
  const minor = Number(lira) * 100 + Number(`${kurus}00`.slice(0, 2));
  return Number.isSafeInteger(minor) ? minor : null;
}

/* -------------------------------------------------------------------------- */
/* Turkish labels                                                             */
/* -------------------------------------------------------------------------- */

/**
 * Verdict labels for display. Choosing the *label* is presentation; choosing the
 * *verdict* is the API's job and never happens here (plan section 10.1).
 */
export const ONBOARDING_VERDICT_LABEL: Record<OnboardingVerdict, string> = {
  READY: "Onaya hazır",
  CO_SIGNER_REQUIRED: "İkinci imza gerekli",
  MISMATCH: "Bilgiler uyuşmuyor",
  REGISTRY_CONFLICT: "Sicil kaydıyla çelişiyor",
};

/**
 * Which of the three check colors represents each verdict, for a legend/badge
 * — e.g. the control panel's case cards. This mirrors plan section 6.1's own
 * precedence (CO_SIGNER_REQUIRED comes from an amber check; MISMATCH and
 * REGISTRY_CONFLICT both come from a red one); it does not compute a verdict,
 * only chooses a color for one the API already returned.
 */
export const ONBOARDING_VERDICT_STATUS: Record<OnboardingVerdict, CheckStatus> = {
  READY: "green",
  CO_SIGNER_REQUIRED: "amber",
  MISMATCH: "red",
  REGISTRY_CONFLICT: "red",
};

export const TRANSACTION_VERDICT_LABEL: Record<TransactionVerdict, string> = {
  ALLOWED: "İşlem onaylandı",
  PENDING_COSIGN: "İkinci imza bekleniyor",
  DENIED: "İşlem reddedildi",
};

/**
 * Status is communicated by icon **and** text, never by color alone
 * (plan section 10.1). This is the shared symbol vocabulary.
 */
export const CHECK_STATUS_SYMBOL: Record<CheckStatus, string> = {
  green: "✓",
  amber: "!",
  red: "×",
};

export const CHECK_STATUS_LABEL: Record<CheckStatus, string> = {
  green: "Uygun",
  amber: "Dikkat",
  red: "Engel",
};

/** Backend application lifecycle states, for the branch stepper and badges. */
export const APPLICATION_STATUS_LABEL: Record<ApplicationStatus, string> = {
  DRAFT: "Taslak — kimlik doğrulanmadı",
  IDENTITY_VERIFIED: "Kimlik doğrulandı",
  DOCUMENT_SCANNED: "Belge tarandı",
  ANALYZING: "Analiz ediliyor",
  ANALYZED: "Analiz tamamlandı",
  APPROVED: "Onaylandı",
  DOC_REQUESTED: "Yeni belge istendi",
  ESCALATED: "Uyum birimine iletildi",
  ANALYSIS_FAILED: "Analiz başarısız",
};

export const TRANSACTION_SUBJECT_LABEL: Record<TransactionSubject, string> = {
  GENERAL: "Genel işlem",
  CREDIT: "Kredi kullanımı",
  REAL_ESTATE: "Gayrimenkul",
};

export const AUTHORITY_MODE_LABEL: Record<AuthorityMode, string> = {
  SOLE: "Münferit",
  JOINT: "Müşterek",
  LIMITED: "Sınırlı",
  UNKNOWN: "Belirsiz",
};

const AUDIT_ACTION_LABEL: Record<string, string> = {
  APPLICATION_CREATED: "Başvuru oluşturuldu",
  IDENTITY_ATTESTED: "Kimlik doğrulandı",
  DOCUMENT_UPLOADED: "Belge yüklendi",
  ANALYSIS_STARTED: "Belge incelemesi başladı",
  ANALYSIS_COMPLETED: "Belge incelemesi tamamlandı",
  ANALYSIS_FAILED: "Belge incelemesi tamamlanamadı",
  EXTRACTION_CORRECTED: "Belge bilgisi düzeltildi",
  APPLICATION_DECIDED: "Başvuru kararı kaydedildi",
  APPROVAL_OVERRIDE: "İstisnai onay verildi",
  AUTHORITY_CREATED: "Yetki kaydı oluşturuldu",
  AUTHORITY_SUSPENDED: "Yetki kaydı askıya alındı",
  REGISTRY_REPRESENTATIVE_UPDATED: "Temsilci sicil durumu güncellendi",
  TRANSACTION_AUTHORIZED: "İşlem yetkisi kontrol edildi",
  TRANSACTION_COSIGNED: "İkinci imza tamamlandı",
};

export function formatAuditAction(action: string): string {
  return AUDIT_ACTION_LABEL[action] ?? "Kayıt güncellendi";
}

export function formatActor(actor: string): string {
  if (actor.startsWith("branch_user:")) return "Şube görevlisi";
  if (actor.startsWith("system")) return "Sistem";
  if (actor.startsWith("mobile_user:")) return "Mobil kullanıcı";
  return "Yetkili kullanıcı";
}

/**
 * Lowercase AI rule scopes -> Turkish display labels (guide section 13:
 * "rules with lowercase scope rendered as Turkish labels"). Unknown scopes
 * fall back to the raw contract value rather than guessing a meaning.
 */
const RULE_SCOPE_LABEL: Record<string, string> = {
  general: "Genel işlemler",
  credit: "Kredi işlemleri",
  real_estate: "Gayrimenkul işlemleri",
};

export function formatRuleScope(scope: string): string {
  return RULE_SCOPE_LABEL[scope] ?? scope;
}
