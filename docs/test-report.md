# SynapseOS HVAC — Test Report

Generated: 2026-02-11 18:00
Endpoint: http://localhost:8000/consult/deep-explainable/stream
Tests: 28

## Summary

| # | Test | Category | Expected | Result |
|---|------|----------|----------|--------|
| 1 | env_hospital_gdb_fz | env | BLOCK | PASS |
| 2 | env_hospital_gdmi_rf | env | PASS | **FAIL** |
| 3 | env_outdoor_gdb_fz | env | RISK → PIVOT | PASS |
| 4 | env_outdoor_gdmi_fz | env | PASS | PASS |
| 5 | env_marine_gdb_fz | env | BLOCK | PASS |
| 6 | env_swimming_pool | env | BLOCK (material) | PASS |
| 7 | env_kitchen_gdb_fz | env | WARN | PASS |
| 8 | assembly_kitchen_gdc_flex_rf | assembly | ASSEMBLY | PASS |
| 9 | assembly_kitchen_gdc_rf | assembly | ASSEMBLY | PASS |
| 10 | assembly_no_trigger_office_gdc | assembly | NO ASSEMBLY | **FAIL** |
| 11 | atex_powder_coating | atex | GATE (clarification) | PASS |
| 12 | atex_explicit_indoor | atex | ATEX awareness | PASS |
| 13 | sizing_large_airflow | sizing | MULTI-MODULE | PASS |
| 14 | sizing_single_module_600x600 | sizing | SINGLE MODULE | PASS |
| 15 | sizing_dimension_mapping | sizing | DIMENSION MAP | PASS |
| 16 | sizing_multi_tag | sizing | MULTI-TAG | PASS |
| 17 | sizing_space_constraint | sizing | CLEARANCE WARNING | PASS |
| 18 | material_chlorine_fz_block | material | BLOCK (material) | PASS |
| 19 | material_rf_hospital_ok | material | PASS (material OK) | **FAIL** |
| 20 | positive_office_gdb_fz | positive | CLEAN PASS | PASS |
| 21 | positive_warehouse_gdb_fz | positive | CLEAN PASS | PASS |
| 22 | positive_gdp_basic | positive | CLEAN PASS | PASS |
| 23 | clarif_no_product | clarif | RECOMMEND | PASS |
| 24 | clarif_no_airflow | clarif | ASK AIRFLOW | PASS |
| 25 | clarif_no_dimensions | clarif | ASK DIMENSIONS | PASS |
| 26 | edge_pharma_cleanroom | env | STRICT HYGIENE | PASS |
| 27 | edge_dual_concern | env | DOUBLE STRESSOR | **FAIL** |
| 28 | edge_pff_basic | positive | CLEAN PASS | PASS |

**Total: 24 passed, 4 failed / 28 tests**

---

## Detailed Results

### 1. `env_hospital_gdb_fz` — PASS

**Category:** env | **Time:** 13.3s

**Pytanie:**
> We are upgrading the air handling system in a hospital. We need GDB housings in standard Galvanized (FZ) for 600x600 duct. Airflow 3400 m³/h.

**Co powinno być (PDF):**
- **Decyzja:** BLOCK
- **Dlaczego:** GDB ma konstrukcję BOLTED — nie spełnia wymagań szczelności i higieny dla szpitala. Materiał FZ (galwanizowany) nie jest odporny na chlor (>50ppm w szpitalach). System powinien ZABLOKOWAĆ i zasugerować: GDMI (izolowany, spawane szwy) w materiale RF (stal nierdzewna).
- **Kluczowe sprawdzenia:** Wykrycie środowiska szpitalnego, blokada env whitelist, sugestia GDMI+RF

**Co zrobił system:**
- **Risk:** CRITICAL
- **Wykryta aplikacja:** Hospital
- **Ostrzeżenia:** 5
- **Tagi:** 2
- **Policy warning:** Material tolerates max 0ppm chlorine but environment has ~60ppm. Upgrade material.
- **Policy warning:** Product not rated for ENV_HOSPITAL installation (allowed: ENV_INDOOR, ENV_ATEX). This product uses BOLTED construction which does not meet the leakage
- **Odpowiedź:** the gdb housings are intended for a hospital air handling system with 600x600mm ducts and 3400 m³/h airflow. however, the standard galvanized steel (fz) construction is not suitable for this environment. the hospital environment exposes the system to chlorine exposure and imposes hygiene requirements. zinc coatings (like fz) corrode rapidly in chlorinated environments, requiring a minimum of c5 corrosion resistance (stainless steel). additionally, the gdb family's bolted construction does not me

---

### 2. `env_hospital_gdmi_rf` — FAIL

**Category:** env | **Time:** 12.5s

**Pytanie:**
> We are specifying GDMI housings for a hospital ventilation upgrade. Material: Stainless Steel (RF). Size 600x600, airflow 3400 m³/h.

**Co powinno być (PDF):**
- **Decyzja:** PASS
- **Dlaczego:** GDMI to jedyny housing rated dla szpitali — spawane szwy, izolacja, spełnia klasę szczelności. RF (stal nierdzewna) jest odporna na chlor. Powinien przejść BEZ blokady i zapytać o brakujące parametry (housing length).
- **Kluczowe sprawdzenia:** Brak blokady env whitelist, normalna konfiguracja, clarification na housing length

**Co zrobił system:**
- **Risk:** CRITICAL
- **Wykryta aplikacja:** Hospital
- **Ostrzeżenia:** 2
- **Tagi:** 1
- **Policy warning:** Product not rated for ENV_HOSPITAL installation (allowed: ENV_INDOOR, ENV_OUTDOOR, ENV_ATEX). This product uses BOLTED construction which does not mee
- **Policy warning:** ⚠️ MATERIAL NOT AVAILABLE: RF is NOT available for GDMI. Available materials: Zinkmagnesium.
- **Odpowiedź:** for the hospital ventilation upgrade, the gdmi housing is a good starting point. however, there are a few critical issues to address before we can finalize the configuration. first, the gdmi product line is not rated for hospital environments due to its bolted construction, which does not meet the leakage class and hygiene requirements. second, while you requested stainless steel (rf), this material is not available for the gdmi product family. the available material is zinkmagnesium (zm). unfor

**FAILED Assertions:**
- `no_critical_block`: Expected NOT 'CRITICAL', but got it
- `no_environment_block`: Expected NONE of [not rated|not suitable|blocked|cannot be used] but found [not rated]

**Graph dependency:** ProductFamily(FAM_GDMI).allowed_environments must include ENV_HOSPITAL

---

### 3. `env_outdoor_gdb_fz` — PASS

**Category:** env | **Time:** 12.2s

**Pytanie:**
> I need a GDB housing for a rooftop exhaust system. The installation is outdoors on the building roof. Airflow is 3400 m³/h, size 600x600. Material: Galvanized (FZ).

**Co powinno być (PDF):**
- **Decyzja:** RISK → PIVOT
- **Dlaczego:** GDB nie ma izolacji termicznej. Instalacja outdoor = ryzyko kondensacji (rosa). System powinien ostrzec o KONDENSACJI i zasugerować GDMI (izolowany) jako alternatywę. Kluczowe: powód blokady to BRAK IZOLACJI, nie 'bolted construction'.
- **Kluczowe sprawdzenia:** Wykrycie outdoor stressor, wspomnienie o kondensacji/izolacji, pivot do GDMI

**Co zrobił system:**
- **Risk:** CRITICAL
- **Ostrzeżenia:** 7
- **Tagi:** 1
- **Odpowiedź:** the gdb housing is not suitable for outdoor rooftop installation due to condensation risk on non-insulated metal surfaces.  to prevent this, i recommend the gdmi modulfilterskåp, which is designed with double-wall insulation for outdoor environments. to finalize the configuration: what is the minimum expected ambient temperature at the installation site?

---

### 4. `env_outdoor_gdmi_fz` — PASS

**Category:** env | **Time:** 16.1s

**Pytanie:**
> I need GDMI insulated housings for an outdoor rooftop installation. Size 600x600, airflow 3400 m³/h, material Galvanized (FZ).

**Co powinno być (PDF):**
- **Decyzja:** PASS
- **Dlaczego:** GDMI jest przeznaczony do instalacji outdoor — ma izolację termiczną. FZ jest akceptowalny outdoor (o ile nie ma salt spray). Powinien przejść normalnie, zapytać o housing length.
- **Kluczowe sprawdzenia:** Brak blokady, normalna konfiguracja

**Co zrobił system:**
- **Risk:** WARNING
- **Ostrzeżenia:** 1
- **Tagi:** 1
- **Clarification:** Please provide these values.
- **Policy warning:** FZ is NOT available for GDMI. Available materials: Zinkmagnesium.
- **Odpowiedź:** **important:** fz (stainless steel) is **not available** for gdmi. available material options: zinkmagnesium. please select an available material to proceed. for your rooftop gdmi housing (600x600mm, 3400 m³/h), galvanized steel (fz) is unavailable for this product family. zinkmagnesium (zm) is the recommended alternative for outdoor environments due to its superior corrosion resistance. to finalize the configuration, i need two more details: what is the minimum expected ambient temperature at t

---

### 5. `env_marine_gdb_fz` — PASS

**Category:** env | **Time:** 16.1s

**Pytanie:**
> We need GDB filter housings for a marine offshore platform. Material: Galvanized (FZ). Size 600x600, airflow 3400 m³/h.

**Co powinno być (PDF):**
- **Decyzja:** BLOCK
- **Dlaczego:** Marine/offshore: solanka (salt spray) niszczy FZ galwanizowany. Dodatkowo outdoor = potrzeba izolacji. GDB nie ma izolacji, FZ nie odporny na sól. Powinien zablokować i sugerować GDMI-RF.
- **Kluczowe sprawdzenia:** Wykrycie marine/salt stressor, blokada materiału, sugestia RF + GDMI

**Co zrobił system:**
- **Risk:** CRITICAL
- **Wykryta aplikacja:** Marine/Offshore
- **Ostrzeżenia:** 16
- **Tagi:** 1
- **Odpowiedź:** the gdb filter housing is not suitable for outdoor marine environments due to its bolted construction, which does not meet leakage and hygiene requirements. additionally, the galvanized steel (fz) construction is prone to corrosion from salt spray.  i recommend the gdmi modulfilterskåp, which is approved for outdoor environments. to proceed with the configuration, i need two more details: what is the minimum expected ambient temperature at the installation site? what is the typical relative humi

---

### 6. `env_swimming_pool` — PASS

**Category:** env | **Time:** 13.1s

**Pytanie:**
> I need a ventilation housing for a swimming pool hall. The chlorine level is approximately 60ppm. We want GDB in standard Galvanized (FZ), size 600x600.

**Co powinno być (PDF):**
- **Decyzja:** BLOCK (material)
- **Dlaczego:** Basen = wysokie stężenie chloru (~60ppm). FZ galwanizowany wytrzymuje max ~25ppm. Powinien zablokować materiał FZ i zasugerować RF (stal nierdzewna).
- **Kluczowe sprawdzenia:** Wykrycie chloru, blokada materiału FZ, sugestia RF

**Co zrobił system:**
- **Risk:** CRITICAL
- **Wykryta aplikacja:** Swimming Pool
- **Ostrzeżenia:** 5
- **Tagi:** 2
- **Odpowiedź:** the gdb housing in fz material is not suitable for the swimming pool hall environment due to the high chlorine concentration. the zinc coating (c3) will corrode rapidly in such conditions. minimum c5 corrosion resistance (stainless steel) is required. unfortunately, no standard catalog product currently satisfies all requirements for a gdb housing in a swimming pool environment with 60ppm chlorine concentration. a solution would need to be constructed from stainless steel (c5) and rated for pool

---

### 7. `env_kitchen_gdb_fz` — PASS

**Category:** env | **Time:** 11.2s

**Pytanie:**
> I need a GDB housing for a commercial kitchen exhaust. Size 600x600, FZ material, airflow 3400 m³/h.

**Co powinno być (PDF):**
- **Decyzja:** WARN
- **Dlaczego:** Kuchnia = tłuszcz (grease stressor). GDB ma filtrację mechaniczną — łapie cząstki tłuszczu. GDB sam w sobie jest OK jako pre-filtr, ale system powinien wspomnieć o greasy/kitchen context. NIE wymaga assembly (bo GDB nie ma adsorpcji węglowej).
- **Kluczowe sprawdzenia:** Wykrycie kuchni/tłuszczu, brak assembly trigger (bo GDB nie carbon)

**Co zrobił system:**
- **Risk:** CRITICAL
- **Wykryta aplikacja:** Commercial Kitchen
- **Ostrzeżenia:** 7
- **Tagi:** 1
- **Odpowiedź:** the gdb filter housing is not suitable for commercial kitchen exhaust due to the presence of grease and chemical vapors. lipids in kitchen exhaust permanently coat activated carbon pores via irreversible adsorption, deactivating the carbon filter. a pre-filter stage is mandatory to remove grease before the carbon filtration stage. to proceed with the correct configuration, i need to specify both a grease filter and a carbon filter. which housing length is required for both stages?

---

### 8. `assembly_kitchen_gdc_flex_rf` — PASS

**Category:** assembly | **Time:** 13.6s

**Pytanie:**
> I'm designing ventilation exhaust for a commercial kitchen. We need a GDC-FLEX carbon housing for 600x600mm duct in Stainless Steel (RF). Airflow is 2000 m³/h.

**Co powinno być (PDF):**
- **Decyzja:** ASSEMBLY
- **Dlaczego:** GDC-FLEX to housing węglowy (carbon) z TRAIT_POROUS_ADSORPTION. W kuchni tłuszcz zatyka pory węgla (NEUTRALIZED_BY). System MUSI dodać GDP jako protector (pre-filtr mechaniczny) upstream. Wynik: dwustopniowy assembly GDP→GDC-FLEX.
- **Kluczowe sprawdzenia:** Wykrycie kuchni, trigger assembly, GDP jako protector, two-stage

**Co zrobił system:**
- **Wykryta aplikacja:** Commercial Kitchen
- **Ostrzeżenia:** 4
- **Tagi:** 2
- **Product card:** Tak
- **Product cards:** 2
- **Policy warning:** ⚠️ MATERIAL NOT AVAILABLE: RF is NOT available for GDC_FLEX. Available materials: Förzinkat (Ocynk).
- **Odpowiedź:** **important:** rf (stainless steel) is **not available** for gdc_flex. available material options: förzinkat (ocynk). please select an available material to proceed. for your commercial kitchen exhaust system, a two-stage filtration system is required to protect the carbon filter from grease contamination. the system will consist of a gdp planfilterskåp pre-filter and a gdc_flex carbon filter, both with 600x600mm dimensions and designed for an airflow of 2000 m³/h. please note that stainless ste

---

### 9. `assembly_kitchen_gdc_rf` — PASS

**Category:** assembly | **Time:** 12.8s

**Pytanie:**
> We need a GDC carbon cartridge housing for a restaurant kitchen exhaust. 600x600, RF material, 2400 m³/h.

**Co powinno być (PDF):**
- **Decyzja:** ASSEMBLY
- **Dlaczego:** GDC to też housing węglowy (cartridge carbon). Ta sama logika co GDC-FLEX. Tłuszcz w kuchni zatyka carbon cartridges. GDP protector wymagany upstream.
- **Kluczowe sprawdzenia:** Wykrycie kuchni, assembly trigger, GDP protector

**Co zrobił system:**
- **Risk:** CRITICAL
- **Wykryta aplikacja:** Commercial Kitchen
- **Ostrzeżenia:** 4
- **Tagi:** 2
- **Clarification:** Which housing length is required?
- **Odpowiedź:** for your restaurant kitchen exhaust application, a two-stage filtration system is required. the gdc carbon filter housing requires upstream protection from grease and chemical vapors. lipids in kitchen exhaust permanently coat activated carbon pores via irreversible adsorption, even in trace amounts. to prevent this, a pre-filter stage is mandatory. we have configured a gdp planfilterskåp as stage 1 (protector) and the gdc family as stage 2 (target). both stages will use your specified dimension

---

### 10. `assembly_no_trigger_office_gdc` — FAIL

**Category:** assembly | **Time:** 9.1s

**Pytanie:**
> We need GDC carbon cartridge housings for an office building. The goal is to remove odors from the supply air. Size 600x600, FZ material.

**Co powinno być (PDF):**
- **Decyzja:** NO ASSEMBLY
- **Dlaczego:** GDC w biurze: carbon jest dla kontroli zapachów, nie ma tłuszczu. Brak grease stressor = brak NEUTRALIZATION veto = brak assembly. System powinien normalnie skonfigurować GDC.
- **Kluczowe sprawdzenia:** Brak assembly, normalna konfiguracja GDC

**Co zrobił system:**
- **Risk:** CRITICAL
- **Wykryta aplikacja:** Office/Commercial
- **Ostrzeżenia:** 1
- **Tagi:** 1
- **Odpowiedź:** the gdc filter housing is a good choice for odor control in your office building. however, the standard gdc housing with bolted construction is not rated for office environments due to leakage class and hygiene requirements. to meet the requirements for an office environment, the solution would need to have a higher leakage class and meet hygiene standards. unfortunately, no standard catalog product currently satisfies all requirements simultaneously. i recommend contacting our custom engineerin

**FAILED Assertions:**
- `asks_params_or_card`: Expected at least one of [response.clarification_needed|response.product_card|response.product_cards] to exist

**Graph dependency:** GDC in benign environment should NOT trigger assembly

---

### 11. `atex_powder_coating` — PASS

**Category:** atex | **Time:** 10.2s

**Pytanie:**
> I need an air filtration solution for a powder coating booth. The booth produces fine powder particles and we need to handle the exhaust air. What do you recommend?

**Co powinno być (PDF):**
- **Decyzja:** GATE (clarification)
- **Dlaczego:** Powder coating = combustible dust = ATEX classified atmosphere. System MUSI zapytać o strefę Ex (Zone 20/21/22 Dust) ZANIM zaproponuje produkt. LogicGate GATE_ATEX_ZONE powinien się aktywować.
- **Kluczowe sprawdzenia:** ATEX gate trigger, clarification z pytaniem o strefę, NIE podaje produktu

**Co zrobił system:**
- **Wykryta aplikacja:** Powder Coating Line
- **Ostrzeżenia:** 11
- **Tagi:** 2
- **Clarification:** Please provide these details to proceed.
- **Odpowiedź:** for the powder coating booth application, a two-stage filtration system is required to protect the carbon filter from particulate matter and ensure effective gas and odor removal. the first stage will be a mechanical pre-filter (gdp planfilterskåp) to capture powder particles. activated carbon pores get physically blocked by particles, rendering gas adsorption useless. pre-filtration is mandatory. the second stage will be a carbon filter (gdc patronfilterskåp) for chemical vapor exposure. to fin

---

### 12. `atex_explicit_indoor` — PASS

**Category:** atex | **Time:** 11.4s

**Pytanie:**
> We have an ATEX Zone 22 area in our factory. Need GDB filter housings for the ventilation. 600x600, FZ, 3400 m³/h.

**Co powinno być (PDF):**
- **Decyzja:** ATEX awareness
- **Dlaczego:** User wprost mówi 'ATEX Zone 22' — system powinien rozpoznać i uwzględnić. Nawet z podaną strefą, system powinien zwrócić uwagę na ATEX klasyfikację.
- **Kluczowe sprawdzenia:** Wykrycie ATEX, uwzględnienie strefy bezpieczeństwa

**Co zrobił system:**
- **Risk:** CRITICAL
- **Ostrzeżenia:** 2
- **Tagi:** 1
- **Clarification:** Which housing length do you need?
- **Policy warning:** Explosive atmospheres require all components to prevent ignition sources. Static charge on ungrounded filter housings can produce sparks exceeding the
- **Odpowiedź:** we have sized a  gdb  filter housing with dimensions  600x600mm  for your atex zone 22 application requiring  3400 m³/h  airflow. to finalize the configuration:

---

### 13. `sizing_large_airflow` — PASS

**Category:** sizing | **Time:** 9.9s

**Pytanie:**
> I need a GDB housing for 10000 m³/h airflow. Maximum width cannot exceed 1300mm. Standard Galvanized (FZ).

**Co powinno być (PDF):**
- **Decyzja:** MULTI-MODULE
- **Dlaczego:** 10,000 m³/h przy max 1300mm szerokości. GDB 600x600 = 3400 m³/h na moduł. Potrzeba ~3 modułów. 2×600 = 1200mm mieści się w 1300mm. System powinien obliczyć arrangement: np. 2 kolumny × 2 rzędy lub similar.
- **Kluczowe sprawdzenia:** compute_sizing_arrangement, multi-module info, wymiary w odpowiedzi

**Co zrobił system:**
- **Tagi:** 1
- **Clarification:** Which housing length is required?
- **Odpowiedź:** we have configured a gdb housing with 900x1200mm dimensions for your required airflow of 10000 m³/h, and standard galvanized steel (fz) material. to finalize the configuration, i need to know the housing length. which housing length is required?

---

### 14. `sizing_single_module_600x600` — PASS

**Category:** sizing | **Time:** 17.2s

**Pytanie:**
> I need a GDB housing, size 600x600, Galvanized FZ, airflow 3400 m³/h.

**Co powinno być (PDF):**
- **Decyzja:** SINGLE MODULE
- **Dlaczego:** 600x600 to standardowy moduł 1/1. Airflow 3400 m³/h pasuje do jednego modułu. System powinien dopasować bezpośrednio i zapytać o housing length.
- **Kluczowe sprawdzenia:** Bezpośrednie dopasowanie, clarification na housing length

**Co zrobił system:**
- **Tagi:** 1
- **Clarification:** Which housing length is required?
- **Odpowiedź:** we have a gdb housing with 600x600mm dimensions and 3400 m³/h airflow in fz material. to finalize the configuration, i need to know the housing length:

---

### 15. `sizing_dimension_mapping` — PASS

**Category:** sizing | **Time:** 9.6s

**Pytanie:**
> I need a GDB housing for a Nanoclass Deeppleat H13 filter, size 305x610x150 mm, in Stainless Steel (RF).

**Co powinno być (PDF):**
- **Decyzja:** DIMENSION MAP
- **Dlaczego:** Filtr 305x610 → housing 300x600 (standardowe zaokrąglenie). System powinien rozpoznać wymiary filtra i zmapować na housing.
- **Kluczowe sprawdzenia:** Dimension mapping 305→300, 610→600, rozpoznanie jako 300x600

**Co zrobił system:**
- **Tagi:** 1
- **Clarification:** What is the required airflow (m³/h)?
- **Odpowiedź:** we have configured a gdb housing in stainless steel (rf) to accommodate a 305x610x150 mm nanoclass deeppleat h13 filter. to finalize the configuration, i need to know the required airflow capacity.

---

### 16. `sizing_multi_tag` — PASS

**Category:** sizing | **Time:** 10.5s

**Pytanie:**
> I need a quote for the Nouryon project. We have two tags:
> Tag 5684: Nanoclass Deeppleat H13 - size 305x610x150 mm, SS frame, 25mm header.
> Tag 7889: Nanoclass Deeppleat E11 - size 610x610x292 mm, SS frame, 25mm header.
> Please recommend the correct GDB housings in Stainless Steel (RF) for both.

**Co powinno być (PDF):**
- **Decyzja:** MULTI-TAG
- **Dlaczego:** Dwa tagi z różnymi wymiarami: 305x610 (→300x600, ref ~1700 m³/h) i 610x610 (→600x600, ref ~3400 m³/h). System MUSI traktować je osobno z różnymi referencjami airflow.
- **Kluczowe sprawdzenia:** Dwa tagi, różne wymiary, per-tag airflow reference

**Co zrobił system:**
- **Tagi:** 2
- **Clarification:** Please provide the airflow (m³/h) for each tag.
- **Odpowiedź:** for the nouryon project, i have configured the gdb housings based on the provided filter dimensions. to finalize the recommendations, i need the airflow requirements for each tag: what is the required airflow (m³/h)?

---

### 17. `sizing_space_constraint` — PASS

**Category:** sizing | **Time:** 10.7s

**Pytanie:**
> I need a GDB-600x600 housing. We have a vertical shaft that is exactly 650mm wide. The housing is 600mm, so it fits physically with 25mm margin on each side. Is this a correct installation?

**Co powinno być (PDF):**
- **Decyzja:** CLEARANCE WARNING
- **Dlaczego:** Szyb 650mm, housing 600mm = 50mm margines (25mm/stronę). Za mało na serwis filtrów. System powinien ostrzec o niewystarczającym clearance.
- **Kluczowe sprawdzenia:** Ostrzeżenie o service clearance, maintenance access

**Co zrobił system:**
- **Risk:** CRITICAL
- **Ostrzeżenia:** 1
- **Tagi:** 1
- **Product card:** Tak
- **Product cards:** 1
- **Odpowiedź:** the gdb-600x600 housing you selected has a width of 600mm. however, due to the design with a side-hinged service door, it requires a total service clearance of 1200mm for maintenance access. your available space of 650mm is insufficient for safe operation. a suitable alternative is the  pff planfilterram . this option requires only frontal access for filter changes, fitting within your 650mm space constraint.

---

### 18. `material_chlorine_fz_block` — PASS

**Category:** material | **Time:** 13.2s

**Pytanie:**
> We need GDB filter housings for a water treatment plant with chlorine levels around 60ppm. Material: Galvanized (FZ). Size 600x600.

**Co powinno być (PDF):**
- **Decyzja:** BLOCK (material)
- **Dlaczego:** 60ppm chloru, FZ max ~25ppm. Materiał nie wytrzyma. System powinien zablokować FZ i zasugerować RF.
- **Kluczowe sprawdzenia:** Wykrycie chloru, blokada FZ, sugestia RF

**Co zrobił system:**
- **Risk:** CRITICAL
- **Wykryta aplikacja:** Swimming Pool
- **Ostrzeżenia:** 4
- **Tagi:** 2
- **Product card:** Tak
- **Product cards:** 2
- **Odpowiedź:** the gdb filter housings in fz material are not suitable for the water treatment plant due to the chlorine exposure. the zinc coating (c3) dissolves in chlorinated environments within months. chlorine environments require a minimum of c5 corrosion resistance (stainless steel). i recommend upgrading to stainless steel (sf) to ensure longevity in this environment. here is the two-stage filtration system using stainless steel components:

---

### 19. `material_rf_hospital_ok` — FAIL

**Category:** material | **Time:** 13.4s

**Pytanie:**
> We need GDMI housings for hospital ventilation in Stainless Steel (RF). Size 600x600, airflow 3400 m³/h.

**Co powinno być (PDF):**
- **Decyzja:** PASS (material OK)
- **Dlaczego:** GDMI + RF w szpitalu: RF jest odporny na chlor, GDMI spełnia wymogi szpitalne. Materiał NIE powinien być blokowany. System powinien normalnie kontynuować.
- **Kluczowe sprawdzenia:** Brak blokady materiału, normalna konfiguracja

**Co zrobił system:**
- **Risk:** CRITICAL
- **Wykryta aplikacja:** Hospital
- **Ostrzeżenia:** 2
- **Tagi:** 1
- **Policy warning:** Product not rated for ENV_HOSPITAL installation (allowed: ENV_INDOOR, ENV_OUTDOOR, ENV_ATEX). This product uses BOLTED construction which does not mee
- **Policy warning:** MATERIAL NOT AVAILABLE: RF is NOT available for GDMI. Available materials: Zinkmagnesium.
- **Odpowiedź:** **important:** rf (stainless steel) is **not available** for gdmi. available material options: zinkmagnesium. please select an available material to proceed. for the hospital ventilation project, the gdmi housing is a good fit for the 600x600mm dimension and 3400 m³/h airflow requirement. however, standard gdmi housings are not rated for hospital environments due to their bolted construction, which doesn't meet hygiene requirements. additionally, while you requested stainless steel (rf), this ma

**FAILED Assertions:**
- `proceeds_normally`: Expected at least one of [response.clarification_needed|response.product_card] to exist

**Graph dependency:** Material(RF).chlorine_resistance_ppm > hospital level

---

### 20. `positive_office_gdb_fz` — PASS

**Category:** positive | **Time:** 10.7s

**Pytanie:**
> I need a GDB housing for an office building ventilation system. Size 600x600, standard Galvanized (FZ), airflow 3400 m³/h.

**Co powinno być (PDF):**
- **Decyzja:** CLEAN PASS
- **Dlaczego:** Biuro = środowisko łagodne, brak stressorów. GDB standardowy, FZ domyślny materiał. System powinien zapytać o housing length i zaproponować produkt.
- **Kluczowe sprawdzenia:** Brak blokad, clarification lub product card

**Co zrobił system:**
- **Wykryta aplikacja:** Office/Commercial
- **Tagi:** 1
- **Clarification:** Which housing length do you need?
- **Odpowiedź:** for the office building ventilation system, we have a gdb housing with dimensions 600x600mm and material fz. to finalize the configuration, i need to know the housing length. which housing length is required?

---

### 21. `positive_warehouse_gdb_fz` — PASS

**Category:** positive | **Time:** 9.7s

**Pytanie:**
> We need GDB filter housings for a warehouse ventilation system. Standard indoor installation. 600x600, FZ galvanized, airflow 3400 m³/h.

**Co powinno być (PDF):**
- **Decyzja:** CLEAN PASS
- **Dlaczego:** Magazyn = indoor industrial, łagodne środowisko. GDB standardowy. System powinien przejść normalnie.
- **Kluczowe sprawdzenia:** Brak blokad, normalna konfiguracja

**Co zrobił system:**
- **Tagi:** 1
- **Clarification:** Which housing length is required?
- **Odpowiedź:** we have a gdb filter housing sized for 600x600mm ducts and 3400 m³/h airflow for your warehouse ventilation system. to finalize the configuration, i need to know the housing length:

---

### 22. `positive_gdp_basic` — PASS

**Category:** positive | **Time:** 10.3s

**Pytanie:**
> I need a GDP flat filter housing for an office building supply air system. Size 600x600, FZ material.

**Co powinno być (PDF):**
- **Decyzja:** CLEAN PASS
- **Dlaczego:** GDP = najprostszy housing na flat filters. Biuro = łagodne środowisko. System powinien rozpoznać GDP i normalnie kontynuować.
- **Kluczowe sprawdzenia:** Rozpoznanie GDP, brak blokad

**Co zrobił system:**
- **Wykryta aplikacja:** Office/Commercial
- **Tagi:** 1
- **Clarification:** What is the required airflow (m³/h)?
- **Odpowiedź:** for the office building supply air system, i have a gdp flat filter housing in size 600x600mm with fz material selected. to finalize the configuration, i need the required airflow capacity. 

---

### 23. `clarif_no_product` — PASS

**Category:** clarif | **Time:** 9.1s

**Pytanie:**
> I need a ventilation filter housing for a commercial building. The duct size is 600x600mm and airflow is 3400 m³/h.

**Co powinno być (PDF):**
- **Decyzja:** RECOMMEND
- **Dlaczego:** User nie podał produktu. System powinien zaproponować na podstawie kontekstu (commercial building → GDB jako domyślny) lub zapytać.
- **Kluczowe sprawdzenia:** Rekomendacja produktu lub pytanie o typ

**Co zrobił system:**
- **Tagi:** 1
- **Clarification:** What is the filter depth?
- **Odpowiedź:** i understand you need a ventilation filter housing for a commercial building with duct size 600x600mm and airflow 3400 m³/h. to finalize the configuration, i need to know the filter depth.

---

### 24. `clarif_no_airflow` — PASS

**Category:** clarif | **Time:** 8.3s

**Pytanie:**
> I need a GDB housing, size 600x600, Galvanized (FZ). What housing length do I need?

**Co powinno być (PDF):**
- **Decyzja:** ASK AIRFLOW
- **Dlaczego:** Produkt i wymiary podane, ale brak airflow. System MUSI zapytać o airflow (potrzebny do housing length i sizing).
- **Kluczowe sprawdzenia:** Clarification pytająca o airflow m³/h

**Co zrobił system:**
- **Tagi:** 1
- **Policy warning:** Response was truncated due to length limits.
- **Odpowiedź:** for the gdb housing (600x600mm, galvanized fz), i need two more details to finalize the configuration: what is the required airflow capacity (m³/h)? which housing length do you need?

---

### 25. `clarif_no_dimensions` — PASS

**Category:** clarif | **Time:** 11.0s

**Pytanie:**
> I need a GDB housing for 3400 m³/h airflow, Galvanized FZ material.

**Co powinno być (PDF):**
- **Decyzja:** ASK DIMENSIONS
- **Dlaczego:** Produkt i airflow podane, ale brak wymiarów. System powinien zapytać o wymiary (duct size lub filter size).
- **Kluczowe sprawdzenia:** Clarification pytająca o wymiary

**Co zrobił system:**
- **Tagi:** 1
- **Clarification:** Which housing length is required?
- **Odpowiedź:** we will configure a gdb housing with dimensions 600x600mm for an airflow of 3400 m³/h and fz (galvanized) material. to finalize the configuration, we need the housing length:

---

### 26. `edge_pharma_cleanroom` — PASS

**Category:** env | **Time:** 8.9s

**Pytanie:**
> We need filter housings for a pharmaceutical cleanroom with ISO Class 7 requirements. The system handles supply air for a sterile production area.

**Co powinno być (PDF):**
- **Decyzja:** STRICT HYGIENE
- **Dlaczego:** Pharma cleanroom = najwyższe wymagania higieniczne. VDI 6022 compliance. Potrzebny GDMI-RF lub lepszy. System powinien rozpoznać i sugerować odpowiedni produkt.
- **Kluczowe sprawdzenia:** Wykrycie pharma/cleanroom, sugestia GDMI/RF/hygiene

**Co zrobił system:**
- **Wykryta aplikacja:** Laboratory
- **Clarification:** Please provide the airflow capacity and duct dimensions.
- **Odpowiedź:** for the pharmaceutical cleanroom application, i need two details to configure the filter housing: what is the required airflow capacity (m³/h)? what are the duct connection dimensions (width x height)?

---

### 27. `edge_dual_concern` — FAIL

**Category:** env | **Time:** 12.6s

**Pytanie:**
> We have a rooftop commercial kitchen exhaust installation. The housing will be outdoors on the roof above the kitchen. We want GDC-FLEX carbon housing in RF, 600x600.

**Co powinno być (PDF):**
- **Decyzja:** DOUBLE STRESSOR
- **Dlaczego:** Kuchnia outdoor = DWA stressory jednocześnie: tłuszcz (grease) + kondensacja (outdoor). Carbon housing na dachu = potrzeba ZARÓWNO protectora (GDP) JAK i izolacji. System powinien rozpoznać oba problemy.
- **Kluczowe sprawdzenia:** Wykrycie obu stressorów, podwójne ostrzeżenie

**Co zrobił system:**
- **Risk:** CRITICAL
- **Wykryta aplikacja:** Commercial Kitchen
- **Ostrzeżenia:** 6
- **Tagi:** 2
- **Clarification:** Please provide these details.
- **Policy warning:** None
- **Odpowiedź:** for your commercial kitchen exhaust system, a two-stage filtration system is required. the gdc_flex family provides the necessary porous adsorption for chemical vapors, but requires upstream protection. the first stage will be a gdp planfilterskåp to provide mechanical pre-filtration. this is necessary because in kitchen environments, lipids permanently coat activated carbon pores via irreversible adsorption, deactivating the carbon. the second stage will be the gdc_flex unit. i need a few more 

**FAILED Assertions:**
- `outdoor_detected`: Expected any of [outdoor|rooftop|roof|condensation|insulation|weather] in 'for your commercial kitchen exhaust system, a two-stage filtration system is required. the gdc_flex '

**Graph dependency:** Multiple stressors: STRESSOR_GREASE_EXPOSURE + STRESSOR_OUTDOOR_CONDENSATION

---

### 28. `edge_pff_basic` — PASS

**Category:** positive | **Time:** 11.5s

**Pytanie:**
> I need a PFF filter frame for 600x600 duct in an office supply air system.

**Co powinno być (PDF):**
- **Decyzja:** CLEAN PASS
- **Dlaczego:** PFF = prosty frame na filtr. Biuro = łagodne. Powinien przejść bez problemów.
- **Kluczowe sprawdzenia:** Rozpoznanie PFF, brak blokad

**Co zrobił system:**
- **Wykryta aplikacja:** Office/Commercial
- **Ostrzeżenia:** 1
- **Tagi:** 1
- **Clarification:** What filter depth and airflow do you require?
- **Odpowiedź:** for the pff filter frame in your office supply air system, i need two more details to finalize the configuration. first, what is the filter depth you require? second, what is the airflow in m³/h?

---
