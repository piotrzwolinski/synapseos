from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.comments import Comment
from openpyxl.worksheet.datavalidation import DataValidation

import os
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "MH_Product_Advisor_Companion_V3_Change_Overview.xlsx")
F = "Arial"
HDR_FILL = PatternFill("solid", start_color="1F3864")
HDR_FONT = Font(name=F, bold=True, color="FFFFFF", size=10)
BODY = Font(name=F, size=10)
BOLD = Font(name=F, size=10, bold=True)
INPUT_FONT = Font(name=F, size=10, color="0000FF")
YELLOW = PatternFill("solid", start_color="FFFF00")
DONE_FILL = PatternFill("solid", start_color="E2EFDA")
OPEN_FILL = PatternFill("solid", start_color="FFF2CC")
thin = Side(style="thin", color="BFBFBF")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
WRAP = Alignment(wrap_text=True, vertical="top")

COLS = ["ID", "Item", "Description", "Source / basis", "Status", "Effort min (PD)", "Effort max (PD)", "Notes"]
WIDTHS = [8, 30, 60, 50, 14, 10, 10, 40]

fixes = [
    ("F-01", "GDMI FLEX housing lengths", "Use the catalogue lengths 850 mm (450 mm cylinder) and 1100 mm (600 mm cylinder + post filter). The system applied the GDMI lengths 600/850.", "Brochure, GDMI FLEX: \"Finns som standard i 850 och 1100 mm längd\"", "Done", 0.5, 0.5, ""),
    ("F-02", "GDMI FLEX / GDC FLEX product type", "GDMI FLEX described as a cartridge (carbon) housing instead of a bag/compact housing. GDC FLEX described with a pull-out cartridge plate instead of a rail.", "Brochure, GDMI FLEX: \"Patronfilterskåp ... utdragbar kolfilterplatta\"", "Done", 0.25, 0.25, ""),
    ("F-03", "GDB housing length thresholds", "GDB 550 mm for filters up to 450 mm deep, 750 mm up to 650 mm. Removed a non-existent 900 mm length and a wrong 292 mm threshold.", "Brochure, Sortiment: \"Skåp 550/600 mm – Filter max 450 mm; Skåp 750/800 mm – Filter max 650 mm\"", "Done", 0.5, 0.5, ""),
    ("F-04", "GDMI application ceiling", "GDMI no longer offered for hospital / pharmaceutical environments.", "Brochure, GDP/GDB/GDMI: \"Avsett användningsområde är för filter upp t.o.m. F9 enligt VVS AMA QGB/1\"", "Done", 0.25, 0.25, ""),
    ("F-05", "Door hand L/R", "Left/right-hinged door selectable on all housings; L/R position filled in the ordering code.", "Brochure, all housings: \"Option: Vänsterhängd lucka = L (left)\"", "Planned", 1, 1, ""),
    ("F-06", "Flange connection for GDMI FLEX", "Add the 40 mm flange option (F) to GDMI FLEX; check the length offset against the PG/F40 tables on all housings.", "Brochure, all housings: \"alternativt utförande är med 40 mm flänskant\"", "Planned", 0.5, 0.5, "Offset value depends on A-06"),
    ("F-07", "Round-duct transitions PT / TT", "Offer a PT (flat) or TT (conical) transition when the customer has a round duct; generate the transition code (e.g. PT-600x600-315-FZ).", "Brochure, Övergångar: \"Om du behöver en formförändring ... beställa detta separat\"", "Planned", 1.5, 1.5, ""),
    ("F-08", "Filter products from the brochure", "Complete depths of the brochure example products, remove duplicates, add missing Scandsorb KOH/KI 450/600 (61090M2396, 61090M3978) and AIRSQUARE ePM1 55 %. A filter named by the customer drives the housing length.", "Brochure, \"Filter & tillbehör\" pages (GDP, GDB, GDMI, GDC family)", "Planned", 1.5, 1.5, ""),
    ("F-09", "EXL vs Filter Profil by filter class", "Recommend EXL for fine filters and Filter Profil for low filter classes only.", "Brochure, Tillbehör: EXL \"Rekommenderas för finfilter och högre filterklasser\"; Filter Profil \"Rekommenderas för låga filterklasser\"", "Planned", 0.5, 0.5, ""),
    ("F-10", "F9 ceiling vs H13 elements", "A NANOCLASS CUBE PRO H13 element fitting a GDB/GDMI housing is not presented as a HEPA installation.", "Brochure: \"upp t.o.m. F9 enligt VVS AMA QGB/1\"", "Planned", 0.5, 0.5, ""),
    ("F-11", "Indoor use only", "All housings treated as indoor-only; remove the rooftop/outdoor recommendation from GDMI.", "Brochure, every housing: \"För inomhusbruk\"", "Planned", 0.5, 0.5, "Confirm with Q-04"),
    ("F-12", "Post carbon filter (polisfilter)", "Offered only in the 900/950 (GDC, GDC FLEX) and 1100/1150 (GDMI FLEX) lengths, with the AIRSQUARE ePM1 55 % part number.", "Brochure, GDC family: \"Option: Skåp L = 900/950 mm – Förmonterad filterskena för polisfilter\"", "Planned", 0.5, 0.5, ""),
    ("F-13", "Accessory data check", "Verify EXL lengths, Filter Profil sizes, BFF and PFF tables against the brochure.", "Brochure, Tillbehör / BFF / PFF pages", "Planned", 0.5, 0.5, ""),
    ("F-14", "Insulation of other housings", "When GDMI is not selected, state that other housings are insulated on site.", "Brochure, \"Vid val av skåp tänk på\": \"Övriga skåp isoleras på plats\"", "Planned", 0.5, 0.5, ""),
    ("F-15", "Duplicate housing-length question (GDMI)", "Remove a malformed duplicate housing-length feature that can trigger the same question twice.", "Internal data defect", "Planned", 0.25, 0.25, ""),
    ("F-16", "Release", "Backend release, graph migration on Azure, full regression run.", "–", "Planned", 1, 1, ""),
]

ambig = [
    ("A-01", "GDMI lengths", "Text: 550/600 and 800/850 mm. Size table and Sortiment: 600/650 and 850/900 mm.", "Brochure GDMI text vs size table", "Resolved", 0, 0, "M+H: 850 per the tables. No change needed."),
    ("A-02", "GDMI material", "Text: \"vanligen i ZM\". Ordering example: AZ. Description: \"förzinkad plåt\".", "Brochure GDMI page", "Resolved", 0.5, 0.5, "M+H: ZM. Implemented, incl. engine fix to use the family default material."),
    ("A-03", "GDMI FLEX material", "Text: \"vanligen i ZM, ej i rostfritt\". Ordering example: FZ.", "Brochure GDMI FLEX page vs Companion §2.2", "Resolved", 0.25, 0.25, "Companion: AZ and ZM only. Implemented."),
    ("A-04", "Max filter depth, short housing", "Brochure: 450 mm. Input Excel (2026-09-01): 500 mm.", "Brochure Sortiment vs input Excel", "Resolved", 0, 0, "M+H: 450. Implemented under F-03."),
    ("A-05", "SF corrosion class", "Brochure prints \"C5.1\"; Companion reads it as C5-I (typeface misprint).", "Brochure Material page vs Companion §2.1", "Resolved", 0.5, 0.5, "Implemented as C5-I; \"C5.1\" from users still recognised."),
    ("A-06", "Flange length offset", "Companion §3.2: +20 mm per end (+40 mm). Companion §9 and size tables: +50 mm.", "Companion §3.2 vs §9 / brochure tables", "Open", 0.5, 0.5, "Open – see Q-02"),
    ("A-07", "Corrosion class model", "Brochure and Companion §2.3 give a class per finished housing (C2/C4). Companion §10: \"complete housing is not rated\". Companion §1.7 forbids upgrading the class by substituting material, which the engine does today (e.g. coastal → RF).", "Companion §1.7, §2.3, §10 vs brochure", "Open", 2, 4, "Open – see Q-01. If the answer requires changing the current material-upgrade behaviour, this becomes a change request (est. 2–4 PD)."),
    ("A-08", "GDP default frame depth", "\"Standarddjup på ram\" suggests 25 mm, but the ordering example uses 50 mm. Current default: 50 mm.", "Brochure GDP page", "Open", 0.25, 0.25, "Open – see Q-05"),
    ("A-09", "GDMI FLEX weights", "Both weight columns in the size table are headed 1100/1150. First column interpreted as 850/900.", "Brochure GDMI FLEX size table", "Open", 0.25, 0.25, "Open – see Q-06"),
    ("A-10", "Companion section 11 missing", "\"Manual review\" section is referenced (incl. the FZ in the GDMI FLEX example) but not included in V3.", "Companion V3", "Open", 0, 0, "Open – see Q-03"),
    ("A-11", "Selection checklist handling", "The brochure lists 6 topics (modules/airflow, material, filter type, connection, insulation, transitions) but not whether to ask or assume the standard. Proposal: state assumed defaults explicitly (e.g. \"assumed: FZ, PG, right-hinged door, insulate on site\").", "Brochure, \"Vid val av skåp tänk på\"", "Proposed", 1, 1, "Open – see Q-07"),
]

crq = [
    ("CRQ-01", "Advisory guardrails", "Enforce the 9 do-not-infer rules not contained in the brochure (no leakage class claims A–D / L1–L3, no single ePM1 value for F9, no ISO 14644 / P-marking / Eurovent claims for the housing, etc.), with one regression test per rule.", "Companion §10 (\"hard rules\"), §1", "Proposed", 3, 3, ""),
    ("CRQ-02", "Legacy & out-of-scope routing", "Recognise legacy housings (GDD, GDR, GDR HEPA, GDR BC-FW, NSC) and special duties (biohazard, nuclear, pharma containment, safe-change, installed HEPA); decline and route to a specialist.", "Companion §0, §5.7, §10 – not in brochure", "Proposed", 2, 2, ""),
    ("CRQ-03", "Filter classification", "ISO 16890 classes with approximate EN 779 mapping; F9 treated as a ceiling and confirmed against the actual filter.", "Companion §1.4–1.5", "Proposed", 2, 2, ""),
    ("CRQ-04", "Extended filter catalogue", "Filter products and depths beyond the brochure examples (e.g. AIRPOCKET ECO 360/500/535 mm).", "Companion §6.3, §7", "Proposed", 1.5, 1.5, "Requires product data from M+H"),
    ("CRQ-05", "Molecular media selection", "Select SC carbon vs KOH/KI by contaminant (VOC vs SO₂, H₂S, O₃); ISO 10121-3 duty classes; contact-time guidance.", "Companion §1.8, §7.3", "Proposed", 2.5, 2.5, ""),
    ("CRQ-06", "Prescriptive selection workflow", "Guide the customer through the 11-step order: contaminant type → filter form → class → insulation → depth → airflow → corrosion → service access (FLEX) → connection → door → accessories.", "Companion §8", "Proposed", 2, 2, ""),
    ("CRQ-07", "Standards Q&A", "Answer questions on the 12 referenced standards, incl. what each does NOT certify.", "Companion §1", "Proposed", 3, 3, ""),
    ("CRQ-08", "Proactive accessory bundling", "AI adds matching accessories (EXL, Filter Profil, BFF/PFF, transitions) to the offer unprompted.", "Companion §8 step 11", "Proposed", 1, 1, "Data itself covered by F-07 / F-13"),
    ("CRQ-09", "Brochure Rev F re-sync", "Compare the updated brochure against the knowledge graph, migrate data, regenerate seed, full regression.", "New input document", "Proposed", 2, 2, "Per brochure revision"),
]

questions = [
    ("Q-01", "Corrosion class model", "Is the corrosion class stated per finished housing (Companion §2.3, brochure C2/C4) or per raw material with the complete housing not rated (Companion §10)? May the AI raise the class by proposing a different material (e.g. RF for coastal)?", "A-07"),
    ("Q-02", "Flange length offset", "Does the 40 mm flange add +40 mm (Companion §3.2) or +50 mm (§9 and size tables) to the housing length?", "A-06, F-06"),
    ("Q-03", "Companion section 11", "Could you send the \"Manual review\" section referenced in V3?", "A-10"),
    ("Q-04", "GDMI outdoors", "The brochure states \"För inomhusbruk\" for all housings. Should the AI block GDMI on a rooftop, or recommend it as the insulated option?", "F-11"),
    ("Q-05", "GDP default frame depth", "Is the standard GDP frame depth 25 mm or 50 mm?", "A-08"),
    ("Q-06", "GDMI FLEX weights", "Please confirm that the first weight column in the GDMI FLEX size table refers to the 850/900 length.", "A-09"),
    ("Q-07", "Default assumptions", "Is it acceptable that the AI assumes standard options (FZ / ZM per family, PG, right-hinged door) and states them in the answer, rather than asking each time?", "A-11"),
]


def table(ws, rows, title, effort=True):
    cols = COLS if effort else [c for c in COLS if "Effort" not in c]
    widths = WIDTHS if effort else [w for c, w in zip(COLS, WIDTHS) if "Effort" not in c]
    if not effort:
        rows = [r[:5] + r[7:] for r in rows]
    ws["A1"] = title
    ws["A1"].font = Font(name=F, size=13, bold=True)
    for c, (h, w) in enumerate(zip(cols, widths), 1):
        cell = ws.cell(row=3, column=c, value=h)
        cell.font, cell.fill, cell.alignment, cell.border = HDR_FONT, HDR_FILL, Alignment(wrap_text=True, vertical="center"), BORDER
        ws.column_dimensions[cell.column_letter].width = w
    for r, row in enumerate(rows, 4):
        for c, v in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font, cell.alignment, cell.border = BODY, WRAP, BORDER
            if effort and c in (6, 7):
                cell.number_format = "0.00"
        fill = DONE_FILL if row[4] in ("Done", "Resolved") else OPEN_FILL if row[4] == "Open" else None
        if fill:
            ws.cell(row=r, column=5).fill = fill
    last = 3 + len(rows)
    t = last + 1
    lastcol = "H" if effort else "F"
    if effort:
        ws.cell(row=t, column=2, value="Total").font = BOLD
    for c in ((6, 7) if effort else ()):
        L = ws.cell(row=4, column=c).column_letter
        cell = ws.cell(row=t, column=c, value=f"=SUM({L}4:{L}{last})")
        cell.font, cell.number_format, cell.border = BOLD, "0.00", BORDER
    ws.freeze_panes = "C4"
    ws.auto_filter.ref = f"A3:{lastcol}{last}"
    dv = DataValidation(type="list", formula1='"Done,Resolved,Planned,Open,Proposed,Approved,Rejected"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"E4:E{last}")
    return last


wb = Workbook()
s = wb.active
s.title = "Summary"
f_last = table(wb.create_sheet("1 Fixes (in scope)"), fixes, "1 · Fixes – brochure is explicit, system deviated", effort=False)
a_last = table(wb.create_sheet("2 Ambiguities"), ambig, "2 · Ambiguities & inconsistencies in source documents", effort=False)
c_last = table(wb.create_sheet("3 CRQ"), crq, "3 · Change requests – new knowledge from Selection Companion V3")

q = wb.create_sheet("Open Questions")
q["A1"] = "Open questions to MANN+HUMMEL"
q["A1"].font = Font(name=F, size=13, bold=True)
for c, (h, w) in enumerate(zip(["ID", "Topic", "Question", "Blocks", "M+H answer"], [8, 26, 80, 14, 50]), 1):
    cell = q.cell(row=3, column=c, value=h)
    cell.font, cell.fill, cell.border = HDR_FONT, HDR_FILL, BORDER
    q.column_dimensions[cell.column_letter].width = w
for r, row in enumerate(questions, 4):
    for c, v in enumerate(list(row) + [None], 1):
        cell = q.cell(row=r, column=c, value=v)
        cell.font, cell.alignment, cell.border = BODY, WRAP, BORDER
    q.cell(row=r, column=5).fill = YELLOW
q.cell(row=5 + len(questions), column=1, value="Yellow cells: please fill in your answer.").font = Font(name=F, size=9, italic=True)
q.freeze_panes = "C4"

# Summary
s["A1"] = "M+H Product Advisor – Selection Companion V3: change overview"
s["A1"].font = Font(name=F, size=14, bold=True)
s["A2"] = "Basis: Filterskåp brochure (version 01-09-2025) = original scope; Filter Housing Selection Companion V3 = new input."
s["A2"].font = Font(name=F, size=10, italic=True)
hdr = ["Category", "Items", "Done / resolved", "Open / planned", "Effort min (PD)", "Effort max (PD)", "Scope"]
for c, (h, w) in enumerate(zip(hdr, [34, 8, 14, 14, 14, 14, 50]), 1):
    cell = s.cell(row=4, column=c, value=h)
    cell.font, cell.fill, cell.border = HDR_FONT, HDR_FILL, BORDER
    cell.alignment = Alignment(wrap_text=True, vertical="center")
    s.column_dimensions[cell.column_letter].width = w
cats = [
    ("1 · Fixes (in scope)", "'1 Fixes (in scope)'", f_last, "Original scope (brochure)", False),
    ("2 · Ambiguities", "'2 Ambiguities'", a_last, "Clarification of source documents. A-07 may become a change request depending on the M+H answer", False),
    ("3 · Change requests", "'3 CRQ'", c_last, "New scope (Companion V3) – subject to approval", True),
]
for r, (name, sh, last, treat, charge) in enumerate(cats, 5):
    s.cell(row=r, column=1, value=name)
    s.cell(row=r, column=2, value=f"=COUNTA({sh}!A4:A{last})")
    s.cell(row=r, column=3, value=f'=COUNTIF({sh}!E4:E{last},"Done")+COUNTIF({sh}!E4:E{last},"Resolved")')
    s.cell(row=r, column=4, value=f"=B{r}-C{r}")
    if charge:
        s.cell(row=r, column=5, value=f"={sh}!F{last + 1}")
        s.cell(row=r, column=6, value=f"={sh}!G{last + 1}")
    else:
        s.cell(row=r, column=5, value="–")
        s.cell(row=r, column=6, value="–")
    s.cell(row=r, column=7, value=treat)
    for c in range(1, 8):
        cell = s.cell(row=r, column=c)
        cell.font, cell.border, cell.alignment = (Font(name=F, size=10, color="008000") if c in (5, 6) else BODY), BORDER, WRAP
        if c in (5, 6):
            cell.number_format = "0.00"
        if c in (8, 9):
            cell.number_format = "#,##0"
s.cell(row=8, column=1, value="Open questions to M+H").font = BOLD
s.cell(row=8, column=2, value=f"=COUNTA('Open Questions'!A4:A{3 + len(questions)})").font = BODY

s["A11"] = "Legend"
s["A11"].font = BOLD
legend = [
    ("Yellow cell", "Input – M+H answers (Open Questions sheet)"),
    ("Green text", "Linked from the category sheets"),
    ("Status green", "Done / resolved"),
    ("Status amber", "Open – waiting for M+H input"),
    ("PD", "Person-day (change requests only); includes graph data, code, unit + end-to-end regression tests, Azure deployment"),
]
for i, (k, v) in enumerate(legend, 12):
    s.cell(row=i, column=1, value=k).font = BODY
    s.cell(row=i, column=2, value=v).font = BODY

wb.save(OUT)
print(OUT)
