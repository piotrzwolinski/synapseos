#!/usr/bin/env python3
"""
Generate a comparison report: Question / Expected / Actual
Runs all tests and saves a markdown report file.

Usage:
    python generate_report.py                    # Run all, save to /tmp/test-report.md
    python generate_report.py --out report.md    # Custom output path
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime

import requests

# Re-use test infrastructure
sys.path.insert(0, os.path.dirname(__file__))
from run_tests import (
    TEST_CASES, TestResult, authenticate, call_streaming_endpoint,
    extract_test_data, check_assertion, BASE_URL, TIMEOUT
)

# ---------------------------------------------------------------------------
# Expected behavior descriptions (PDF ground truth)
# ---------------------------------------------------------------------------
EXPECTED = {
    "env_hospital_gdb_fz": {
        "decision": "BLOCK",
        "reason": (
            "GDB ma konstrukcję BOLTED — nie spełnia wymagań szczelności i higieny dla szpitala. "
            "Materiał FZ (galwanizowany) nie jest odporny na chlor (>50ppm w szpitalach). "
            "System powinien ZABLOKOWAĆ i zasugerować: GDMI (izolowany, spawane szwy) w materiale RF (stal nierdzewna)."
        ),
        "key_checks": "Wykrycie środowiska szpitalnego, blokada env whitelist, sugestia GDMI+RF",
    },
    "env_hospital_gdmi_rf": {
        "decision": "PASS",
        "reason": (
            "GDMI to jedyny housing rated dla szpitali — spawane szwy, izolacja, spełnia klasę szczelności. "
            "RF (stal nierdzewna) jest odporna na chlor. Powinien przejść BEZ blokady i zapytać o brakujące parametry (housing length)."
        ),
        "key_checks": "Brak blokady env whitelist, normalna konfiguracja, clarification na housing length",
    },
    "env_outdoor_gdb_fz": {
        "decision": "RISK → PIVOT",
        "reason": (
            "GDB nie ma izolacji termicznej. Instalacja outdoor = ryzyko kondensacji (rosa). "
            "System powinien ostrzec o KONDENSACJI i zasugerować GDMI (izolowany) jako alternatywę. "
            "Kluczowe: powód blokady to BRAK IZOLACJI, nie 'bolted construction'."
        ),
        "key_checks": "Wykrycie outdoor stressor, wspomnienie o kondensacji/izolacji, pivot do GDMI",
    },
    "env_outdoor_gdmi_fz": {
        "decision": "PASS",
        "reason": (
            "GDMI jest przeznaczony do instalacji outdoor — ma izolację termiczną. "
            "FZ jest akceptowalny outdoor (o ile nie ma salt spray). "
            "Powinien przejść normalnie, zapytać o housing length."
        ),
        "key_checks": "Brak blokady, normalna konfiguracja",
    },
    "env_marine_gdb_fz": {
        "decision": "BLOCK",
        "reason": (
            "Marine/offshore: solanka (salt spray) niszczy FZ galwanizowany. "
            "Dodatkowo outdoor = potrzeba izolacji. GDB nie ma izolacji, FZ nie odporny na sól. "
            "Powinien zablokować i sugerować GDMI-RF."
        ),
        "key_checks": "Wykrycie marine/salt stressor, blokada materiału, sugestia RF + GDMI",
    },
    "env_swimming_pool": {
        "decision": "BLOCK (material)",
        "reason": (
            "Basen = wysokie stężenie chloru (~60ppm). FZ galwanizowany wytrzymuje max ~25ppm. "
            "Powinien zablokować materiał FZ i zasugerować RF (stal nierdzewna)."
        ),
        "key_checks": "Wykrycie chloru, blokada materiału FZ, sugestia RF",
    },
    "env_kitchen_gdb_fz": {
        "decision": "WARN",
        "reason": (
            "Kuchnia = tłuszcz (grease stressor). GDB ma filtrację mechaniczną — łapie cząstki tłuszczu. "
            "GDB sam w sobie jest OK jako pre-filtr, ale system powinien wspomnieć o greasy/kitchen context. "
            "NIE wymaga assembly (bo GDB nie ma adsorpcji węglowej)."
        ),
        "key_checks": "Wykrycie kuchni/tłuszczu, brak assembly trigger (bo GDB nie carbon)",
    },
    "assembly_kitchen_gdc_flex_rf": {
        "decision": "ASSEMBLY",
        "reason": (
            "GDC-FLEX to housing węglowy (carbon) z TRAIT_POROUS_ADSORPTION. "
            "W kuchni tłuszcz zatyka pory węgla (NEUTRALIZED_BY). "
            "System MUSI dodać GDP jako protector (pre-filtr mechaniczny) upstream. "
            "Wynik: dwustopniowy assembly GDP→GDC-FLEX."
        ),
        "key_checks": "Wykrycie kuchni, trigger assembly, GDP jako protector, two-stage",
    },
    "assembly_kitchen_gdc_rf": {
        "decision": "ASSEMBLY",
        "reason": (
            "GDC to też housing węglowy (cartridge carbon). Ta sama logika co GDC-FLEX. "
            "Tłuszcz w kuchni zatyka carbon cartridges. GDP protector wymagany upstream."
        ),
        "key_checks": "Wykrycie kuchni, assembly trigger, GDP protector",
    },
    "assembly_no_trigger_office_gdc": {
        "decision": "NO ASSEMBLY",
        "reason": (
            "GDC w biurze: carbon jest dla kontroli zapachów, nie ma tłuszczu. "
            "Brak grease stressor = brak NEUTRALIZATION veto = brak assembly. "
            "System powinien normalnie skonfigurować GDC."
        ),
        "key_checks": "Brak assembly, normalna konfiguracja GDC",
    },
    "atex_powder_coating": {
        "decision": "GATE (clarification)",
        "reason": (
            "Powder coating = combustible dust = ATEX classified atmosphere. "
            "System MUSI zapytać o strefę Ex (Zone 20/21/22 Dust) ZANIM zaproponuje produkt. "
            "LogicGate GATE_ATEX_ZONE powinien się aktywować."
        ),
        "key_checks": "ATEX gate trigger, clarification z pytaniem o strefę, NIE podaje produktu",
    },
    "atex_explicit_indoor": {
        "decision": "ATEX awareness",
        "reason": (
            "User wprost mówi 'ATEX Zone 22' — system powinien rozpoznać i uwzględnić. "
            "Nawet z podaną strefą, system powinien zwrócić uwagę na ATEX klasyfikację."
        ),
        "key_checks": "Wykrycie ATEX, uwzględnienie strefy bezpieczeństwa",
    },
    "sizing_large_airflow": {
        "decision": "MULTI-MODULE",
        "reason": (
            "10,000 m³/h przy max 1300mm szerokości. GDB 600x600 = 3400 m³/h na moduł. "
            "Potrzeba ~3 modułów. 2×600 = 1200mm mieści się w 1300mm. "
            "System powinien obliczyć arrangement: np. 2 kolumny × 2 rzędy lub similar."
        ),
        "key_checks": "compute_sizing_arrangement, multi-module info, wymiary w odpowiedzi",
    },
    "sizing_single_module_600x600": {
        "decision": "SINGLE MODULE",
        "reason": (
            "600x600 to standardowy moduł 1/1. Airflow 3400 m³/h pasuje do jednego modułu. "
            "System powinien dopasować bezpośrednio i zapytać o housing length."
        ),
        "key_checks": "Bezpośrednie dopasowanie, clarification na housing length",
    },
    "sizing_dimension_mapping": {
        "decision": "DIMENSION MAP",
        "reason": (
            "Filtr 305x610 → housing 300x600 (standardowe zaokrąglenie). "
            "System powinien rozpoznać wymiary filtra i zmapować na housing."
        ),
        "key_checks": "Dimension mapping 305→300, 610→600, rozpoznanie jako 300x600",
    },
    "sizing_multi_tag": {
        "decision": "MULTI-TAG",
        "reason": (
            "Dwa tagi z różnymi wymiarami: 305x610 (→300x600, ref ~1700 m³/h) "
            "i 610x610 (→600x600, ref ~3400 m³/h). "
            "System MUSI traktować je osobno z różnymi referencjami airflow."
        ),
        "key_checks": "Dwa tagi, różne wymiary, per-tag airflow reference",
    },
    "sizing_space_constraint": {
        "decision": "CLEARANCE WARNING",
        "reason": (
            "Szyb 650mm, housing 600mm = 50mm margines (25mm/stronę). "
            "Za mało na serwis filtrów. System powinien ostrzec o niewystarczającym clearance."
        ),
        "key_checks": "Ostrzeżenie o service clearance, maintenance access",
    },
    "material_chlorine_fz_block": {
        "decision": "BLOCK (material)",
        "reason": (
            "60ppm chloru, FZ max ~25ppm. Materiał nie wytrzyma. "
            "System powinien zablokować FZ i zasugerować RF."
        ),
        "key_checks": "Wykrycie chloru, blokada FZ, sugestia RF",
    },
    "material_rf_hospital_ok": {
        "decision": "PASS (material OK)",
        "reason": (
            "GDMI + RF w szpitalu: RF jest odporny na chlor, GDMI spełnia wymogi szpitalne. "
            "Materiał NIE powinien być blokowany. System powinien normalnie kontynuować."
        ),
        "key_checks": "Brak blokady materiału, normalna konfiguracja",
    },
    "positive_office_gdb_fz": {
        "decision": "CLEAN PASS",
        "reason": (
            "Biuro = środowisko łagodne, brak stressorów. GDB standardowy, FZ domyślny materiał. "
            "System powinien zapytać o housing length i zaproponować produkt."
        ),
        "key_checks": "Brak blokad, clarification lub product card",
    },
    "positive_warehouse_gdb_fz": {
        "decision": "CLEAN PASS",
        "reason": (
            "Magazyn = indoor industrial, łagodne środowisko. GDB standardowy. "
            "System powinien przejść normalnie."
        ),
        "key_checks": "Brak blokad, normalna konfiguracja",
    },
    "positive_gdp_basic": {
        "decision": "CLEAN PASS",
        "reason": (
            "GDP = najprostszy housing na flat filters. Biuro = łagodne środowisko. "
            "System powinien rozpoznać GDP i normalnie kontynuować."
        ),
        "key_checks": "Rozpoznanie GDP, brak blokad",
    },
    "clarif_no_product": {
        "decision": "RECOMMEND",
        "reason": (
            "User nie podał produktu. System powinien zaproponować na podstawie kontekstu "
            "(commercial building → GDB jako domyślny) lub zapytać."
        ),
        "key_checks": "Rekomendacja produktu lub pytanie o typ",
    },
    "clarif_no_airflow": {
        "decision": "ASK AIRFLOW",
        "reason": (
            "Produkt i wymiary podane, ale brak airflow. "
            "System MUSI zapytać o airflow (potrzebny do housing length i sizing)."
        ),
        "key_checks": "Clarification pytająca o airflow m³/h",
    },
    "clarif_no_dimensions": {
        "decision": "ASK DIMENSIONS",
        "reason": (
            "Produkt i airflow podane, ale brak wymiarów. "
            "System powinien zapytać o wymiary (duct size lub filter size)."
        ),
        "key_checks": "Clarification pytająca o wymiary",
    },
    "edge_pharma_cleanroom": {
        "decision": "STRICT HYGIENE",
        "reason": (
            "Pharma cleanroom = najwyższe wymagania higieniczne. VDI 6022 compliance. "
            "Potrzebny GDMI-RF lub lepszy. System powinien rozpoznać i sugerować odpowiedni produkt."
        ),
        "key_checks": "Wykrycie pharma/cleanroom, sugestia GDMI/RF/hygiene",
    },
    "edge_dual_concern": {
        "decision": "DOUBLE STRESSOR",
        "reason": (
            "Kuchnia outdoor = DWA stressory jednocześnie: tłuszcz (grease) + kondensacja (outdoor). "
            "Carbon housing na dachu = potrzeba ZARÓWNO protectora (GDP) JAK i izolacji. "
            "System powinien rozpoznać oba problemy."
        ),
        "key_checks": "Wykrycie obu stressorów, podwójne ostrzeżenie",
    },
    "edge_pff_basic": {
        "decision": "CLEAN PASS",
        "reason": (
            "PFF = prosty frame na filtr. Biuro = łagodne. Powinien przejść bez problemów."
        ),
        "key_checks": "Rozpoznanie PFF, brak blokad",
    },

    # ===================================================================
    #  CHATGPT-GENERATED — Sizing & data verification tests
    # ===================================================================

    "chatgpt_gdb_600x600_2500_ok": {
        "decision": "PASS (sizing OK)",
        "reason": (
            "GDB 600x600 ma capacity 3400 m³/h. 2500 < 3400 → mieści się. "
            "System powinien normalnie kontynuować (zapytać o housing length)."
        ),
        "key_checks": "Brak ostrzeżeń o undersized, normalna konfiguracja",
    },
    "chatgpt_gdb_600x600_3800_undersized": {
        "decision": "UNDERSIZED",
        "reason": (
            "GDB 600x600 = 3400 m³/h < 3800 m³/h. Niedowymiarowane. "
            "Sugestia: 600x900 (5100 m³/h)."
        ),
        "key_checks": "Wykrycie przekroczenia capacity, sugestia większego rozmiaru",
    },
    "chatgpt_gdb_15000_height_constraint": {
        "decision": "SIZE SELECTION",
        "reason": (
            "15000 m³/h przy height ≤ 1500mm. GDB 1800x900 = 15300 m³/h, Höjd=900mm. "
            "Inne opcje: 1500x1200 (17000, h=1200), 1200x1500 (17000, h=1500)."
        ),
        "key_checks": "Dobór rozmiaru spełniającego oba constrainty",
    },
    "chatgpt_gdb_1500x1200_16000_ok": {
        "decision": "PASS (sizing OK)",
        "reason": (
            "GDB 1500x1200 = 17000 m³/h ≥ 16000. Mieści się."
        ),
        "key_checks": "Brak ostrzeżeń o undersized",
    },
    "chatgpt_gdcflex_600x600_3000_undersized": {
        "decision": "UNDERSIZED",
        "reason": (
            "GDC-FLEX 600x600 = 1750 m³/h < 3000. 900x600=2500 też za mało. "
            "Sugestia: 1200x600 (3500 m³/h)."
        ),
        "key_checks": "Wykrycie undersized, przeskoczenie 900x600, sugestia 1200x600",
    },
    "chatgpt_gdcflex_900x600_2500_ok": {
        "decision": "PASS (sizing OK)",
        "reason": "GDC-FLEX 900x600 = 2500 m³/h. Dokładne dopasowanie.",
        "key_checks": "Brak ostrzeżeń, normalna konfiguracja",
    },
    "chatgpt_gdc_600x600_2000_ok": {
        "decision": "PASS (sizing OK)",
        "reason": "GDC 600x600 = 2000 m³/h. Dokładne dopasowanie.",
        "key_checks": "Brak ostrzeżeń, normalna konfiguracja",
    },
    "chatgpt_gdc_600x600_2800_undersized": {
        "decision": "UNDERSIZED",
        "reason": (
            "GDC 600x600 = 2000 m³/h < 2800. "
            "Sugestia: 900x600 (3000 m³/h)."
        ),
        "key_checks": "Wykrycie undersized, sugestia 900x600",
    },
    "chatgpt_gdmi_600x600_3400_ok": {
        "decision": "PASS (sizing OK)",
        "reason": "GDMI 600x600 = 3400 m³/h. Dokładne dopasowanie.",
        "key_checks": "Brak ostrzeżeń, normalna konfiguracja",
    },
    "chatgpt_gdmi_600x600_4000_undersized": {
        "decision": "UNDERSIZED",
        "reason": (
            "GDMI 600x600 = 3400 m³/h < 4000. "
            "Sugestia: 600x900 (5100 m³/h)."
        ),
        "key_checks": "Wykrycie undersized, sugestia 600x900",
    },
    "chatgpt_gdcflex_rf_available": {
        "decision": "PASS (material OK)",
        "reason": (
            "GDC-FLEX jest dostępny w RF (stal nierdzewna). "
            "Katalog pokazuje 5 ikon materiałów: FZ, AZ, RF, SF, ZM."
        ),
        "key_checks": "Brak blokady materiału RF, normalna konfiguracja",
    },
    "chatgpt_insulated_c5_gdmi_zm": {
        "decision": "RECOMMEND GDMI-ZM",
        "reason": (
            "Izolacja + C5 = GDMI w ZM. GDMI jedyny izolowany housing. "
            "ZM = C5 corrosion class. RF/SF niedostępne dla GDMI."
        ),
        "key_checks": "Rekomendacja GDMI, materiał ZM, wspomnienie C5",
    },
    "chatgpt_gdb_300x600_1800_undersized": {
        "decision": "UNDERSIZED",
        "reason": (
            "GDB 300x600 = 1700 m³/h < 1800. 600x300=1700 też za mało. "
            "Sugestia: 600x600 (3400 m³/h)."
        ),
        "key_checks": "Wykrycie undersized, sugestia 600x600",
    },
    "chatgpt_gdb_1200x900_10000_ok": {
        "decision": "PASS (sizing OK)",
        "reason": "GDB 1200x900 = 10200 m³/h ≥ 10000.",
        "key_checks": "Brak ostrzeżeń, normalna konfiguracja",
    },
    "chatgpt_gdcflex_600x600_cartridges": {
        "decision": "DATA CHECK",
        "reason": "GDC-FLEX 600x600 ma 14 patronów (Antal patroner=14).",
        "key_checks": "Odpowiedź zawiera informację o 14 patronach",
    },
    "chatgpt_gdc_600x600_cartridges": {
        "decision": "DATA CHECK",
        "reason": "GDC 600x600 ma 16 patronów (Antal patroner=16).",
        "key_checks": "Odpowiedź zawiera informację o 16 patronach",
    },
    "chatgpt_gdmi_1800x1200_20000_ok": {
        "decision": "PASS (sizing OK)",
        "reason": "GDMI 1800x1200 = 20400 m³/h ≥ 20000.",
        "key_checks": "Brak ostrzeżeń, normalna konfiguracja",
    },
    "chatgpt_gdb_900x900_7000_ok": {
        "decision": "PASS (sizing OK)",
        "reason": "GDB 900x900 = 7650 m³/h ≥ 7000.",
        "key_checks": "Brak ostrzeżeń, normalna konfiguracja",
    },
    "chatgpt_gdmi_rf_not_available": {
        "decision": "MATERIAL BLOCK",
        "reason": (
            "GDMI nie jest dostępny w RF (stal nierdzewna). "
            "Katalog: 'Ej i Rostfritt'. Dostępne: AZ, ZM."
        ),
        "key_checks": "Wykrycie niedostępności RF dla GDMI, sugestia ZM",
    },
    "chatgpt_gdb_length_750_for_long_bags": {
        "decision": "LENGTH GUIDANCE",
        "reason": (
            "Filtr 635mm depth wymaga housing length 750/800mm. "
            "550/600 tylko dla krótkich worków (max 450mm)."
        ),
        "key_checks": "Sugestia 750/800mm length, wzmianka o głębokości filtra",
    },

    # ===================================================================
    #  CHATGPT-GENERATED — Environment & Material tests
    # ===================================================================

    "chatgpt_env_hospital_gdb_fz": {
        "decision": "BLOCK (Engineering)",
        "reason": (
            "GDB FZ w szpitalu: bolted construction + FZ(C3) nie spełnia wymagań higienicznych. "
            "Pivot do GDMI-ZM (izolowany, C5)."
        ),
        "key_checks": "Wykrycie niezgodności środowiskowej, sugestia GDMI-ZM",
    },
    "chatgpt_env_hospital_gdmi_rf": {
        "decision": "BLOCK (Availability)",
        "reason": (
            "GDMI nie jest dostępny w RF. Katalog: 'Ei i Rostfritt'. "
            "Sugestia: GDMI-ZM."
        ),
        "key_checks": "Wykrycie niedostępności RF dla GDMI, sugestia ZM",
    },
    "chatgpt_env_outdoor_gdb_fz": {
        "decision": "WARN / PIVOT",
        "reason": (
            "GDB FZ na dachu: brak izolacji → kondensacja. "
            "Wszystkie produkty 'för inomhusbruk'. Sugestia: GDMI-ZM."
        ),
        "key_checks": "Ostrzeżenie o kondensacji, sugestia izolowanego GDMI-ZM",
    },
    "chatgpt_env_outdoor_gdmi_zm": {
        "decision": "PASS",
        "reason": (
            "GDMI ZM na dachu: izolowany + C5. Najlepsza opcja outdoor."
        ),
        "key_checks": "Brak blokady, potwierdzenie izolacji, zapytanie o housing length",
    },
    "chatgpt_env_marine_gdb_fz": {
        "decision": "BLOCK (Material)",
        "reason": (
            "GDB FZ offshore: FZ=C3, marine wymaga C5. "
            "Sugestia: GDB-RF (C5) lub GDB-SF (C5.1)."
        ),
        "key_checks": "BLOCK materiałowy, sugestia RF/SF",
    },
    "chatgpt_env_marine_gdmi_rf": {
        "decision": "BLOCK (Availability)",
        "reason": (
            "GDMI RF offshore: RF niedostępne. Sugestia: GDMI-ZM (C5). "
            "Izolacja już wbudowana."
        ),
        "key_checks": "BLOCK dostępności, sugestia GDMI-ZM, wzmianka o izolacji",
    },
    "chatgpt_env_pool_gdb_fz": {
        "decision": "BLOCK (Material)",
        "reason": (
            "GDB FZ basen: chlor + wilgoć niszczą FZ(C3). "
            "Sugestia: GDB-RF (C5) lub GDB-SF (C5.1)."
        ),
        "key_checks": "Wykrycie chloru, BLOCK dla FZ, sugestia stainless",
    },
    "chatgpt_env_kitchen_gdcflex_rf": {
        "decision": "ASSEMBLY + UNDERSIZED",
        "reason": (
            "Kuchnia → tłuszcz → GDP upstream. GDC-FLEX 600x600=1750 m³/h < 2000. "
            "RF dostępne. Potrzeba większego rozmiaru lub 2 modułów."
        ),
        "key_checks": "GDP assembly, wykrycie undersized (1750<2000)",
    },
    "chatgpt_env_office_gdc_fz": {
        "decision": "PASS",
        "reason": "GDC FZ w biurze: łagodne środowisko, carbon na zapachy. Brak blokad.",
        "key_checks": "Brak blokad, zapytanie o housing length",
    },
    "chatgpt_env_atex22_gdb_fz": {
        "decision": "WARN (ATEX)",
        "reason": (
            "GDB FZ w ATEX Zone 22: uziemienie + filtry antystatyczne. "
            "Brak certyfikacji Ex w katalogu."
        ),
        "key_checks": "ATEX awareness, wzmianka o groundingu",
    },
    "chatgpt_env_atex21_gdcflex": {
        "decision": "BLOCK (Engineering)",
        "reason": (
            "GDC-FLEX w ATEX Zone 21: standardowy housing bez certyfikacji Ex. "
            "Wymagana zewnętrzna ekspertyza. GDC-FLEX 600x600=1750 m³/h."
        ),
        "key_checks": "BLOCK dla Zone 21, brak certyfikacji",
    },
    "chatgpt_env_wastewater_h2s_fz": {
        "decision": "BLOCK (Material)",
        "reason": (
            "GDB FZ przy H2S: siarkowodór ekstremalnie korozyjny. FZ=C3 niedostateczne. "
            "Sugestia: RF (C5) lub SF (C5.1)."
        ),
        "key_checks": "BLOCK dla H2S+FZ, sugestia stainless",
    },
    "chatgpt_env_cement_gdc": {
        "decision": "ASSEMBLY",
        "reason": (
            "GDC w cementowni: ciężki pył zablokuje carbon. "
            "Wymagany GDP upstream jako pre-filtr."
        ),
        "key_checks": "Assembly z GDP, wzmianka o zapychaniu carbona",
    },
    "chatgpt_env_airport_gdcflex_rf": {
        "decision": "PASS / CHECK CAPACITY",
        "reason": (
            "GDC-FLEX 900x600 RF: 2500 m³/h exact match. RF dostępne. "
            "Brak założeń o salt spray. Carbon na VOC odpowiedni."
        ),
        "key_checks": "Weryfikacja capacity, brak fałszywych założeń",
    },
    "chatgpt_env_datacenter_gdmi_rf": {
        "decision": "BLOCK (Availability)",
        "reason": (
            "GDMI RF: niedostępne. 'Ei i Rostfritt'. "
            "Sugestia: GDMI-ZM. ZM=C5 (równoważny RF w klasie korozji)."
        ),
        "key_checks": "BLOCK dostępności, sugestia ZM, wzmianka o C5",
    },
    "chatgpt_env_pool_gdc_fz": {
        "decision": "BLOCK (Material)",
        "reason": (
            "GDC FZ w basenie: chlor niszczy FZ(C3). "
            "Sugestia: GDC-RF (C5) lub GDC-SF (C5.1)."
        ),
        "key_checks": "BLOCK chlor+FZ, sugestia stainless dla GDC",
    },
    "chatgpt_env_museum_gdmi_zm": {
        "decision": "PASS",
        "reason": (
            "GDMI ZM w archiwum muzeum: 70% RH umiarkowane. "
            "ZM(C5) wystarczające. Brak dramatycznych ostrzeżeń."
        ),
        "key_checks": "PASS, brak blokad, zapytanie o airflow i housing length",
    },
    "chatgpt_env_rooftop_cold_gdmi_zm": {
        "decision": "PASS",
        "reason": (
            "GDMI ZM na dachu -25°C: GDMI już izolowany ('värme- och kondensisolerat'). "
            "ZM=C5. Nie mówić 'insulation required' — już jest."
        ),
        "key_checks": "PASS, potwierdzenie izolacji, brak redundantnych ostrzeżeń",
    },
    "chatgpt_env_marine_atex22_gdb_fz": {
        "decision": "BLOCK (Material)",
        "reason": (
            "GDB FZ offshore ATEX22: FZ=C3 < C5 (marine). "
            "Grounding wymagany. Sugestia: RF/SF."
        ),
        "key_checks": "BLOCK materiał, grounding, sugestia RF/SF",
    },
    "chatgpt_env_hospital_atex22_gdmi_zm": {
        "decision": "PASS with WARN",
        "reason": (
            "GDMI ZM w lab szpitalnym ATEX22: ZM dostępne. "
            "Hygiene OK. ATEX grounding wymagany."
        ),
        "key_checks": "PASS, ATEX grounding warn, brak blokady materiału",
    },

    # ===================================================================
    #  CHATGPT-GENERATED — Production-Grade Tricky Scenarios
    # ===================================================================

    "chatgpt_prod_hospital_gdb_fz_pivot": {
        "decision": "PIVOT to GDMI-ZM",
        "reason": (
            "GDB FZ w szpitalu: bolted industrial housing nie nadaje się do sterylnych ward. "
            "Pivot do GDMI 600x600 ZM (izolowany, C5). Housing length: 600 lub 850mm."
        ),
        "key_checks": "Wykrycie niezgodności bolted+hospital, pivot do GDMI-ZM, pytanie o housing length",
    },
    "chatgpt_prod_hospital_gdmi_rf_block": {
        "decision": "BLOCK (Availability)",
        "reason": (
            "GDMI RF niedostępny. Katalog: 'Ei i Rostfritt'. Tylko AZ i ZM. "
            "Sugestia: GDMI 600x600 ZM dla szpitala."
        ),
        "key_checks": "BLOCK dostępności RF w GDMI, sugestia ZM",
    },
    "chatgpt_prod_rooftop_gdb_fz_condensation": {
        "decision": "WARN / PIVOT",
        "reason": (
            "GDB FZ na dachu outdoor: brak izolacji → kondensacja. "
            "Wszystkie produkty 'för inomhusbruk'. Pivot do GDMI ZM (izolowany)."
        ),
        "key_checks": "Ostrzeżenie outdoor/kondensacja, sugestia GDMI insulated",
    },
    "chatgpt_prod_offshore_gdb_fz_c5m": {
        "decision": "BLOCK (Material)",
        "reason": (
            "GDB FZ offshore: FZ=C3 vs marine C5-M. Za słabe. "
            "Sugestia: RF (C5) lub SF (C5.1). Housing length 550/750mm."
        ),
        "key_checks": "BLOCK FZ na morzu, sugestia RF/SF, wzmianka C5",
    },
    "chatgpt_prod_kitchen_gdcflex_grease": {
        "decision": "ASSEMBLY + UNDERSIZED",
        "reason": (
            "Kuchnia → tłuszcz blokuje pory carbona → GDP upstream. "
            "GDC-FLEX 600x600 = 1750 m³/h < 1800 → undersized. "
            "Potrzeba: GDP pre-filter + upsizing GDC-FLEX."
        ),
        "key_checks": "GDP assembly dla tłuszczu, undersized 1750<1800, sugestia upsizing",
    },
    "chatgpt_prod_cement_gdc_no_prefilter": {
        "decision": "BLOCK (Engineering)",
        "reason": (
            "GDC w cementowni bez pre-filtra: pył cementowy zatknie pory carbona. "
            "Wymagany GDP upstream. Dwustopniowa konfiguracja."
        ),
        "key_checks": "Wykrycie zagrożenia pyłem, wymaganie GDP pre-filter upstream",
    },
    "chatgpt_prod_atex21_gdcflex_block": {
        "decision": "BLOCK (ATEX)",
        "reason": (
            "ATEX Zone 21 = atmosfera wybuchowa prawdopodobna podczas normalnej pracy. "
            "Standardowe housings bez certyfikacji Ex. Konfiguracja nie może być zatwierdzona."
        ),
        "key_checks": "BLOCK ATEX Zone 21, brak certyfikacji Ex, wymagana ekspertyza",
    },
    "chatgpt_prod_flour_atex22_gdb_15000": {
        "decision": "SIZE + ATEX WARN",
        "reason": (
            "GDB 1800x900 = 15300 m³/h, Höjd=900mm (≤1500mm OK). "
            "ATEX Zone 22: grounding + filtry antystatyczne. FZ OK w suchym środowisku."
        ),
        "key_checks": "Dobór 1800x900, ATEX grounding, housing length 550/750mm",
    },
    "chatgpt_prod_museum_85rh_carbon": {
        "decision": "WARN (Physics)",
        "reason": (
            "85% RH drastycznie redukuje adsorpcję carbon. "
            "Para wodna konkuruje o miejsca adsorpcji z VOC. "
            "Zalecenia: osuszanie powietrza, podgrzewanie, zwiększenie złoża."
        ),
        "key_checks": "Ostrzeżenie humidity vs carbon, sugestie mitygacji",
    },
    "chatgpt_prod_oversized_gdc_low_velocity": {
        "decision": "WARN (Physics)",
        "reason": (
            "GDC 1800x1200 @ 800 m³/h: ekstremalne przewymiarowanie. "
            "Za niska prędkość czołowa → nierównomierny rozkład → channeling. "
            "Zalecenie: mniejszy housing bliżej nominalnego przepływu."
        ),
        "key_checks": "Ostrzeżenie oversizing, channeling risk, sugestia mniejszego rozmiaru",
    },

    # ===================================================================
    #  CHATGPT-GENERATED — Hardcore / Golden Manifest V2
    # ===================================================================

    "hc_gdmi_sf_trap": {
        "decision": "BLOCK (Material)",
        "reason": (
            "GDMI nie jest dostępne w SF (ani RF). Katalog: 'Ej i Rostfritt'. "
            "Tylko AZ i ZM. Pivot: GDB-SF + izolacja on-site."
        ),
        "key_checks": "BLOCK materiał SF/RF w GDMI, sugestia GDB-SF lub ZM",
    },
    "hc_gdcflex_rf_available": {
        "decision": "PASS (RF available)",
        "reason": (
            "GDC-FLEX dostępne we wszystkich 5 materiałach: FZ/AZ/RF/SF/ZM. "
            "RF jest dostępne. Pytanie o housing length 750/900mm."
        ),
        "key_checks": "PASS konfiguracji, RF dostępne, pytanie o housing length",
    },
    "hc_gdb_length_900_block": {
        "decision": "BLOCK (Geometry)",
        "reason": (
            "GDB housing lengths: 550 i 750mm. 900mm nie istnieje. "
            "Sugestia: 750mm lub pivot do GDC (750/900mm)."
        ),
        "key_checks": "BLOCK 900mm dla GDB, sugestia 750mm lub innego produktu",
    },
    "hc_greenhouse_95rh_carbon": {
        "decision": "CRITICAL WARNING (Physics)",
        "reason": (
            "GDC przy 95% RH: drastycznie obniżona adsorpcja. "
            "Para wodna konkuruje o miejsca aktywne w carbonie. "
            "Wymagane osuszanie lub specjalne media."
        ),
        "key_checks": "Ostrzeżenie humidity vs carbon, sugestie mitygacji",
    },
    "hc_kitchen_grease_killer": {
        "decision": "ASSEMBLY (GDP upstream)",
        "reason": (
            "Kuchnia → tłuszcz (lipidy) blokuje pory carbona nieodwracalnie. "
            "GDP pre-filter obowiązkowy upstream. "
            "GDC 600x600 FZ: 2550 m³/h >= 1600 → airflow OK."
        ),
        "key_checks": "Assembly GDP+GDC, grease risk, capacity check",
    },
    "hc_shared_duct_grease_trap": {
        "decision": "WARNING (Pre-filter needed)",
        "reason": (
            "Biuro na wspólnym kanale ze stacją smażenia → ryzyko tłuszczu. "
            "GDP pre-filter zalecany mimo że główna aplikacja biurowa."
        ),
        "key_checks": "Wykrycie ryzyka tłuszczu z kanału, sugestia pre-filtra",
    },
    "hc_formaldehyde_lab": {
        "decision": "WARNING (Chemistry)",
        "reason": (
            "Formaldehyd (HCHO) ma niską masę cząsteczkową → słaba adsorpcja na standardowym carbonie. "
            "Wymagane media impregnowane lub specjalistyczne."
        ),
        "key_checks": "Ostrzeżenie o słabej adsorpcji formaldehyde, sugestia specjalnych mediów",
    },
    "hc_shaft_service_access": {
        "decision": "WARNING (Service access)",
        "reason": (
            "GDMI 600x600 mieści się (600mm < 650mm szer. szybu), ale drzwi serwisowe "
            "wymagają +140mm → 740mm > 650mm. Brak dostępu serwisowego."
        ),
        "key_checks": "Ostrzeżenie o dostępie serwisowym, +140mm clearance",
    },
    "hc_flex_contact_time_failure": {
        "decision": "BLOCK (Capacity)",
        "reason": (
            "GDC-FLEX 600x600 = 1750 m³/h. Wymagane 3500 m³/h = 200% pojemności. "
            "Potrzeba 2 modułów lub większy housing."
        ),
        "key_checks": "BLOCK pojemności, 3500>>1750, sugestia 2 modułów lub upsizing",
    },
    "hc_tight_maintenance_shaft": {
        "decision": "WARNING (Clearance)",
        "reason": (
            "Szyb 650mm, GDMI 600mm: delta tylko 50mm. "
            "Brak miejsca na drzwi serwisowe (+140mm). Serwis niemożliwy."
        ),
        "key_checks": "Ostrzeżenie o braku miejsca serwisowego, 50mm < 140mm",
    },
    "hc_atex21_powder_booth": {
        "decision": "BLOCK (ATEX)",
        "reason": (
            "ATEX Zone 21 = atmosfera wybuchowa prawdopodobna podczas normalnej pracy. "
            "Standardowe housings bez certyfikacji Ex. Nie można zatwierdzić."
        ),
        "key_checks": "BLOCK Zone 21, brak Ex, wymagana specjalistyczna ocena",
    },
    "hc_hospital_leakage_class": {
        "decision": "BLOCK (Construction)",
        "reason": (
            "GDB = bolted construction → wyższe ryzyko nieszczelności. "
            "Szpital sterylny wymaga welded/GDMI. Pivot do GDMI-ZM."
        ),
        "key_checks": "BLOCK bolted w szpitalu, pivot GDMI-ZM, hygiene concern",
    },
    "hc_wastewater_h2s_fz": {
        "decision": "BLOCK (Material)",
        "reason": (
            "H2S (siarkowodór) atakuje cynk w FZ → korozja przyspieszona. "
            "FZ=C3 niewystarczające. Sugestia: SF (C5.1) lub RF (C5)."
        ),
        "key_checks": "BLOCK FZ w H2S, sugestia SF/RF, korozja chemiczna",
    },
    "hc_aluminium_dust_atex22": {
        "decision": "WARNING (ATEX)",
        "reason": (
            "Pył aluminium ATEX Zone 22: grounding wszystkich metalowych komponentów. "
            "Filtry antystatyczne z elementami przewodzącymi. "
            "GDB 1200x600 FZ: 5150 m³/h >= 5000."
        ),
        "key_checks": "ATEX grounding, anti-static, capacity check",
    },
    "hc_arctic_condensation": {
        "decision": "BLOCK (Insulation)",
        "reason": (
            "GDB brak izolacji → kondensacja przy -30°C. "
            "Katalog: 'för inomhusbruk'. Pivot do GDMI (izolowany)."
        ),
        "key_checks": "BLOCK brak izolacji, kondensacja, pivot GDMI",
    },
    "hc_cruise_ship_gdc_oversized": {
        "decision": "BLOCK (Capacity)",
        "reason": (
            "GDC 600x600 = 2550 m³/h. Wymagane: 2600. "
            "Marginalnie undersized. Sugestia: upsize do 900x600 (3050 m³/h)."
        ),
        "key_checks": "BLOCK undersized 2550<2600, sugestia upsizing",
    },
    "hc_lcc_four_small_housings": {
        "decision": "WARNING (Oversizing / LCC)",
        "reason": (
            "4× GDB 300x300 = 4× 440 m³/h (łącznie 1760 m³/h) dla 1500. "
            "Nadmiarowa złożoność. Zalecenie: jeden GDB 600x600 (2550 m³/h)."
        ),
        "key_checks": "Ostrzeżenie oversizing/złożoność, sugestia uproszczenia",
    },
    "hc_short_bag_geometry_error": {
        "decision": "BLOCK (Geometry)",
        "reason": (
            "GDB 550mm housing → max filter depth 450mm. "
            "Filtr workowy 600mm > 450mm max. Potrzeba housing 750mm."
        ),
        "key_checks": "BLOCK głębokość filtra vs housing, sugestia 750mm",
    },
    "hc_marine_gdmi_sf_pivot": {
        "decision": "BLOCK (Material)",
        "reason": (
            "GDMI-FLEX nie jest dostępne w SF. Katalog: 'Ej i rostfritt'. "
            "Tylko FZ/AZ/ZM. Pivot: GDC-FLEX SF (5 materiałów) lub GDB-SF + izolacja."
        ),
        "key_checks": "BLOCK SF w GDMI-FLEX, sugestia GDC-FLEX SF lub GDB-SF",
    },
    "hc_stressor_cascade_boss": {
        "decision": "MULTI-BLOCK",
        "reason": (
            "5 stressorów jednocześnie: capacity (15000>2550), brak izolacji (outdoor), "
            "hygiene (szpital), marine (C5-M), grease (kuchnia). "
            "System musi wykryć i zaadresować każdy stressor."
        ),
        "key_checks": "Wielokrotny BLOCK: capacity, insulation, hygiene, marine, grease",
    },
}


def extract_actual_summary(events: list) -> dict:
    """Extract the actual system behavior from raw SSE events."""
    data = extract_test_data(events)
    resp = data.get("response", {})
    gr = data.get("graph_report", {})
    ts = data.get("technical_state", {})

    content_text = resp.get("content_text", "")
    # Truncate for readability but keep enough for context
    if len(content_text) > 600:
        content_text = content_text[:600] + "..."

    clar_needed = resp.get("clarification_needed", False)
    clar = resp.get("clarification", {})
    clar_question = ""
    if clar and isinstance(clar, dict):
        clar_question = clar.get("question", "")
        if not clar_question:
            opts = clar.get("options", [])
            if opts:
                clar_question = "Options: " + ", ".join(
                    o.get("label", str(o)) if isinstance(o, dict) else str(o)
                    for o in opts[:4]
                )

    risk = resp.get("risk_severity")
    risk_detected = resp.get("risk_detected", False)

    product_card = resp.get("product_card")
    product_cards = resp.get("product_cards", [])
    warnings = resp.get("policy_warnings", [])

    return {
        "content_text": content_text,
        "clarification_needed": clar_needed,
        "clarification_question": clar_question,
        "risk_detected": risk_detected,
        "risk_severity": risk,
        "has_product_card": product_card is not None,
        "product_cards_count": len(product_cards) if product_cards else 0,
        "warnings": warnings,
        "application": gr.get("application"),
        "warnings_count": gr.get("warnings_count", 0),
        "tags_count": gr.get("tags_count", 0),
    }


def main():
    args = sys.argv[1:]
    out_path = "/tmp/test-report.md"
    if "--out" in args:
        idx = args.index("--out")
        if idx + 1 < len(args):
            out_path = args[idx + 1]

    print(f"  Authenticating...", end=" ")
    token = authenticate()
    print("OK")

    lines = []
    lines.append(f"# SynapseOS HVAC — Test Report")
    lines.append(f"")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Endpoint: {BASE_URL}/consult/deep-explainable/stream")
    lines.append(f"Tests: {len(TEST_CASES)}")
    lines.append(f"")

    # Summary table
    lines.append(f"## Summary")
    lines.append(f"")
    lines.append(f"| # | Test | Category | Expected | Result |")
    lines.append(f"|---|------|----------|----------|--------|")

    all_results = []
    total_pass = 0
    total_fail = 0

    print(f"\n  Running {len(TEST_CASES)} tests...\n")

    for i, (name, test) in enumerate(TEST_CASES.items(), 1):
        session_id = f"report-{name}-{uuid.uuid4().hex[:6]}"

        # Clear session
        try:
            requests.delete(
                f"{BASE_URL}/session/{session_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5,
            )
        except Exception:
            pass

        start = time.time()
        events = call_streaming_endpoint(test.query, session_id, token)
        duration = time.time() - start

        # Run assertions
        data = extract_test_data(events)
        passed_all = True
        failed_assertions = []
        for assertion in test.assertions:
            checked = check_assertion(assertion, data)
            if not checked.passed:
                passed_all = False
                failed_assertions.append(checked)

        status = "PASS" if passed_all else "FAIL"
        if passed_all:
            total_pass += 1
        else:
            total_fail += 1

        expected_info = EXPECTED.get(name, {})
        expected_decision = expected_info.get("decision", "?")

        icon = "PASS" if passed_all else "FAIL"
        print(f"  {i:>2}. [{icon}] {name:<35} ({duration:.1f}s)")

        actual = extract_actual_summary(events)
        all_results.append({
            "name": name,
            "test": test,
            "expected_info": expected_info,
            "actual": actual,
            "passed": passed_all,
            "failed_assertions": failed_assertions,
            "duration": duration,
        })

        status_icon = "PASS" if passed_all else "**FAIL**"
        lines.append(f"| {i} | {name} | {test.category} | {expected_decision} | {status_icon} |")

    lines.append(f"")
    lines.append(f"**Total: {total_pass} passed, {total_fail} failed / {len(TEST_CASES)} tests**")
    lines.append(f"")

    # Detailed results
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## Detailed Results")
    lines.append(f"")

    for i, r in enumerate(all_results, 1):
        name = r["name"]
        test = r["test"]
        exp = r["expected_info"]
        actual = r["actual"]
        passed = r["passed"]

        status_label = "PASS" if passed else "FAIL"
        lines.append(f"### {i}. `{name}` — {status_label}")
        lines.append(f"")
        lines.append(f"**Category:** {test.category} | **Time:** {r['duration']:.1f}s")
        lines.append(f"")

        # Query
        query_text = test.query.replace("\n", "\n> ")
        lines.append(f"**Pytanie:**")
        lines.append(f"> {query_text}")
        lines.append(f"")

        # Expected
        lines.append(f"**Co powinno być (PDF):**")
        lines.append(f"- **Decyzja:** {exp.get('decision', '?')}")
        lines.append(f"- **Dlaczego:** {exp.get('reason', '?')}")
        lines.append(f"- **Kluczowe sprawdzenia:** {exp.get('key_checks', '?')}")
        lines.append(f"")

        # Actual
        lines.append(f"**Co zrobił system:**")

        if actual["risk_detected"]:
            lines.append(f"- **Risk:** {actual['risk_severity']}")
        if actual["application"]:
            lines.append(f"- **Wykryta aplikacja:** {actual['application']}")
        if actual["warnings_count"]:
            lines.append(f"- **Ostrzeżenia:** {actual['warnings_count']}")
        if actual["tags_count"]:
            lines.append(f"- **Tagi:** {actual['tags_count']}")
        if actual["clarification_needed"]:
            lines.append(f"- **Clarification:** {actual['clarification_question'][:200]}")
        if actual["has_product_card"]:
            lines.append(f"- **Product card:** Tak")
        if actual["product_cards_count"]:
            lines.append(f"- **Product cards:** {actual['product_cards_count']}")
        if actual["warnings"]:
            for w in actual["warnings"][:3]:
                lines.append(f"- **Policy warning:** {str(w)[:150]}")

        lines.append(f"- **Odpowiedź:** {actual['content_text'][:500]}")
        lines.append(f"")

        # Verdict
        if not passed:
            lines.append(f"**FAILED Assertions:**")
            for a in r["failed_assertions"]:
                lines.append(f"- `{a.name}`: {a.message}")
            lines.append(f"")
            # Graph dependency
            if test.tests_graph_node:
                lines.append(f"**Graph dependency:** {test.tests_graph_node}")
                lines.append(f"")

        lines.append(f"---")
        lines.append(f"")

    # Write file
    report = "\n".join(lines)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n  Report saved to: {out_path}")
    print(f"  {total_pass} passed, {total_fail} failed / {len(TEST_CASES)} tests")


if __name__ == "__main__":
    main()
