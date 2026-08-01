# AI + Backend Build Plan — Signature Circular Verification Platform

**Audience:** anyone on (or joining) the team, with zero prior context.
**Scope of this document:** the AI pipeline + backend. The frontend is a separate track that
builds against the API contract in §7.
**Deadline context:** hackathon demo in ~24 hours from plan approval (demo on 2 Aug 2026).

---

## 1. What we are building and why

### 1.1 The problem

An **imza sirküleri** (signature circular) is a notarized Turkish legal document that defines
**who is allowed to sign on behalf of a company, for what, and how**: which people, alone
(*münferiden*) or jointly (*müştereken*), up to which monetary limits, for which transaction
types, valid until when. It also contains each person's specimen signatures.

Banks must check this document for **every corporate transaction** — account opening, loan
agreements, payment orders. Today a bank employee reads pages of notary legalese manually
(15–25 minutes per document), re-keys the result, and repeats a shorter manual check
(~5–10 min) on every transaction. Errors mean fraud losses: an unauthorized signature on a
₺5M transfer is a catastrophic mistake. Nobody has automated this because until vision LLMs,
software could not parse clauses like *"(A) Grubu imza yetkilileri münferiden ₺500.000'e kadar…"*.

### 1.2 The product

1. **Ingestion:** upload a scanned circular → an AI agent pipeline extracts a structured
   **authority matrix** (people + rules), with every value linked to the exact clause it came
   from → a human reviews and approves it. Nothing is trusted without review.
2. **Verification (the actual money-maker):** a deterministic API that answers, in
   milliseconds, "is this payment order validly signed?" — `APPROVED / BLOCKED /
   NEEDS_SECOND_SIGNATURE`, always citing the clause. **No LLM is involved in this decision** —
   it is a rule walk over the approved matrix that an auditor can replay.

The live demo: upload the circular, show the agents working, review + approve the matrix, then
feed in a ₺750,000 payment order signed by one person → the system **BLOCKS it** citing the
joint-signature clause → add the second signer → **APPROVED**.

### 1.3 Why we believe extraction works (the spike)

We ran a graded feasibility spike (`extraction-spike/`, results in `extraction-spike/outputs/`)
on 4 documents before writing this plan:

| Test | Document | Result |
|---|---|---|
| 1 | Real 2-page Ltd company circular (2017 scan, stamps) | Identity + rules 100%; honestly flagged an unreadable field instead of guessing |
| 2 | Real 5-page circular with A/B/C groups and USD amount tiers | All 12 authority rules correct; **but** silently garbled 4 rare proper names + 1 digit (e.g. GUSEVA→CUSKYA) |
| 3 | Fictional circular, printed + photographed as a bad scan (we know ground truth) | 100%, including a clause under a notary stamp |
| 4 | Real 9-page bank circular (21 signatories, 6 authority degrees) | Full rule ladder correct. Model A dropped a co-signer referenced from an older document ("Tolga Akar"); model B caught him but missed a person-level expiry date ("12.12.2023"); **both** flattened per-person validity to "indefinite" |

Every failure class has a named mitigation in this plan, and the plan references them by these
names: **the CUSKYA case** (perception errors on rare names/digits), **the Tolga Akar case**
(references to people defined in *other* documents), **the 12.12.2023 case** (person-level
validity lost).

### 1.4 One legal fact that shapes the design

Under Turkish Commercial Code (TTK) art. 367/371 (since 2012), *limited* signature authority
(degrees, groups, monetary tiers) may only be defined in a registered **iç yönerge** (internal
directive) — which by law contains **no names**. People are assigned to groups by a separate
board resolution. So the "who" and the "what" of authority live in **different documents**, and
joining them is not an edge case — it is the legally mandated shape of the problem. Our
pipeline must therefore treat cross-document references as first-class (see
`document_references` table and the `unresolved_external` concept).

### 1.5 Glossary (Turkish terms you will see in documents and code)

| Term | Meaning |
|---|---|
| imza sirküleri | signature circular (the document we process) |
| münferiden | signing alone (sole authority) |
| müştereken | signing jointly |
| iç yönerge | internal directive defining limited-authority groups/degrees (no names in it) |
| tatbik imzaları | specimen signatures section |
| dayanak | "legal basis" — the paragraph citing the underlying board resolution / registrations |
| yevmiye no | the notary's journal number for the notarization |
| VKN / TCKN | tax ID (10 digits) / citizen ID (11 digits) — both have checksum algorithms |
| TTSG | Türkiye Ticaret Sicili Gazetesi (trade registry gazette) |
| müstenidattır | "supporting document — not valid alone" (stamped on annexes) |

---

## 2. Locked decisions (do not relitigate during the build)

1. **Storage: SQLite** via SQLAlchemy async + `aiosqlite`. High-variance data (rules) goes in
   JSON text columns validated by versioned Pydantic models. Reason: zero setup, no network
   dependency on stage. "PostgreSQL in production" is a slide line; the SQLAlchemy code is
   written so the engine URL is the only thing that changes.
2. **Verification is a backend endpoint** and is pure deterministic Python. Never an LLM.
3. **Models come from `.env`, never hardcoded.** `EXTRACTION_MODEL=gpt-5.6-luna` (primary; in
   the spike it was faster and caught the 12.12.2023 expiry), `WITNESS_MODEL=gpt-5.6-terra`
   (second opinion; it caught Tolga Akar). The witness double-call runs on **rules chunks only**.
4. **Review-first:** a document's matrix only becomes usable by `/api/verify` after a human
   approves it via the API. AI output is never trusted directly.
5. **The Validator produces annotations only.** It cannot stop, branch, or gate the pipeline.
   (Hard lesson from the team's previous project, where hardcoded validation blocking the flow
   was a constant headache.) It checks **provenance** ("does this value trace to the document?"),
   never **plausibility** ("does this value seem reasonable?") — plausibility is the human
   reviewer's job.
6. **Demo safety:** every pipeline stage's output is cached as JSON; a seed script can load the
   full result into SQLite so the entire demo works with the network unplugged. The on-stage
   document is the **fictional** `extraction-spike/samples/hard_case_scan.jpg` (known ground
   truth, no real people). The real bank circular contains real names — never on screen.

---

## 3. Architecture overview

```
 upload (PDF/JPG)
   │
   ▼
 RENDER      pypdfium2 → every page as PNG, twice: 100 DPI (cheap) + 250 DPI (detailed)
   │
   ▼
 SORTER      agent #1 (vision LLM, ONE call, all 100-DPI pages)
   │         → page map: which sections live on which pages + continuation flags
   ▼
 CHUNKER     pure code, no model. Groups 250-DPI page images into small requests
   │         along section boundaries (1-2 pages each, overlap on rules pages)
   ▼
 EXTRACTORS  agents #2-4 (vision LLM, MANY calls, async in parallel)
   │         appointments agent / rules agent / specimens agent
   │         + witness model re-extracts rules chunks for cross-checking
   ▼
 NORMALIZER  pure code. Merges chunk outputs into one draft authority matrix
   │         (dedupe overlaps, stitch split clauses, join people rosters)
   ▼
 VALIDATOR   pure code. Runs provenance checks → flags (info/warn/serious).
   │         Flags NEVER stop the flow; they annotate the review screen.
   ▼
 REVIEW      human, via the frontend. Corrects fields, resolves flags,
   │         approves → ATOMIC save (all-or-nothing transaction)
   ▼
 VERIFY      /api/verify — deterministic rule walk over the approved matrix.
             Every call is written to an audit table.
```

Why chunking: the spike showed long documents cause *attention* errors (omissions) — a 9-page
single call dropped a co-signer that a focused call catches. Small requests = focused attention.
Why async: chunking would be slow sequentially; a bounded parallel fan-out
(`asyncio.Semaphore(4)`) makes 7 chunk calls finish in roughly the time of the slowest one
(~20-30s), not the sum (~5 min).
Why the model never decides alone: banks need auditability. Agents read; code merges and
checks; humans approve; deterministic code decides.

---

## 4. Backend layout (all new code lives here)

```
backend/
  .env.example          # template below — copy to .env, fill the key
  main.py               # FastAPI app factory, CORS (frontend dev server), router mounting
  db.py                 # SQLite async engine/session; create_all on startup
  models.py             # SQLAlchemy tables (§5)
  schemas.py            # ALL Pydantic models: page map, extraction records,
                        # AuthorityRule v1, API request/response bodies
  pipeline/
    render.py           # file bytes -> {page_no: (png_100dpi, png_250dpi)}
    sorter.py           # agent 1
    chunker.py          # pure code
    extractors.py       # agents 2-4 + witness, async fan-out
    normalizer.py       # merge logic
    validator.py        # flag battery
    run.py              # orchestrator: upload_id -> staged document; progress + timing events
  verification.py       # the rule walk
  seed_demo.py          # load cached golden run into SQLite (offline demo)
  cache/                # per-stage JSON outputs of golden runs
```

`.env.example`:

```
OPENAI_API_KEY=copy-from-extraction-spike-.env
EXTRACTION_MODEL=gpt-5.6-luna
WITNESS_MODEL=gpt-5.6-terra        # empty string disables the witness (cut line)
PDF_DPI_SORT=100
PDF_DPI_EXTRACT=250
MAX_CONCURRENCY=4                  # asyncio.Semaphore per model
FUZZ_THRESHOLD=90                  # rapidfuzz ratio for quote matching (0-100)
DB_URL=sqlite+aiosqlite:///./demo.db
```

Dependencies (add to a `backend/requirements.txt`): `fastapi uvicorn[standard] sqlalchemy
aiosqlite openai python-dotenv pypdfium2 pillow rapidfuzz python-multipart pytest pytest-asyncio httpx`.

Reusable existing code: `extraction-spike/test_extraction.py` already has working
page-rendering (pypdfium2, `scale = dpi/72`), base64 data-URL image encoding, and the two
prompts that passed the spike. Copy code from it freely; do not import it.

---

## 5. Database schema (implement exactly; frontend + verification both depend on it)

### 5.1 Relational tables

```
companies           id, legal_name, vkn (10 digits), trade_registry_no, mersis (nullable),
                    address, created_at

documents           id, company_id FK, kind ('imza_sirkuleri' for now),
                    status ENUM: processing | staged | approved | rejected | failed,
                    source_path, notary_name_no, notary_date, yevmiye_no,
                    page_count, created_at, staged_at, approved_at

signatories         id, document_id FK,
                    name_printed        (exactly as in the document),
                    name_normalized     (uppercase, Turkish-aware, for joins),
                    title, id_no_masked (e.g. "182******70", may be null),
                    group_code          (e.g. "A", "B", "1", "2" … nullable),
                    valid_from DATE nullable, valid_until DATE nullable,
                    -- NULL means "unknown -> must be flagged", NEVER silently defaulted
                    evidence_page INT, specimen_image_path (nullable)

document_references id, document_id FK,      -- the cross-document chain (see §1.4)
                    ref_doc_type ('board_resolution'|'ic_yonerge'|'gazette'|'circular'|'other'),
                    ref_date, ref_number,
                    resolved ENUM: in_file | external | unknown

flags               id, document_id FK, severity ENUM: info | warn | serious,
                    check_name, message, field_path (e.g. "signatories[2].valid_until"),
                    evidence_page nullable, review_status ENUM: open | resolved | dismissed

review_decisions    id, document_id FK, reviewer, decision, corrections_json, created_at

verification_checks id, company_id FK, request_json, decision, reasons_json,
                    cited_rule_json, created_at          -- the audit log (a selling point)
```

### 5.2 JSON columns (each validated by a Pydantic model with `schema_version: 1`)

`documents.rules_json` — a list of **AuthorityRule v1** objects. This is the heart of the system;
the verification engine consumes it directly:

```json
{
  "schema_version": 1,
  "who": {"type": "group", "ref": "A"},
  "sole_or_joint": "joint",
  "joint_with": [
    {"type": "group", "ref": "B"},
    {"type": "unresolved_external", "name": "TOLGA AKAR", "note": "not defined in this document"}
  ],
  "amount_min": 500000.0,
  "amount_max": null,
  "currency": "TRY",
  "scope_tags": ["general"],
  "scope_text": "500.000,00 TL'yi aşan her türlü iş ve işlemde",
  "valid_until": "2027-03-12",
  "source": "circular",
  "evidence": {"page": 1, "quote": "500.000,00 TL'yi aşan her türlü iş ve işlemde, (A) Grubundan bir yetkili ile (B) Grubundan bir yetkilinin müşterek imzası şarttır."},
  "confidence": "high",
  "partial": false
}
```

Field rules (each traces to a spike failure — do not "simplify" them away):
- `who.type` ∈ `group | person | unresolved_external`. `person` refs use `signatories.id`.
  **Never store a bare name string as a reference** — names get normalized; IDs don't break.
- `joint_with` may contain `unresolved_external` entries → *the Tolga Akar case* stays visible.
- Amounts are **ranges** (`amount_min`/`amount_max`, null = unbounded). Circulars define
  ladders ("between 500k and 1M do X, above 1M do Y") — a single `limit` field cannot express this.
- `null`/absent means **unknown** and must co-exist distinctly with explicit "unlimited"
  (`amount_max: null` + `scope_tags: ["unlimited"]` if stated) and "indefinite"
  (`valid_until: null` only when the document says so; otherwise it's a flag) →
  *the 12.12.2023 case*.
- `evidence.quote` is verbatim Turkish from the document. Every rule must have one.
- `source` ∈ `circular | directive | annex` — annex-sourced rules confirm but never create
  authority (see Sorter labels, §6.2).
- `scope_tags` vocabulary (extendable): `general`, `credit`, `real_estate`, `litigation`,
  `hr_sgk`, `banking_ops`, `securities`, `unlimited`, `regulator`.

Other JSON columns: `documents.page_map_json` (Sorter output, §6.2),
`documents.raw_chunks_json` (raw agent outputs — debugging + the demo's "show the agents" panel),
`signatories.specimen_bboxes_json` (`[{page, x0, y0, x1, y1}]`).

---

## 6. Pipeline stages in implementation detail

### 6.1 `render.py`

Input: file bytes + extension (`.pdf`, `.jpg`, `.jpeg`, `.png`).
Output: `list[PageImages]` where `PageImages = {page_no, png_sort: bytes, png_extract: bytes}`.
PDF path: pypdfium2, `scale = dpi / 72.0`, render each page twice (100 + 250 DPI) — copy the
working loop from `extraction-spike/test_extraction.py::render_pdf_pages`. Image path: load once
with Pillow, downscale a copy to ~40% for the sort version. Also write the 250-DPI PNGs to disk
(`uploads/{document_id}/pages/{n}.png`) — the API serves them to the frontend review screen.

### 6.2 `sorter.py` — agent #1 (one vision call, all 100-DPI pages)

Job: classify pages, do NOT extract content (its images are deliberately too cheap for that).
Output (`page_map_json`):

```json
{
  "company_name_line": "YILDIZ TEKSTİL SANAYİ VE TİCARET LİMİTED ŞİRKETİ",
  "structure_hints": ["groups A and B exist"],
  "pages": [
    {"page": 1, "labels": ["identity_header", "appointments", "rules", "specimens", "notary_block"],
     "continues_on_next": false}
  ]
}
```

Label taxonomy (12, closed set):
- Primary: `identity_header`, `dayanak`, `appointments`, `rules`, `specimens`, `notary_block`
- Annex (always supporting-only): `ic_yonerge_annex`, `board_resolution_annex`,
  `gazette_annex`, `imza_beyannamesi`
- Utility: `cover_or_blank` (skip), `other_unknown` (→ becomes a serious flag immediately)

Notes for the prompt (write it in `extractors.py`-style English with Turkish terms):
a page can carry MULTIPLE labels (single-page circulars put everything on one page);
`continues_on_next` = "does a sentence/list/table on this page continue on the next page?";
`imza_beyannamesi` is a different document type that must never yield authority rules —
mislabeling it as a circular would fabricate authority.

### 6.3 `chunker.py` — pure code, no model

Input: page map + the 250-DPI images. Output: `list[Chunk]`:

```python
@dataclass
class Chunk:
    chunk_id: str            # "rules_p3-4"
    agent: str               # "appointments" | "rules" | "specimens" | "annex"
    pages: list[int]
    images: list[bytes]      # the 250-DPI PNGs
    context_header: str      # see below
    supporting_only: bool
```

Rules:
- `appointments` section → ONE chunk for the whole section (people + validity must stay together).
- `rules` section → sliding window, ≤2 pages per chunk, **1-page overlap**
  (pages 3-5 → chunks [3,4] and [4,5]; a clause split across pages is seen whole by one chunk).
- `specimens` → 1 page per chunk. Annex sections → own chunk, `supporting_only=True`.
- `identity_header`, `dayanak`, `notary_block` ride along with the appointments chunk
  (they're small and usually share page 1); if they're on separate pages, append those pages.
- Context header template (goes into every extractor call so a 2-page chunk isn't blind):
  `"Document: imza sirküleri of {company_name_line}. {structure_hints}. This request covers
  pages {pages} of a {section} section spanning pages {span}. Page numbers below are absolute."`
- Unit test: feed the 9-page T.O.M. page map (appointments 1-2, rules 3-5, specimens 6-8,
  gazette 9) → expect exactly chunks: appointments[1,2], rules[3,4], rules[4,5],
  specimens[6], specimens[7], specimens[8], annex[9].

### 6.4 `extractors.py` — agents #2-4 + witness (the async fan-out)

Three prompts (evolve from the spike's proven Pass-1/Pass-2 prompts — keep the style:
"quote verbatim, never paraphrase; write UNREADABLE instead of guessing"):

- **Appointments agent** → per person: `name_printed, title, id_no_masked, group_code,
  authority_form (münferiden/müştereken/sınırlı-per-directive), joint_with_names[],
  valid_from, valid_until, evidence {page, quote}`.
  Prompt must explicitly demand: "if an appointment states a date limit ('… tarihine kadar'),
  put it in valid_until — do not omit it" (*the 12.12.2023 case*) and "list every name in a
  joint-signature clause even if that person appears nowhere else in the document"
  (*the Tolga Akar case*).
- **Rules agent** → per clause: an AuthorityRule v1 minus resolution (who/joint_with as
  names/group codes at this stage), plus `partial: true` if the clause looks cut off at the
  chunk's page boundary.
- **Specimens agent** → per person on the page: `name_printed, title, group_code,
  signature_bbox {page, x0,y0,x1,y1}` (bbox in relative 0-1 coordinates).

Mechanics:
- One async function `call_agent(chunk, model) -> dict`, JSON-mode response, minimal params.
- Fan-out: `asyncio.gather` over all chunks under `asyncio.Semaphore(MAX_CONCURRENCY)`.
  Witness: rules chunks are additionally sent to `WITNESS_MODEL` (same prompt) — schedule both
  in the same gather; the fan-out hides the extra latency.
- Failure policy: one retry per chunk; a twice-failed chunk produces
  `{"chunk_failed": true, chunk_id, error}` — the Normalizer keeps going and the Validator
  turns it into a `serious` flag. **A chunk failure never kills the run.**
- Progress events: after each chunk completes, `run.py` appends
  `{"name": "Rules agent p3-4", "state": "done", "detail": "6 clauses"}` to the document's
  status (§7 status endpoint) — this powers the frontend's live agent panel, which is a demo
  centerpiece. Emit `state: "running"` events when the call starts.

### 6.5 `normalizer.py` — pure code merge

In order:
1. **Overlap dedupe:** rules extracted from overlapping chunks ([3,4] and [4,5] both saw p4)
   are matched by `rapidfuzz.fuzz.ratio(quote_a, quote_b) > FUZZ_THRESHOLD` → keep the
   non-partial (or longer) one.
2. **Partial stitch:** a `partial` clause surviving dedupe (no complete twin found) stays but
   is marked for the Validator.
3. **Roster join:** signatory list = appointments people ∪ specimens people, joined on
   `name_normalized` (uppercase via Turkish casing — `'i'.upper() == 'İ'`; strip titles).
   A person present in only one source → keep, note the asymmetry for the Validator.
4. **Reference resolution:** every name in `joint_with_names` / rule `who`: resolve to a
   `signatories.id` if found, else to a group code if it matches `structure_hints`, else emit
   `{"type": "unresolved_external", "name": ...}`. **Never drop an unresolved name.**
5. **Annex precedence:** rules from `supporting_only` chunks are matched (fuzzy) against
   primary rules — matches raise the primary rule's confidence; non-matches become
   annex-sourced rules with `source: "annex"` (Validator flags them; they confirm, never create).
6. Map everything into `schemas.py` models; write `rules_json`, signatory rows, reference rows.
7. Unit tests run against **cached spike outputs** (copy JSONs from `extraction-spike/outputs/`
   into `backend/tests/fixtures/`) — no API calls, no cost.

### 6.6 `validator.py` — the flag battery (annotations ONLY)

Every check returns `Flag(severity, check_name, message, field_path, evidence_page)` objects;
`run.py` saves them. **No check may raise, stop the pipeline, or change data.** P0 checks:

| # | check_name | Logic | Catches |
|---|---|---|---|
| 1 | `id_checksum` | VKN (10-digit) and TCKN (11-digit) checksum algorithms on any unmasked ID | misread digits (CUSKYA-class) |
| 2 | `unresolved_reference` | any `unresolved_external` in rules/joint_with → `warn` | Tolga Akar case |
| 3 | `validity_missing_or_conflict` | signatory with NULL `valid_until` → `warn`; a date regex (`\d{2}[./]\d{2}[./]\d{4}`) inside that person's evidence quote while field is NULL → `serious` | 12.12.2023 case |
| 4 | `model_disagreement` | field-level diff of primary vs witness rules (match rules by quote fuzzy ratio; compare amounts/joint/sole) → `warn` per differing field | union coverage |
| 5 | `quote_cross_check` | each primary rule's quote must fuzzy-match some witness quote ≥ `FUZZ_THRESHOLD`, else `warn` | invented quotes |
| 6 | `structure_sanity` | no `appointments` label anywhere → `serious`; no `notary_block` → `warn`; any appointment says "sınırlı yetkili / iç yönergede belirtilen şekilde" but zero rules with source `circular|directive` exist → `serious` ("authority rules incomplete — request the directive") | wrong/incomplete document |
| 7 | `chunk_failed` / `partial_clause` / `other_unknown` page | pass-through of pipeline incidents | anything mechanical |

P1 (only if ahead of schedule): a true OCR witness (pytesseract; or pdfium's text layer for
born-digital PDFs) to check quotes/names against a second, non-LLM reading.
Thresholds from `.env`. A check the reviewer always dismisses is a check we delete.

### 6.7 `run.py` — the orchestrator

`async def run_pipeline(document_id)`: load file → render → sorter → chunker → extractors
(fan-out) → normalizer → validator → set status `staged`. Wrap each stage with `time.perf_counter`
and append `{stage, seconds}` to a timing list stored on the document — the demo says
"~35 seconds instead of 25 minutes", this is where the number comes from. On unexpected
exception: status `failed` + a `serious` flag with the error (the review list shows it; nothing
dies silently). Trigger via FastAPI `BackgroundTasks` from the upload endpoint.

---

## 7. API contract (FREEZE IN HOUR 1 — the frontend builds against this verbatim)

All routes under `/api`. JSON everywhere except upload (multipart) and page images (PNG).

```
POST /api/upload
  multipart: file
  → 202 {"document_id": 17}

GET /api/documents/{id}/status
  → {"status": "processing",
     "stage": "extracting",              // rendering|sorting|extracting|merging|validating|staged|approved|failed
     "agents": [
       {"name": "Sorter", "state": "done", "detail": "9 pages, 4 sections"},
       {"name": "Appointments agent p1-2", "state": "done", "detail": "21 people"},
       {"name": "Rules agent p3-4", "state": "running", "detail": ""},
       {"name": "Witness (terra) p3-4", "state": "running", "detail": ""}
     ],
     "timings": [{"stage": "sorter", "seconds": 6.2}]}

GET /api/documents/{id}/review
  → {"company": {...}, "notary": {...},
     "signatories": [{...incl. valid_until, group_code, specimen_url...}],
     "rules": [AuthorityRule v1 ...],
     "flags": [{severity, check_name, message, field_path, evidence_page}],  // serious first
     "pages": ["/api/documents/17/pages/1.png", ...],
     "references": [{ref_doc_type, ref_date, ref_number, resolved}]}

GET /api/documents/{id}/pages/{n}.png     → the 250-DPI page image (review screen background)

POST /api/documents/{id}/approve
  {"reviewer": "m.erbay",
   "corrections": [{"field_path": "signatories[0].valid_until", "value": "2023-12-12"}],
   "flag_resolutions": [{"flag_id": 3, "status": "resolved"}]}
  → applies corrections + status='approved' + review_decisions row IN ONE TRANSACTION
  → 200 {"status": "approved"}     (409 if not currently 'staged')

POST /api/verify
  {"company_id": 1, "amount": 750000, "currency": "TRY", "tx_type": "general",
   "signer_ids": [3], "date": "2026-08-02"}
  → {"decision": "BLOCKED",
     "reasons": ["Amount 750,000 TRY exceeds sole-signature limit of group A (500,000 TRY)",
                 "Rule requires one group-A and one group-B signature jointly"],
     "cited_rule": {AuthorityRule v1 incl. evidence quote+page},
     "missing": [{"type": "group", "ref": "B"}],      // present when NEEDS_SECOND_SIGNATURE
     "checked_at": "..."}
  and INSERT a verification_checks audit row for every call.

GET /api/dashboard
  → static JSON: counts + mocked monitoring alerts
    (e.g. {"alerts": [{"kind": "expiry", "message": "Circular of X expires 12.03.2027"},
                      {"kind": "gazette", "message": "Board change published for Y — 2 pending transactions held"}]})
```

## 8. `verification.py` — the rule walk (deterministic, ~100 lines, unit-tested)

```
def verify(company, matrix, signatories, req) -> Decision:
  1. resolve req.signer_ids -> signatory rows; unknown id -> BLOCKED("unknown signer")
  2. date checks: any signer with valid_until < req.date -> BLOCKED("authority expired <name>")
     (NULL valid_until on an APPROVED matrix = reviewer accepted indefinite -> passes)
  3. candidate rules = rules where req.tx_type ∈ scope_tags (fall back to 'general')
     and rule.valid_until is null or >= req.date
     and (amount_min is null or amount >= amount_min)
     and (amount_max is null or amount <  amount_max)
     -> none -> BLOCKED("no rule covers this transaction")
  4. pick the tightest range (smallest amount_max - amount_min, unbounded = infinity)
  5. signer-set check against who + joint_with:
     - who: group  -> need ≥1 signer whose group_code == ref (sole: exactly that; joint: …)
     - who: person -> that signatory must be among signers
     - joint: every joint_with entry must be satisfiable by a DIFFERENT signer;
       'unresolved_external' in the applicable rule -> BLOCKED("rule references a person
       not in the system — manual check required")
  6. satisfied -> APPROVED (cite rule)
     missing exactly one co-signature -> NEEDS_SECOND_SIGNATURE (cite + missing[])
     otherwise -> BLOCKED (cite + reasons)
```

Anything ambiguous → BLOCKED with a reason. The engine never guesses; that asymmetry
("we fail safe") is a pitch line. Unit tests (hard-case matrix ground truth): Ahmet alone 400k
general → APPROVED · Ahmet alone 750k → NEEDS_SECOND_SIGNATURE (missing group B) · Ahmet+Kaya
750k → APPROVED · Ahmet alone any real_estate → BLOCKED (needs all of group A) · Kaya alone 90k
hr_sgk → APPROVED · Kaya alone 90k general → BLOCKED · anyone after 2027-03-12 → BLOCKED.

## 9. Task list (dependency-ordered; split among yourselves)

| # | Task | Time | Deliverable / acceptance |
|---|---|---|---|
| T0 | **Together, hour 0-1:** freeze §5 schema + §7 contract; hand contract to frontend | 1h | both teammates sign off; frontend unblocked |
| T1 | Scaffold `backend/`: FastAPI + CORS, db.py, models.py, .env, upload + status + page-serving endpoints with stub pipeline | 1h | `POST /api/upload` returns an id; status endpoint polls |
| T2 | `render.py` + `sorter.py` + prompt | 1.5h | correct 12-label page map for hard_case_scan.jpg AND the T.O.M. PDF |
| T3 | `chunker.py` + unit test | 1h | T.O.M. map yields exactly the 7 expected chunks |
| T4 | `extractors.py`: 3 prompts, fan-out, witness, retries, progress events | 2.5h | full extraction of hard case; agents panel data flows |
| T5 | `normalizer.py` + fixture-based unit tests (cached spike outputs, zero API cost) | 2h | draft matrix from raw chunks; dedupe verified on overlap fixture |
| T6 | `validator.py` P0 checks 1-7 | 1.5h | hard case yields ≥1 flag; seeded fixtures trigger checks 2 and 3 |
| T7 | Review + approve endpoints, atomic transaction | 1.5h | approve is all-or-nothing; 409 on double-approve |
| T8 | `verification.py` + `/api/verify` + §8 unit tests | 1.5h | all 7 listed cases pass |
| T9 | Golden cache + `seed_demo.py` | 1h | network unplugged → full review+verify demo works |
| T10 | Timing summary in status payload | 0.5h | demo number available |

Suggested split — AI engineer: T2, T4, T5, T6. Backend: T1, T3, T7, T8, T9, T10. T0 together.

## 10. Cut lines (check the clock; cut without mercy)

- **Hour 8 behind:** drop the witness model (checks 4-5 disappear; keep 1-3, 6-7);
  T.O.M. document demoted to cached screenshots.
- **Hour 12 behind:** Validator = checks 1-3 only. Skip P1 OCR entirely (it was P1 anyway).
- **Hour 16 behind:** run the pipeline once on the hard case tonight, cache everything;
  the live demo becomes a seeded replay (frontend looks identical).
  **`/api/verify` is never cut — it IS the demo.**
- **Ahead of schedule:** Q&A agent — one endpoint + one prompt over the approved matrix:
  "Can Ayşe Demir sign a ₺2M loan alone?" → answer + cited clause, live from the audience.

## 11. Definition of done

1. `uvicorn backend.main:app` → curl-upload `extraction-spike/samples/hard_case_scan.jpg` →
   status reaches `staged` in <60s → review JSON: 3 signatories (Ahmet Yılmaz A, Ayşe Demir A,
   Mehmet Kaya B), 4 rules, expiry 2027-03-12, ≥1 flag.
2. Approve via curl → §8's seven verification cases all return the expected decisions,
   each with a cited Turkish quote; `verification_checks` has one row per call.
3. `pytest backend/tests` green (chunker, normalizer fixtures, rule walk).
4. Disconnect network → fresh DB → `python backend/seed_demo.py` → review + verify flow fully
   functional from cache.
