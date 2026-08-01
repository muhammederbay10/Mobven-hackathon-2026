"use client";

import { useState } from "react";

import { ApiError, createApplication, fieldErrors } from "@/lib/api";
import type { ApplicationView } from "@/lib/types";

import { Button, Checkbox, Field, Input } from "@/components/UI";

/**
 * Step 1 — application intake and branch identity attestation.
 *
 * Uses `CreateApplicationRequest` exactly (guide section 10). The backend has
 * no later attestation endpoint, so `identity_verified_at_branch` must be true
 * before submission; the checkbox gates the submit button rather than being
 * silently defaulted. The TCKN stays masked everywhere.
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

const FIELDS: Array<{
  name: keyof FormValues;
  label: string;
  hint?: string;
  placeholder?: string;
}> = [
  { name: "company_name", label: "Şirket unvanı", placeholder: "ABC Teknoloji Ltd. Şti." },
  { name: "tax_number", label: "Vergi numarası", hint: "10 hane", placeholder: "1234567890" },
  { name: "mersis", label: "MERSİS numarası", hint: "16 hane", placeholder: "0123456789000017" },
  { name: "applicant_name", label: "Başvuran yetkili", placeholder: "Ali Yılmaz" },
  {
    name: "applicant_tckn_masked",
    label: "TCKN (maskeli)",
    hint: "Örn. 123******01 — açık TCKN hiçbir yerde tutulmaz",
    placeholder: "123******01",
  },
  { name: "branch_code", label: "Şube kodu" },
];

export function CreateStep({ onCreated }: { onCreated: (view: ApplicationView) => void }) {
  const [values, setValues] = useState<FormValues>(INITIAL);
  const [identityVerified, setIdentityVerified] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const serverFieldErrors = fieldErrors(error);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!identityVerified || pending) return;
    setPending(true);
    setError(null);
    try {
      const view = await createApplication({ ...values, identity_verified_at_branch: true });
      onCreated(view);
    } catch (cause) {
      setError(cause);
      setPending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl p-4" noValidate>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {FIELDS.map((field) => (
          <Field
            key={field.name}
            htmlFor={`create-${field.name}`}
            label={field.label}
            hint={field.hint}
            error={serverFieldErrors[field.name]}
          >
            <Input
              id={`create-${field.name}`}
              name={field.name}
              value={values[field.name]}
              placeholder={field.placeholder}
              onChange={(event) =>
                setValues((current) => ({ ...current, [field.name]: event.target.value }))
              }
            />
          </Field>
        ))}
      </div>

      <label className="mt-4 flex items-start gap-2.5 text-[13px] text-ink">
        <Checkbox
          checked={identityVerified}
          onChange={(event) => setIdentityVerified(event.target.checked)}
        />
        <span>
          Başvuranın kimliğini şubede aslıyla doğruladım.
          <span className="block text-[11.5px] text-ink-muted">
            Kimlik doğrulaması olmadan başvuru gönderilemez; sonradan tamamlanamaz.
          </span>
        </span>
      </label>

      {error instanceof ApiError && Object.keys(serverFieldErrors).length === 0 ? (
        <div className="mt-4 rounded-panel border border-danger/30 bg-danger-soft px-3.5 py-2.5 text-[12.5px] text-danger" role="alert">
          {error.message}
          {error.correlationId ? (
            <span className="mt-1 block font-mono text-[11px] text-ink-muted">
              İşlem no: {error.correlationId}
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="mt-5">
        <Button type="submit" variant="primary" disabled={!identityVerified || pending}>
          {pending ? "Gönderiliyor…" : "Başvuruyu oluştur"}
        </Button>
      </div>
    </form>
  );
}
