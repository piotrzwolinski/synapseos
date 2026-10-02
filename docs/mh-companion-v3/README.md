# M+H Filter Housing Selection Companion V3 — triage (2026-10-02)

Input: `Filter Housing Selection Companion V3.docx` from Alexander Söderblom (M+H), plus his answers:
GDMI long length **850** (per tables), short-housing max filter depth **450**, GDMI material **ZM**
(no stainless; aluminium framing — stainless coverings only via specialist/sales).

Original scope = brochure `testdata/filter_housings_sweden.pdf` (version 01-09-2025).

## Deliverables

- `MH_Product_Advisor_Companion_V3_Change_Overview.xlsx` — client-facing, no commercial content.
  Sheets: Summary · 1 Fixes (in scope) · 2 Ambiguities · 3 CRQ · Open Questions.
  Regenerate with `python3 build_change_overview_xlsx.py`.
- Messages below (Matthias first — he forwards/handles the commercial side; then Alexander).

## Categories

1. **Fixes** — brochure is explicit, system deviated. Free, not estimated. F-01..F-04 done in this session.
2. **Ambiguities** — brochure self-contradiction or brochure vs Companion. Free, not estimated.
   A-01..A-05 resolved/done. A-07 (corrosion model) may become a CRQ (2–4 PD) depending on M+H's answer.
3. **CRQ** — new knowledge from the Companion not in the brochure. 9 items, 19 PD.

## Implemented in this session

- Engine used a tenant-wide `default_material: FZ` for every product code; now uses
  `ProductFamily.default_material` from the graph first (`database.get_product_family_code_format`,
  `TechnicalState.build_product_code`).
- GDMI / GDMI FLEX default ZM; GDMI FLEX AZ+ZM only; GDMI FLEX = cartridge housing; GDC FLEX wording.
- GDMI FLEX housing lengths 850/1100 (`housing_length_derivation.GDMI_FLEX`) — the `_FLEX` fallback had applied GDMI 600/850.
- GDMI: removed ENV_HOSPITAL / ENV_PHARMACEUTICAL.
- SF corrosion class `C5.1` → `C5-I` (graph, config, Scribe, prompt); legacy spelling still accepted.
- Stale GDB tests (fake 900 mm) updated.
- Graph migration: `backend/database/fix_companion_v3.py` (local) → `deploy/fix_companion_v3.sh` (Azure, run inside
  FalkorDB container, then `SAVE`). Seed `deploy/knowledge.cypher` regenerated.
- **Not yet deployed.** Backend needs a rebuild.

Regression: 70/74 on first run. The 2 random failures passed on rerun. The 2 GDMI-rooftop tests also fail on the old
graph data (catalogue says indoor-only) → see Q-04 / F-11.

## Message to Matthias (DE, sent via clipboard)

```
Betreff: M+H – Companion V3: Einordnung Fixes / Unklarheiten / CRQ

Hallo Matthias,

kurzes Update zu M+H: Alexander hat uns das „Filter Housing Selection Companion V3“ geschickt, ein Begleitdokument zur Broschüre. Ich habe es komplett gegen die Broschüre (= ursprünglicher Scope) und unseren Knowledge Graph abgeglichen und alles in drei Kategorien eingeteilt:

1. Fixes (im Scope, kostenfrei): Punkte, die in der Broschüre eindeutig stehen und die der Advisor noch nicht vollständig umsetzt. 16 Positionen, 4 davon bereits umgesetzt.
2. Unklarheiten: Widersprüche innerhalb der Broschüre oder zwischen Broschüre und Companion. 5 davon sind bereits geklärt und kostenfrei umgesetzt. Für die 6 offenen haben wir Fragen an M+H vorbereitet, die gehen mit der Mail an Alexander raus.
3. Change Requests: neues Wissen aus dem Companion, das nicht in der Broschüre steht, z. B. Do-not-infer-Regeln, Altprodukte, Normen-Q&A, 11-Schritte-Auswahlprozess und Auswahl der Aktivkohle-Medien. 9 Positionen, insgesamt 19 PT.

Details stehen in der angehängten Excel (ein Sheet pro Kategorie plus offene Fragen an M+H). Die Excel ist bewusst rein fachlich, ohne Preise; das Kommerzielle zu den CRQs würde ich gern mit dir abstimmen, bevor das an Alexander geht.

Kannst du kurz drüberschauen? Wenn es für dich passt, schicke ich es mit einer Mail an Alexander raus.

Viele Grüße
Piotr
```

## Draft to Alexander (EN, not sent — waiting for Matthias)

Open decision: keep or drop "estimated at 19 person-days" before the commercial side is agreed with Matthias.

```
Subject: RE: Filter Housing Selection Companion V3 – implementation overview

Hi Alexander,

Thank you for the Companion document and for answering our questions so quickly. It clarifies a lot, and we have already put it to use.

What we have done. We went through the Companion line by line against the brochure and the knowledge graph. Based on your answers (850 mm, 450 mm, ZM), several corrections are already implemented and tested:
- GDMI and GDMI FLEX now default to ZM. GDMI FLEX is offered in AZ and ZM only.
- GDMI FLEX uses its correct lengths of 850/1100 mm and is treated as a cartridge housing.
- GDB lengths follow the catalogue: 550 mm for filters up to 450 mm deep, 750 mm up to 650 mm.
- The SF corrosion class is shown as C5-I.
- GDMI is no longer suggested for hospital or pharmaceutical duty, in line with the "up to F9" rating.
These will go live with the next release.

How we have structured the rest. The attached Excel sorts every item into three categories:
1. Fixes: points where the brochure is explicit and the advisor did not yet follow it fully, for example door hand L/R, PT/TT transitions, EXL vs Filter Profil, and the post carbon filter option. These are part of the original scope, and we will deliver them at no extra cost.
2. Ambiguities: places where the brochure and the Companion differ, or the brochure contradicts itself. Most are already resolved thanks to your answers. A few still need your decision, listed in the "Open Questions" sheet.
3. Change requests: new knowledge the Companion introduces beyond the brochure, such as the do-not-infer rules, legacy-product routing, the 11-step selection workflow, standards Q&A and molecular media selection. We think these make the advisor much stronger. They are estimated at 19 person-days in total and itemised so you can pick and prioritise.

Open questions. Seven are listed in the "Open Questions" sheet; you can answer directly in the yellow column. The most important one is the corrosion class model: the Companion gives a class per finished housing in §2.3 but states in §10 that the complete housing is not rated. The answer affects how the advisor handles material upgrades for demanding environments.

Proposed next steps:
- We complete the in-scope fixes and deploy them.
- You review the change requests and return the open questions.
- We agree on scope and priority for the change requests, ideally before the brochure update, so the next revision can be synced in one go.

Happy to go through it on a short call if that is easier.

Best regards,
Piotr
```
