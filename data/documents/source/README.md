# `data/documents/source/` — notarial text drop location

**Owner: the AI engineer. Deadline: H2 (plan GAP-10, Phase 0 data step 3).**

Drop the final synthetic notarial Turkish text here, one plain-text UTF-8 file
per case:

```
case1.txt   temiz sirküler — ABC Teknoloji, Ali Yılmaz + Ayşe Demir
case2.txt   müşterek imza zorunlu — ABC Teknoloji
case3.txt   Zeta İnşaat / Kemal Öz  (başvurudaki ABC ile kasıtlı uyumsuz)
case4.txt   — yok; case 4, case1.pdf belgesini yeniden kullanır
```

Format: the **first paragraph becomes the centred heading**; blank lines
separate paragraphs. Nothing else is interpreted, so write ordinary prose.

Once the text is here, the full-stack side renders the demo documents (H4):

```bash
python scripts/render_documents.py
```

That produces `data/documents/caseN.pdf` and
`data/documents/pages/caseN/page-*.png`.

## What case 1 must contain

Section 11.1 makes the clean fixture deliberately **Act-2 capable**, so the
stage can connect branch approval to mobile enforcement. Its text needs to be
the source for both signers and all four rules:

| Subject | Limit | Signature requirement |
|---|---|---|
| Genel işlemler | ≤ 500.000,00 TL | Ali Yılmaz tek başına |
| Genel işlemler | > 500.000,00 TL | Ali Yılmaz + Ayşe Demir müştereken |
| Kredi | tutar sınırı yok | Ali Yılmaz + Ayşe Demir müştereken |
| Gayrimenkul | — | yetki yok |

These limits and people are **fixture data**, not product constants. No engine
may ever read them from code (plan sections 1.4 and 18) — the 500.000 TL
boundary reaches the authority engine only through the extracted rule.

## Still outstanding after rendering

Phase 0 data step 6: at least one synthetic document must be **printed and
re-photographed** so the demo proves the extractor handles a photographed page,
not only a clean digital render. That is a physical step — print `case1.pdf`,
photograph it, and save the image as `data/documents/case1-photo.jpg`.
