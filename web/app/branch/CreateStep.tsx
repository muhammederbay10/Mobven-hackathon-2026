"use client";

import { useState } from "react";

import { ApiError, createApplication, fieldErrors } from "@/lib/api";
import type { ApplicationView } from "@/lib/types";

import { ChevronRightIcon } from "@/components/Icon";
import { Button, Checkbox, Field, Input } from "@/components/UI";

/**
 * Step 1 — application intake and branch identity attestation.
 *
 * Uses `CreateApplicationRequest` exactly (guide section 10). The backend has
 * no later attestation endpoint, so `identity_verified_at_branch` must be true
 * before submission; the attestation card gates the submit button rather than
 * being silently defaulted. The TCKN stays masked everywhere.
 *
 * The outer branch stepper treats intake as one step. Inside it, this component
 * presents a two-stage onboarding flow so company data and applicant/branch
 * attestation are completed separately before document upload.
 */

type FormValues = {
  company_name: string;
  tax_number: string;
  mersis: string;
  applicant_name: string;
  applicant_tckn_masked: string;
  branch_code: string;
};

const INITIAL: FormValues = {
  company_name: "",
  tax_number: "",
  mersis: "",
  applicant_name: "",
  applicant_tckn_masked: "",
  branch_code: "kozyatagi01",
};

type FieldConfig = {
  name: keyof FormValues;
  label: string;
  hint?: string;
  placeholder?: string;
  numeric?: boolean;
  maxLength?: number;
  autoComplete?: string;
};

const COMPANY_FIELDS: FieldConfig[] = [
  {
    name: "company_name",
    label: "Şirket unvanı",
    placeholder: "ABC Teknoloji Ltd. Şti.",
    hint: "Sirkülerdeki unvanla birebir aynı yazılmalı",
    autoComplete: "organization",
  },
  {
    name: "tax_number",
    label: "Vergi numarası",
    hint: "10 hane",
    placeholder: "1234567890",
    numeric: true,
    maxLength: 10,
  },
  {
    name: "mersis",
    label: "MERSİS numarası",
    hint: "16 hane",
    placeholder: "0123456789000017",
    numeric: true,
    maxLength: 16,
  },
];

const APPLICANT_FIELDS: FieldConfig[] = [
  {
    name: "applicant_name",
    label: "Başvuran yetkili",
    placeholder: "Ali Yılmaz",
    autoComplete: "name",
  },
  {
    name: "applicant_tckn_masked",
    label: "TCKN (maskeli)",
    hint: "Açık TCKN hiçbir yerde tutulmaz",
    placeholder: "123******01",
    maxLength: 11,
  },
  { name: "branch_code", label: "Şube kodu", hint: "İşlemi yapan birim" },
];

export function CreateStep({ onCreated }: { onCreated: (view: ApplicationView) => void }) {
  const [intakeStep, setIntakeStep] = useState<1 | 2>(1);
  const [values, setValues] = useState<FormValues>(INITIAL);
  const [identityVerified, setIdentityVerified] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [localErrors, setLocalErrors] = useState<Partial<Record<keyof FormValues, string>>>({});

  const serverFieldErrors = fieldErrors(error);

  function validateCompanyStep() {
    const errors: Partial<Record<keyof FormValues, string>> = {};
    if (!values.company_name.trim()) errors.company_name = "Şirket unvanını girin.";
    if (!/^\d{10}$/.test(values.tax_number)) {
      errors.tax_number = "Vergi numarası 10 rakamdan oluşmalıdır.";
    }
    if (!/^\d{16}$/.test(values.mersis)) {
      errors.mersis = "MERSİS numarası 16 rakamdan oluşmalıdır.";
    }
    return errors;
  }

  function validateApplicantStep() {
    const errors: Partial<Record<keyof FormValues, string>> = {};
    if (!values.applicant_name.trim()) errors.applicant_name = "Başvuranın adını girin.";
    if (!/^\d{3}\*{6}\d{2}$/.test(values.applicant_tckn_masked)) {
      errors.applicant_tckn_masked = "TCKN, 123******01 biçiminde maskelenmelidir.";
    }
    if (!values.branch_code.trim()) errors.branch_code = "Şube kodunu girin.";
    return errors;
  }

  function goToApplicantStep() {
    const errors = validateCompanyStep();
    setLocalErrors(errors);
    if (Object.keys(errors).length > 0) return;
    setError(null);
    setIntakeStep(2);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (intakeStep === 1) {
      goToApplicantStep();
      return;
    }
    const errors = validateApplicantStep();
    setLocalErrors(errors);
    if (Object.keys(errors).length > 0) return;
    if (!identityVerified || pending) return;
    setPending(true);
    setError(null);
    try {
      const view = await createApplication({ ...values, identity_verified_at_branch: true });
      onCreated(view);
    } catch (cause) {
      setError(cause);
      const errors = fieldErrors(cause);
      if (COMPANY_FIELDS.some((field) => errors[field.name])) setIntakeStep(1);
      setPending(false);
    }
  }

  function updateField(name: keyof FormValues, value: string) {
    setValues((current) => ({ ...current, [name]: value }));
    setLocalErrors((current) => {
      if (!current[name]) return current;
      const next = { ...current };
      delete next[name];
      return next;
    });
    if (error) setError(null);
  }

  function renderField(field: FieldConfig) {
    return (
      <div key={field.name}>
        <Field
          htmlFor={`create-${field.name}`}
          label={field.label}
          hint={field.hint}
          error={localErrors[field.name] ?? serverFieldErrors[field.name]}
        >
          <Input
            id={`create-${field.name}`}
            name={field.name}
            value={values[field.name]}
            placeholder={field.placeholder}
            inputMode={field.numeric ? "numeric" : undefined}
            maxLength={field.maxLength}
            autoComplete={field.autoComplete ?? "off"}
            className={field.numeric || field.name === "applicant_tckn_masked" ? "font-mono" : ""}
            onChange={(event) => updateField(field.name, event.target.value)}
          />
        </Field>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 sm:p-6" noValidate>
      <div className="mx-auto max-w-2xl">
        <div className="mb-5 rounded-card border border-border bg-surface-subtle p-1.5">
          <ol className="grid grid-cols-2 gap-1.5" aria-label="Başvuru bilgileri adımları">
            <IntakeStepIndicator
              number={1}
              label="Şirket bilgileri"
              active={intakeStep === 1}
              complete={intakeStep === 2}
            />
            <IntakeStepIndicator
              number={2}
              label="Başvuran ve şube"
              active={intakeStep === 2}
              complete={false}
            />
          </ol>
        </div>

        <div key={intakeStep} className="animate-[intake-in_220ms_ease-out]">
          {intakeStep === 1 ? (
            <FormSection
              eyebrow="Başvuru bilgileri · 1/2"
              title="Şirket bilgileri"
              description="Başvuruya konu tüzel kişiliğin resmi bilgilerini girin."
            >
              {COMPANY_FIELDS.map(renderField)}
            </FormSection>
          ) : (
            <FormSection
              eyebrow="Başvuru bilgileri · 2/2"
              title="Başvuran ve şube"
              description="Şubede kimliği doğrulanan başvuranı ve işlemi yapan birimi girin."
            >
              {APPLICANT_FIELDS.map(renderField)}

              <label
                className={`flex cursor-pointer items-start gap-3 rounded-card border p-3.5 transition-colors ${
                  identityVerified
                    ? "border-success/40 bg-success-soft"
                    : "border-border-strong bg-surface-subtle hover:border-cyan/50 hover:bg-cyan-soft"
                }`}
              >
                <Checkbox
                  checked={identityVerified}
                  onChange={(event) => setIdentityVerified(event.target.checked)}
                />
                <span className="text-[13px] leading-5 text-ink">
                  <b className="font-semibold">
                    Başvuranın kimliğini şubede aslıyla doğruladım.
                  </b>
                  <span className="mt-0.5 block text-[11.5px] leading-4 text-ink-muted">
                    Kimlik doğrulaması olmadan başvuru gönderilemez; sonradan tamamlanamaz.
                  </span>
                </span>
              </label>
            </FormSection>
          )}
        </div>

        {error instanceof ApiError && Object.keys(serverFieldErrors).length === 0 ? (
          <div
            className="mt-4 rounded-card border border-danger/30 bg-danger-soft px-3.5 py-2.5 text-[12.5px] text-danger"
            role="alert"
          >
            {error.message}
            {error.correlationId ? (
              <span className="mt-1 block font-mono text-[11px] text-ink-muted">
                İşlem no: {error.correlationId}
              </span>
            ) : null}
          </div>
        ) : null}

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
          {intakeStep === 2 ? (
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setLocalErrors({});
                setIntakeStep(1);
              }}
              disabled={pending}
            >
              <span aria-hidden>←</span>
              Geri
            </Button>
          ) : (
            <span className="text-[11.5px] text-ink-muted">Sonraki: Başvuran ve şube</span>
          )}

          {intakeStep === 1 ? (
            <Button type="button" variant="primary" onClick={goToApplicantStep}>
              Devam et
              <ChevronRightIcon />
            </Button>
          ) : (
            <div className="flex flex-wrap items-center justify-end gap-3">
              <span className="text-[11.5px] text-ink-muted">Sonraki: Belge yükleme</span>
              <Button type="submit" variant="primary" disabled={!identityVerified || pending}>
                {pending ? "Gönderiliyor…" : "Başvuruyu oluştur"}
                {!pending ? <ChevronRightIcon /> : null}
              </Button>
            </div>
          )}
        </div>
      </div>
    </form>
  );
}

function IntakeStepIndicator({
  number,
  label,
  active,
  complete,
}: {
  number: number;
  label: string;
  active: boolean;
  complete: boolean;
}) {
  return (
    <li
      aria-current={active ? "step" : undefined}
      className={`flex items-center gap-2 rounded-control px-3 py-2.5 text-[12.5px] transition-colors ${
        active ? "bg-surface font-semibold text-ink shadow-panel" : "text-ink-muted"
      }`}
    >
      <span
        className={`grid size-5 flex-none place-items-center rounded-full text-[10.5px] font-semibold ${
          complete
            ? "bg-success-soft text-success"
            : active
              ? "bg-cyan-soft text-info"
              : "bg-surface text-ink-muted"
        }`}
        aria-hidden
      >
        {complete ? "✓" : number}
      </span>
      <span className="truncate">{label}</span>
    </li>
  );
}

function FormSection({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-panel border border-border bg-surface p-5 shadow-panel sm:p-6">
      <div className="mb-5 min-w-0 border-b border-border pb-4">
        <p className="mb-1 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-info">
          {eyebrow}
        </p>
        <h4 className="text-[17px] font-semibold leading-6 text-ink">{title}</h4>
        {description ? (
          <p className="mt-1 text-[12.5px] leading-5 text-ink-secondary">{description}</p>
        ) : null}
      </div>
      <div className="grid grid-cols-1 gap-4">{children}</div>
    </section>
  );
}
