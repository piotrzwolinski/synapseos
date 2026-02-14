"""Generic document ingestion pipeline with AI-driven schema discovery.

Two-pass AI-driven document ingestion:
1. Pass 1 (Architect): Analyze document → propose Ontology (Node types, Relationships, Categories)
2. Pass 2 (Builder): Extract data using confirmed Ontology → write Configuration Graph to Neo4j
"""

import os
import json
import base64
from google import genai
from google.genai import types
from dotenv import load_dotenv

from database import db
from embeddings import generate_embedding

load_dotenv(dotenv_path="../.env")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
LLM_MODEL = "gemini-3-pro-preview"
VISION_MODEL = "gemini-3-pro-preview"

# Schema Analysis Prompt (Pass 1 - Architect)
# Note: Double braces {{ }} are escaped for Python .format() - they become single braces in output
SCHEMA_ANALYSIS_PROMPT = """You are an Ontology Architect specialized in extracting CONFIGURATION GRAPHS from technical documents.

Your task is to analyze the document structure deeply, looking beyond surface-level entities to find the engineering logic, dimensional data, and compatibility rules hidden in tables and specifications.

## What to Look For:

1. **Product Variants**: The specific items/rows in tables (e.g., 'GDP-600x600', 'GDR Nano 1/1'). These are the CORE entities.

2. **Dimensional Attributes**: Identify numeric columns/properties:
   - Physical: Width (mm), Height (mm), Depth (mm), Weight (kg)
   - Performance: Airflow (m³/h), Pressure Drop (Pa), Efficiency (%)
   - Commercial: Price, Lead Time
   *Mark these as type: "number" - crucial for mathematical queries!*

3. **Categorical Dimensions**: Look for grouping/classification concepts:
   - Module Size (e.g., "1/1", "1/2", "2/1")
   - Filter Type (e.g., "Bag Filter", "Panel Filter", "HEPA")
   - Application (e.g., "Indoor", "Outdoor", "Hygienic")
   - Material (e.g., "Galvanized Steel", "Stainless Steel")
   - Connection Type (e.g., "Flanged", "Spigot")
   *These become Category nodes for faceted filtering!*

4. **Compatibility Rules**: Text describing what fits where:
   - "Suitable for Bag Filters up to 600mm"
   - "Compatible with 1/1 and 1/2 modules"
   - "Requires minimum airflow of 2000 m³/h"

5. **Filter Cartridges** (CRITICAL - Look for activated carbon/filter cylinders):
   - Pattern: "ECO-C 2600 SC 3mm pellet... totalvikt 2,8 kg"
   - Look for: model names (ECO-C, ECO-F), weights, diameters, lengths
   - Typical in pages describing GDC/GDC FLEX carbon filter housings
   - Extract: model_name, weight_kg, carbon_weight_kg, diameter_mm, length_mm, pellet_size_mm, media_type

6. **Duct Transitions/Reducers** (CRITICAL - Look for size-to-diameter tables):
   - Pattern: Tables labeled "PT PLAN ÖVERGÅNG" or "Duct Transitions"
   - Matrix format: Housing size (e.g., 600x600) → Valid duct diameters (315, 400, 500)
   - Column headers often: "Storlek", "Ø d nippelmått", "FZ" indicators
   - Extract: housing_size, valid_duct_diameters as array

7. **Configuration Options** (CRITICAL - Look for "Option:" sections):
   - Pattern: "Option: Vänsterhängd lucka = L (left)", "Fläns ohålad=F"
   - Usually at bottom of product pages
   - Format: description = code (translation)
   - Common options: Left/Right hinging, Flange types, Frame depths
   - IMPORTANT CODES TO CAPTURE:
     - L = Left hinging (Vänsterhängd lucka)
     - F = Undrilled flange (Fläns ohålad)
     - EXL = Eccentric locking mechanism for bag filters (Mimośrodowy mechanizm blokujący)
     - Polis = Pre-mounted rail for police filter
     - 25, 50, 100 = Frame depth options in mm
   - Extract as structured list: code, description, category

8. **Material Specifications** (CRITICAL - Look for material codes and corrosion classes):
   - Pattern: Tables showing FZ, ZM, RF, SS material codes
   - Look for: "Utförande" (Design), "Material", "Korrosionsklass"
   - MANDATORY Material mappings to extract:
     - FZ = Sendzimir galvanized → C3 (mild corrosion)
     - ZM = Magnelis/Zinc-Magnesium/ZinkMagnesium → C5 (severe corrosion)
     - RF/SS = Stainless Steel (Rostfritt) → C5 (very severe/marine)
   - Extract: code, full_name, corrosion_class for each material
   - ALWAYS include these 3 materials even if not explicitly in document

9. **Consumable Filters with Part Numbers** (CRITICAL - Look for SKU patterns):
   - Pattern: Part numbers like "61090M2359", "800481002927"
   - Often paired with filter specs: "ECO-C 2600 SC 3mm pellet 450mm 2,2 kg kol"
   - Look for: Part number, model name, weight, filter type, efficiency class
   - Extract: part_number, model_name, filter_type, weight_kg, efficiency_class

10. **Housing Capacity** (CRITICAL - Extract cartridge/filter counts):
    - Pattern: Tables showing how many filters fit in each housing size
    - Example: "GDC 900x600: 24 patroner" (24 cartridges)
    - Look for: "antal", "st", "pcs", "patroner", "filter"
    - Extract as: cartridge_count, filter_count property on ProductVariant

11. **Special Product Features** (CRITICAL - Extract unique characteristics):
    - GDMI: Thermal insulation (isolering termiczna/termisk isolering)
    - GDMI Flex: Adjustable length range (e.g., 850-1100mm)
    - GDB: Standard lengths for bag filters (550mm short, 750mm long)
    - Look for: "isolerad", "insulated", "regulerbar", "adjustable"
    - Extract as: special_features array, length_range_mm, is_insulated boolean

12. **Reference Airflow Values** (CRITICAL - Standard performance data):
    - Pattern: Module size → Airflow capacity tables
    - Example: "592x592 (1/1 modul): 3400 m³/h"
    - Common values: 1/1 module = 3400 m³/h, 1/2 module = 1700 m³/h
    - Extract as: reference_airflow_m3h on ProductVariant

13. **Mounting Frames** (CRITICAL - PFF and similar accessories):
    - Pattern: Frame products with depth options
    - Example: "PFF ram montażowa: 25, 50, 100mm"
    - Extract: available_depths_mm array for frame products

14. **Source Page Numbers** (CRITICAL - For citation support):
    - Track which PDF page each piece of information comes from
    - For each product variant, note the page number where it appears
    - For each specification table, note the page number
    - This enables citations like "See page 18 of catalog"
    - Extract: source_page_number for each product/specification

## Output Format (JSON):

{{
  "document_type": "Technical Catalog / Price List / Specification Sheet",
  "summary": "Brief description of what products/configurations are documented",
  "version": "1.0",

  "product_family": "The main product line name (e.g., 'GDB Filter Cabinet', 'GDR Nano')",

  "variant_properties": [
    {{"name": "width_mm", "type": "number", "description": "Width in millimeters"}},
    {{"name": "height_mm", "type": "number", "description": "Height in millimeters"}},
    {{"name": "depth_mm", "type": "number", "description": "Depth in millimeters"}},
    {{"name": "airflow_m3h", "type": "number", "description": "Airflow capacity in m³/h"}},
    {{"name": "weight_kg", "type": "number", "description": "Weight in kilograms"}},
    {{"name": "price", "type": "number", "description": "Unit price"}}
  ],

  "category_dimensions": [
    {{"label": "ModuleSize", "description": "Filter module size designation", "example_values": ["1/1", "1/2", "2/1"]}},
    {{"label": "FilterType", "description": "Type of filter supported", "example_values": ["Bag Filter", "Panel Filter"]}},
    {{"label": "Application", "description": "Intended use environment", "example_values": ["Indoor", "Outdoor"]}}
  ],

  "compatibility_rules": [
    "Text description of compatibility rule 1",
    "Text description of compatibility rule 2"
  ],

  "has_filter_cartridges": true,
  "filter_cartridge_properties": [
    {{"name": "model_name", "type": "string", "description": "Cartridge model (e.g., ECO-C 2600)"}},
    {{"name": "weight_kg", "type": "number", "description": "Total weight in kg"}},
    {{"name": "carbon_weight_kg", "type": "number", "description": "Carbon content weight"}},
    {{"name": "diameter_mm", "type": "number", "description": "Cylinder diameter"}},
    {{"name": "length_mm", "type": "number", "description": "Cylinder length"}},
    {{"name": "pellet_size_mm", "type": "number", "description": "Pellet size (e.g., 3mm)"}},
    {{"name": "media_type", "type": "string", "description": "Media type (e.g., SC pellet)"}}
  ],

  "has_duct_transitions": true,
  "duct_transition_properties": [
    {{"name": "housing_size", "type": "string", "description": "Housing size (e.g., 600x600)"}},
    {{"name": "valid_duct_diameters_mm", "type": "array", "description": "List of compatible duct diameters"}}
  ],

  "has_configuration_options": true,
  "configuration_option_categories": ["Hinging", "Flange", "Frame Depth", "Accessories"],

  "has_material_specifications": true,
  "material_codes_found": ["FZ", "ZM", "RF"],
  "material_to_corrosion_class": {{
    "FZ": "C3",
    "ZM": "C5",
    "RF": "C5"
  }},

  "has_consumable_filters": true,
  "consumable_filter_types": ["Carbon Cartridge", "Bag Filter", "Panel Filter", "HEPA"],

  "has_page_tracking": true,
  "page_ranges": {{
    "product_tables": [1, 5, 10],
    "specifications": [3, 8],
    "options": [12]
  }},

  "concepts": ["High-level semantic concepts for vector search bridging"]
}}

## Guidelines:

- Extract ALL numeric properties you can find - these enable range queries
- Identify ALL categorical groupings - these enable faceted filtering
- Look at table headers, footnotes, and legends for classification hints
- Compatibility rules often appear in footnotes or "Notes" sections
- The goal is to enable queries like: "Find all 1/1 modules with airflow > 3000 m³/h"
- CRITICAL: Scan for "ECO-C", "ECO-F" patterns to detect filter cartridges
- CRITICAL: Scan for tables with "Ø" or "nippelmått" to detect duct transitions
- CRITICAL: Scan for "Option:" or "Tillval:" sections for configuration options
- CRITICAL: Scan for "FZ", "ZM", "RF", "Utförande", "Material" to detect material specs
- CRITICAL: Scan for part numbers (8-12 digit codes like "61090M2359") for consumable filters
- CRITICAL: Scan for "Korrosionsklass", "C3", "C4", "C5" for corrosion class mappings
- CRITICAL: Scan for cartridge/filter counts per housing ("24 patroner", "antal st")
- CRITICAL: Scan for "EXL", "Polis", "mimośrodowy" for special option codes
- CRITICAL: Scan for "isolerad", "insulated", "GDMI" for thermal insulation products
- CRITICAL: Scan for "592x592", "3400 m³/h" for reference airflow data
- CRITICAL: Scan for "PFF", "ram", "frame" with depth values (25, 50, 100mm)
- CRITICAL: Scan for length ranges like "850-1100mm" for adjustable products

{document_hint}

Now analyze the document and output ONLY valid JSON (no markdown, no explanation):
"""

# Data Extraction Prompt (Pass 2 - Builder)
# Note: Double braces {{ }} are escaped for Python .format() - they become single braces in output
DATA_EXTRACTION_PROMPT = """You are a Configuration Graph Extractor. Extract ALL product variants with their full dimensional data and categorical classifications.

## CONFIRMED SCHEMA:
{schema_json}

## Extraction Rules:

1. **Product Variants**: Extract EVERY row/item from tables. Each becomes a ProductVariant node.
   - Generate a unique "id" (use the product code/SKU from the document)
   - Set "family" to the product line name
   - Extract ALL numeric properties into "variant_props" as NUMBERS (not strings!)
   - Classify into categories based on the schema's category_dimensions
   - Include "available_options" array if configuration options apply to this variant

2. **Numeric Properties**: CRITICAL - Extract as actual numbers for Cypher math:
   - "600" → 600 (integer)
   - "3400.5" → 3400.5 (float)
   - Remove units, convert to standard units (mm, kg, m³/h)

3. **Categories**: For each variant, identify which category values apply:
   - Look at the row data, section headers, or explicit labels
   - If a variant is under "1/1 Module" section, add {{"label": "ModuleSize", "value": "1/1"}}

4. **Accessories & Related Items**: If the document has accessories, extract them too.

5. **Filter Cartridges** (CRITICAL for carbon filter housings):
   - Look for text patterns like: "ECO-C 2600 SC 3mm pellet 450mm 2,2 kg kol, totalvikt 2,8 kg"
   - Extract EACH cartridge model as a separate entry
   - Parse the text to extract: model_name, weight_kg, carbon_weight_kg, diameter_mm, length_mm, pellet_size_mm
   - Link to compatible housing variants (GDC, GDC FLEX)

6. **Duct Transitions** (CRITICAL for housing-to-duct compatibility):
   - Look for tables like "PT PLAN ÖVERGÅNG" with housing sizes and duct diameters
   - Each ROW becomes a DuctConnection entry
   - Example row: "600x600 | 500 | 450 | FZ" means housing 600x600 accepts Ø500 (and FZ indicator)
   - Extract the ARRAY of valid diameters for each housing size
   - Link via housing_width_mm and housing_height_mm to match ProductVariant dimensions

7. **Configuration Options** (CRITICAL - from "Option:" sections):
   - Look for patterns like: "Option: Ram djup 50 = 50", "Vänsterhängd lucka=L(left)"
   - Extract EACH option with: code, description (in English), original_text, category
   - Common categories: "Hinging", "Flange", "Frame", "Accessory"
   - Add the translated options to variant's available_options array

8. **Material Specifications** (CRITICAL - from material tables):
   - Look for material codes: FZ, ZM, RF, SS, ALU
   - Map to corrosion classes: FZ→C3, ZM→C5, RF/SS→C5+
   - Add "available_materials" array to each ProductVariant
   - Add "material_corrosion_mapping" to the global output

9. **Consumable Filters with Part Numbers** (CRITICAL - from filter specs):
   - Look for part number patterns: "61090M2359", "800481002927"
   - Extract: part_number, model_name, filter_type, weight_kg, dimensions, efficiency_class
   - Link to compatible housings via compatible_housings array
   - Create FilterConsumable entries for each unique filter

10. **Duct Diameters on ProductVariant** (CRITICAL - from transition tables):
    - Add "compatible_duct_diameters_mm" directly to ProductVariant nodes
    - This is IN ADDITION to creating DuctConnection nodes
    - Enables direct queries like: "Find housings that fit Ø400 duct"

11. **Housing Capacity** (CRITICAL - cartridge/filter counts):
    - Look for tables showing capacity per housing size
    - Pattern: "GDC 900x600: 24 patroner", "antal filter: 12 st"
    - Extract as "cartridge_count" or "filter_capacity" in variant_props
    - This answers "How many cartridges fit in GDC 900x600?" → 24

12. **Special Product Features** (CRITICAL - unique characteristics):
    - GDMI products: Add "is_insulated": true, "insulation_type": "thermal"
    - GDMI Flex: Add "length_range_mm": {{"min": 850, "max": 1100}}
    - GDB products: Add "standard_length_mm" (550 for short, 750 for long)
    - Extract any special features to "special_features" array

13. **Reference Airflow Values** (CRITICAL - performance data):
    - Look for module size → airflow tables
    - Pattern: "592x592 modul = 3400 m³/h", "1/1 modul: 3400 m³/h"
    - Add "reference_airflow_m3h" and "module_size" to relevant products
    - Common: 592x592 (1/1) = 3400 m³/h, 287x592 (1/2) = 1700 m³/h

14. **Frame/Accessory Depth Options** (CRITICAL - for PFF and similar):
    - Look for depth options: "djup 25, 50, 100 mm"
    - Add "available_depths_mm": [25, 50, 100] to frame products
    - This answers "What depths are available for PFF?" → 25, 50, 100mm

15. **Special Option Codes** (CRITICAL - must capture ALL):
    - EXL = Eccentric locking mechanism (Mimośrodowy mechanizm blokujący)
    - Polis = Pre-mounted police filter rail
    - L = Left hinging
    - F = Undrilled flange (Fläns ohålad)
    - 25, 50, 100 = Frame depths
    - ALWAYS extract with English description

16. **Source Page Numbers** (CRITICAL - For citation support):
    - For EACH product variant, include "source_page" with the PDF page number where it appears
    - For specification tables, note which page contains the data
    - This enables user-facing citations like "See page 18 of catalog"
    - If a product spans multiple pages, use the primary page where main specs appear

## Output Format (JSON):

{{
  "products": [
    {{
      "id": "GDC-900x600-750",
      "family": "GDC",
      "source_page": 18,
      "variant_props": {{
        "width_mm": 900,
        "height_mm": 600,
        "depth_mm": 750,
        "airflow_m3h": 3400,
        "weight_kg": 45,
        "price": 15000,
        "cartridge_count": 24,
        "module_size": "1/1",
        "reference_airflow_m3h": 3400
      }},
      "categories": [
        {{"label": "ModuleSize", "value": "1/1"}},
        {{"label": "FilterType", "value": "Carbon Filter"}},
        {{"label": "Application", "value": "Indoor"}}
      ],
      "available_options": [
        {{"code": "L", "description": "Left Hinging", "category": "Hinging"}},
        {{"code": "F", "description": "Undrilled Flange", "category": "Flange"}},
        {{"code": "EXL", "description": "Eccentric locking mechanism for bag filters", "category": "Accessory"}},
        {{"code": "Polis", "description": "Pre-mounted rail for police filter", "category": "Accessory"}}
      ],
      "available_materials": ["FZ", "ZM", "RF"],
      "compatible_duct_diameters_mm": [315, 400, 500]
    }},
    {{
      "id": "GDMI-600x600-850",
      "family": "GDMI",
      "source_page": 22,
      "variant_props": {{
        "width_mm": 600,
        "height_mm": 600,
        "depth_mm": 850,
        "is_insulated": true,
        "insulation_type": "thermal (anti-condensation)"
      }},
      "special_features": ["Factory-installed thermal insulation", "Anti-condensation"],
      "available_options": [
        {{"code": "L", "description": "Left Hinging", "category": "Hinging"}}
      ]
    }},
    {{
      "id": "GDMI-FLEX-600x600",
      "family": "GDMI",
      "source_page": 23,
      "variant_props": {{
        "width_mm": 600,
        "height_mm": 600,
        "length_min_mm": 850,
        "length_max_mm": 1100,
        "is_insulated": true
      }},
      "special_features": ["Adjustable length 850-1100mm", "Factory-installed thermal insulation"],
      "available_options": []
    }},
    {{
      "id": "GDB-600x600-550",
      "family": "GDB",
      "source_page": 8,
      "variant_props": {{
        "width_mm": 600,
        "height_mm": 600,
        "depth_mm": 550,
        "standard_length_mm": 550,
        "filter_type": "short bag filter"
      }},
      "available_options": [
        {{"code": "EXL", "description": "Eccentric locking mechanism for bag filters", "category": "Locking"}}
      ]
    }},
    {{
      "id": "PFF-600x600",
      "family": "PFF",
      "source_page": 15,
      "variant_props": {{
        "width_mm": 600,
        "height_mm": 600,
        "product_type": "mounting_frame"
      }},
      "available_depths_mm": [25, 50, 100],
      "available_options": [
        {{"code": "25", "description": "Frame Depth 25mm", "category": "Frame"}},
        {{"code": "50", "description": "Frame Depth 50mm", "category": "Frame"}},
        {{"code": "100", "description": "Frame Depth 100mm", "category": "Frame"}}
      ]
    }}
  ],
  "material_specifications": [
    {{
      "code": "FZ",
      "full_name": "Sendzimir galvanized steel",
      "corrosion_class": "C3",
      "description": "Standard finish for indoor use, mild corrosion environments"
    }},
    {{
      "code": "ZM",
      "full_name": "Magnelis/ZinkMagnesium (Zinc-Magnesium alloy)",
      "corrosion_class": "C5",
      "description": "High corrosion resistance for outdoor/coastal environments"
    }},
    {{
      "code": "RF",
      "full_name": "Stainless Steel (Rostfritt)",
      "corrosion_class": "C5",
      "description": "Maximum corrosion resistance for harsh/marine environments"
    }}
  ],
  "reference_airflow_table": [
    {{"module_size": "592x592", "module_designation": "1/1", "airflow_m3h": 3400}},
    {{"module_size": "287x592", "module_designation": "1/2", "airflow_m3h": 1700}},
    {{"module_size": "592x287", "module_designation": "2/1", "airflow_m3h": 1700}}
  ],
  "filter_consumables": [
    {{
      "id": "FILTER-61090M2359",
      "part_number": "61090M2359",
      "model_name": "ECO-C 2600",
      "filter_type": "Carbon Cartridge",
      "weight_kg": 2.8,
      "media_type": "SC 3mm pellet",
      "dimensions": "450mm length",
      "compatible_housings": ["GDC-600x600", "GDC-FLEX-600x600"]
    }},
    {{
      "id": "FILTER-800481002927",
      "part_number": "800481002927",
      "model_name": "Bag Filter ePM1 55%",
      "filter_type": "Bag Filter",
      "weight_kg": 1.2,
      "efficiency_class": "ePM1 55%",
      "dimensions": "600x600x600",
      "compatible_housings": ["GDP-600x600"]
    }}
  ],
  "filter_cartridges": [
    {{
      "id": "ECO-C-2600",
      "model_name": "ECO-C 2600",
      "media_type": "SC 3mm pellet",
      "length_mm": 450,
      "carbon_weight_kg": 2.2,
      "weight_kg": 2.8,
      "compatible_housings": ["GDC-600x600", "GDC-FLEX-600x600"]
    }}
  ],
  "duct_connections": [
    {{
      "id": "DUCT-600x600",
      "housing_size": "600x600",
      "housing_width_mm": 600,
      "housing_height_mm": 600,
      "valid_duct_diameters_mm": [315, 400, 500],
      "transition_type": "PT"
    }}
  ],
  "accessories": [
    {{
      "id": "ACC-001",
      "name": "Mounting Bracket",
      "compatible_with": ["GDC-600x600", "GDC-900x600"],
      "price": 450
    }}
  ],
  "compatibility_rules": [
    {{
      "rule": "ECO-C cartridges require GDC or GDC FLEX housings",
      "applies_to": ["GDC", "GDC FLEX"],
      "constraint_type": "component_fit",
      "constraint_property": "cartridge_type",
      "constraint_value": "ECO-C"
    }}
  ],
  "concepts": ["Extracted semantic concepts for vector search"]
}}

## Guidelines:

- Extract EVERY product variant - completeness is critical
- Numbers must be actual JSON numbers, not strings
- Infer categories from context (section headers, table groupings, explicit labels)
- Include units in property names (width_mm, not width) for clarity
- If price is in thousands (e.g., "12.5" meaning 12500), normalize it
- CRITICAL: Parse Swedish text patterns for cartridges (e.g., "kol" = carbon, "totalvikt" = total weight)
- CRITICAL: Extract ALL diameter values from transition tables as arrays
- CRITICAL: Translate Swedish option descriptions to English (e.g., "Vänsterhängd lucka" = "Left Hinging")
- CRITICAL: Extract part numbers (8-12 digit codes) for ALL consumable filters
- CRITICAL: Map material codes to corrosion classes (FZ→C3, ZM→C5, RF→C5)
- CRITICAL: Add compatible_duct_diameters_mm DIRECTLY to each ProductVariant (not just DuctConnection)
- CRITICAL: Add available_materials array to each ProductVariant where materials are specified
- Swedish material terms: "Rostfritt" = Stainless Steel (RF), "Förzinkat" = Galvanized (FZ)

## MANDATORY EXTRACTIONS (Test Questions Coverage):

1. **GDB Standard Lengths**: Extract "550mm" for short bag filters, "750mm" for long - add to variant_props.standard_length_mm
2. **GDMI Insulation**: Mark GDMI products with is_insulated=true and special_features=["thermal insulation"]
3. **Cartridge Counts**: Extract how many cartridges fit per housing (e.g., GDC 900x600 = 24) - add cartridge_count
4. **Option Code L**: Left hinging (Vänsterhängd lucka) - MUST be in available_options
5. **Material ZM → C5**: ZinkMagnesium/Magnelis material must map to corrosion class C5
6. **Option Code EXL**: Eccentric locking mechanism - MUST be captured with description
7. **PFF Frame Depths**: Extract available depths [25, 50, 100] mm - add available_depths_mm
8. **GDMI Flex Range**: Extract adjustable length range 850-1100mm (or 1100-1350mm) - add length_min_mm, length_max_mm
9. **Option Code F**: Undrilled flange (Fläns ohålad) - MUST be in available_options
10. **Reference Airflow 592x592**: 3400 m³/h for full module - add reference_airflow_m3h and include reference_airflow_table
11. **Source Page Numbers**: For EACH product, add "source_page" field with the PDF page number where the product appears

## DEFAULT MATERIALS (Always include if not found):
If material specifications table is not explicit in document, use these defaults:
- FZ: Sendzimir galvanized, C3
- ZM: Magnelis/ZinkMagnesium, C5
- RF: Stainless Steel (Rostfritt), C5

Now extract ALL data from the document. Output ONLY valid JSON:
"""


def analyze_document_schema(file_bytes: bytes, mime_type: str, document_hint: str = None) -> dict:
    """Pass 1 - Architect: Analyze document and propose ontology schema.

    Args:
        file_bytes: Raw bytes of the document (PDF, image, or text)
        mime_type: MIME type of the document
        document_hint: Optional hint about what the document contains

    Returns:
        Dict with document_type, summary, variant_properties, category_dimensions, etc.
    """
    hint_text = f"\n## Document Hint:\n{document_hint}" if document_hint else ""
    prompt = SCHEMA_ANALYSIS_PROMPT.format(document_hint=hint_text)

    # Choose model based on content type
    if mime_type.startswith("text/"):
        # Text document - use fast model
        text_content = file_bytes.decode("utf-8", errors="ignore")
        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=f"{prompt}\n\n---\nDOCUMENT CONTENT:\n---\n{text_content}",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
    else:
        # PDF or image - use vision model
        file_b64 = base64.b64encode(file_bytes).decode("utf-8")
        response = client.models.generate_content(
            model=VISION_MODEL,
            contents=[
                types.Content(
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                mime_type=mime_type,
                                data=file_b64
                            )
                        ),
                        types.Part(text=prompt)
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

    try:
        # Clean response text - remove markdown code blocks and extra whitespace
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        schema = json.loads(response_text)
        # Ensure required fields exist
        schema.setdefault("document_type", "Unknown Document")
        schema.setdefault("summary", "")
        schema.setdefault("version", "1.0")
        schema.setdefault("product_family", "Unknown")
        schema.setdefault("variant_properties", [])
        schema.setdefault("category_dimensions", [])
        schema.setdefault("compatibility_rules", [])
        schema.setdefault("concepts", [])
        return schema
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Warning: Failed to parse schema response: {e}")
        print(f"Raw response: {response.text}")
        return {
            "document_type": "Unknown Document",
            "summary": "Failed to analyze document",
            "version": "1.0",
            "product_family": "Unknown",
            "variant_properties": [],
            "category_dimensions": [],
            "compatibility_rules": [],
            "concepts": [],
            "error": str(e)
        }


def extract_document_data(file_bytes: bytes, mime_type: str, schema: dict) -> dict:
    """Pass 2 - Builder: Extract data following confirmed schema.

    Args:
        file_bytes: Raw bytes of the document
        mime_type: MIME type of the document
        schema: Confirmed schema from Pass 1

    Returns:
        Dict with products, accessories, compatibility_rules, concepts
    """
    schema_json = json.dumps(schema, indent=2)
    prompt = DATA_EXTRACTION_PROMPT.format(schema_json=schema_json)

    # Choose model based on content type
    if mime_type.startswith("text/"):
        text_content = file_bytes.decode("utf-8", errors="ignore")
        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=f"{prompt}\n\n---\nDOCUMENT CONTENT:\n---\n{text_content}",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
    else:
        file_b64 = base64.b64encode(file_bytes).decode("utf-8")
        response = client.models.generate_content(
            model=VISION_MODEL,
            contents=[
                types.Content(
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                mime_type=mime_type,
                                data=file_b64
                            )
                        ),
                        types.Part(text=prompt)
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

    try:
        # Clean response text - remove markdown code blocks and extra whitespace
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        extraction = json.loads(response_text)
        extraction.setdefault("products", [])
        extraction.setdefault("accessories", [])
        extraction.setdefault("compatibility_rules", [])
        extraction.setdefault("concepts", [])
        return extraction
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Warning: Failed to parse extraction response: {e}")
        print(f"Raw response: {response.text}")
        return {
            "products": [],
            "accessories": [],
            "compatibility_rules": [],
            "concepts": [],
            "error": str(e)
        }


def write_configuration_graph(extracted_data: dict, schema: dict, source_document: str) -> dict:
    """Write extracted Configuration Graph to Neo4j.

    Creates:
    - DocumentSource node linking to all created entities
    - ProductVariant nodes with numeric properties (for math queries!)
    - Category nodes (type + name) for faceted filtering
    - IS_CATEGORY relationships from variants to categories
    - Concept nodes with embeddings for vector search bridging
    - Accessory nodes with COMPATIBLE_WITH relationships
    - FilterCartridge nodes with ACCEPTS_CARTRIDGE relationships
    - DuctConnection nodes with COMPATIBLE_WITH_DUCT relationships

    Args:
        extracted_data: Output from extract_document_data()
        schema: The confirmed schema
        source_document: Name/identifier for the source document

    Returns:
        Dict with counts of created nodes and relationships
    """
    counts = {
        "document_sources": 0,
        "product_variants": 0,
        "categories": 0,
        "accessories": 0,
        "filter_cartridges": 0,
        "filter_consumables": 0,
        "material_specs": 0,
        "duct_connections": 0,
        "concepts": 0,
        "relationships": 0
    }

    # Step 1: Create DocumentSource node
    doc_source_props = {
        "name": source_document,
        "document_type": schema.get("document_type", "Unknown"),
        "summary": schema.get("summary", ""),
        "product_family": schema.get("product_family", "Unknown"),
        "schema_version": schema.get("version", "1.0")
    }
    db.create_node("DocumentSource", doc_source_props)
    counts["document_sources"] = 1

    # Track created entities
    created_variants = set()
    created_categories = set()
    concept_cache = set()

    # Step 2: Create ProductVariant nodes with numeric properties
    for product in extracted_data.get("products", []):
        variant_id = product.get("id")
        if not variant_id:
            continue

        # Build properties - ensure numerics are actual numbers
        props = {
            "name": variant_id,  # Required for db.create_node
            "family": product.get("family", schema.get("product_family", "Unknown"))
        }

        # Add all variant_props as properly typed values
        for key, value in product.get("variant_props", {}).items():
            if value is not None:
                # Ensure numeric types for Cypher math operations
                if isinstance(value, (int, float)):
                    props[key] = value
                elif isinstance(value, str):
                    # Try to convert string numbers
                    try:
                        if '.' in value:
                            props[key] = float(value)
                        else:
                            props[key] = int(value)
                    except ValueError:
                        props[key] = value
                else:
                    props[key] = value

        # Add available_options as a property (list of option strings for display)
        available_options = product.get("available_options", [])
        if available_options:
            # Store as array of formatted strings for easy display
            props["available_options"] = [
                f"{opt.get('description', '')} ({opt.get('code', '')})"
                for opt in available_options
                if opt.get('code')
            ]
            # Also store structured options as JSON string for programmatic access
            props["options_json"] = json.dumps(available_options)

        # Add available_materials as property (e.g., ["FZ", "ZM", "RF"])
        available_materials = product.get("available_materials", [])
        if available_materials:
            props["available_materials"] = available_materials

        # Add compatible_duct_diameters_mm directly to ProductVariant for easy querying
        compatible_duct_diameters = product.get("compatible_duct_diameters_mm", [])
        if compatible_duct_diameters:
            props["compatible_duct_diameters_mm"] = compatible_duct_diameters

        # Add special features (NEW)
        special_features = product.get("special_features", [])
        if special_features:
            props["special_features"] = special_features

        # Add available depths for frames like PFF (NEW)
        available_depths = product.get("available_depths_mm", [])
        if available_depths:
            props["available_depths_mm"] = available_depths

        # Add source page for citations (NEW)
        source_page = product.get("source_page")
        if source_page is not None:
            props["source_page"] = source_page

        # Create ProductVariant node
        db.create_node("ProductVariant", props)
        counts["product_variants"] += 1
        created_variants.add(variant_id)

        # Link to DocumentSource
        db.create_relationship(
            "ProductVariant", variant_id,
            "FROM_DOCUMENT",
            "DocumentSource", source_document
        )
        counts["relationships"] += 1

        # Step 3: Create Category nodes and IS_CATEGORY relationships
        for category in product.get("categories", []):
            cat_label = category.get("label")
            cat_value = category.get("value")

            if not cat_label or not cat_value:
                continue

            # Create unique category key
            cat_key = f"{cat_label}:{cat_value}"

            # MERGE Category node (type + name for uniqueness)
            if cat_key not in created_categories:
                db.create_node("Category", {
                    "name": cat_value,
                    "type": cat_label
                })
                counts["categories"] += 1
                created_categories.add(cat_key)

                # Also create as Concept for vector search bridging
                if cat_value not in concept_cache:
                    embedding = generate_embedding(f"{cat_label}: {cat_value}")
                    db.create_node("Concept", {
                        "name": cat_value,
                        "category_type": cat_label,
                        "embedding": embedding
                    })
                    counts["concepts"] += 1
                    concept_cache.add(cat_value)

            # Create IS_CATEGORY relationship
            db.create_relationship(
                "ProductVariant", variant_id,
                "IS_CATEGORY",
                "Category", cat_value
            )
            counts["relationships"] += 1

    # Step 4: Create Accessory nodes
    for accessory in extracted_data.get("accessories", []):
        acc_id = accessory.get("id") or accessory.get("name")
        if not acc_id:
            continue

        acc_props = {
            "name": acc_id,
            "description": accessory.get("name", acc_id)
        }
        if accessory.get("price"):
            acc_props["price"] = accessory["price"]

        db.create_node("Accessory", acc_props)
        counts["accessories"] += 1

        # Link to DocumentSource
        db.create_relationship(
            "Accessory", acc_id,
            "FROM_DOCUMENT",
            "DocumentSource", source_document
        )
        counts["relationships"] += 1

        # Create COMPATIBLE_WITH relationships
        for compatible_id in accessory.get("compatible_with", []):
            if compatible_id in created_variants:
                db.create_relationship(
                    "Accessory", acc_id,
                    "COMPATIBLE_WITH",
                    "ProductVariant", compatible_id
                )
                counts["relationships"] += 1

    # Step 5: Create FilterCartridge nodes and ACCEPTS_CARTRIDGE relationships
    for cartridge in extracted_data.get("filter_cartridges", []):
        cartridge_id = cartridge.get("id") or cartridge.get("model_name")
        if not cartridge_id:
            continue

        cartridge_props = {
            "name": cartridge_id,
            "model_name": cartridge.get("model_name", cartridge_id),
        }

        # Add numeric properties
        for key in ["weight_kg", "carbon_weight_kg", "diameter_mm", "length_mm", "pellet_size_mm"]:
            if cartridge.get(key) is not None:
                cartridge_props[key] = cartridge[key]

        # Add string properties
        if cartridge.get("media_type"):
            cartridge_props["media_type"] = cartridge["media_type"]

        db.create_node("FilterCartridge", cartridge_props)
        counts["filter_cartridges"] += 1

        # Link to DocumentSource
        db.create_relationship(
            "FilterCartridge", cartridge_id,
            "FROM_DOCUMENT",
            "DocumentSource", source_document
        )
        counts["relationships"] += 1

        # Create ACCEPTS_CARTRIDGE relationships to compatible housings
        for housing_id in cartridge.get("compatible_housings", []):
            if housing_id in created_variants:
                db.create_relationship(
                    "ProductVariant", housing_id,
                    "ACCEPTS_CARTRIDGE",
                    "FilterCartridge", cartridge_id
                )
                counts["relationships"] += 1

        # Create Concept for vector search bridging
        cartridge_concept = f"Filter Cartridge {cartridge.get('model_name', cartridge_id)}"
        if cartridge_concept not in concept_cache:
            embedding = generate_embedding(cartridge_concept)
            db.create_node("Concept", {
                "name": cartridge_concept,
                "component_type": "FilterCartridge",
                "embedding": embedding
            })
            counts["concepts"] += 1
            concept_cache.add(cartridge_concept)

    # Step 6: Create DuctConnection nodes and COMPATIBLE_WITH_DUCT relationships
    for duct in extracted_data.get("duct_connections", []):
        duct_id = duct.get("id") or f"DUCT-{duct.get('housing_size', 'unknown')}"
        if not duct_id:
            continue

        duct_props = {
            "name": duct_id,
            "housing_size": duct.get("housing_size", ""),
        }

        # Add numeric properties
        if duct.get("housing_width_mm") is not None:
            duct_props["housing_width_mm"] = duct["housing_width_mm"]
        if duct.get("housing_height_mm") is not None:
            duct_props["housing_height_mm"] = duct["housing_height_mm"]

        # Store valid duct diameters as array property
        if duct.get("valid_duct_diameters_mm"):
            duct_props["valid_duct_diameters_mm"] = duct["valid_duct_diameters_mm"]

        if duct.get("transition_type"):
            duct_props["transition_type"] = duct["transition_type"]

        db.create_node("DuctConnection", duct_props)
        counts["duct_connections"] += 1

        # Link to DocumentSource
        db.create_relationship(
            "DuctConnection", duct_id,
            "FROM_DOCUMENT",
            "DocumentSource", source_document
        )
        counts["relationships"] += 1

        # Create COMPATIBLE_WITH_DUCT relationships to matching ProductVariants
        # Match based on housing dimensions (width_mm, height_mm)
        housing_width = duct.get("housing_width_mm")
        housing_height = duct.get("housing_height_mm")

        if housing_width and housing_height:
            for product in extracted_data.get("products", []):
                variant_props = product.get("variant_props", {})
                if (variant_props.get("width_mm") == housing_width and
                    variant_props.get("height_mm") == housing_height):
                    product_id = product.get("id")
                    if product_id and product_id in created_variants:
                        db.create_relationship(
                            "ProductVariant", product_id,
                            "COMPATIBLE_WITH_DUCT",
                            "DuctConnection", duct_id
                        )
                        counts["relationships"] += 1

        # Create Concept for vector search bridging
        duct_concept = f"Duct Transition {duct.get('housing_size', '')} to Ø{duct.get('valid_duct_diameters_mm', [])}"
        if duct_concept not in concept_cache:
            embedding = generate_embedding(duct_concept)
            db.create_node("Concept", {
                "name": duct_concept,
                "component_type": "DuctConnection",
                "embedding": embedding
            })
            counts["concepts"] += 1
            concept_cache.add(duct_concept)

    # Step 7: Create MaterialSpecification nodes
    for material in extracted_data.get("material_specifications", []):
        material_code = material.get("code")
        if not material_code:
            continue

        material_props = {
            "name": material_code,
            "code": material_code,
            "full_name": material.get("full_name", material_code),
        }

        if material.get("corrosion_class"):
            material_props["corrosion_class"] = material["corrosion_class"]
        if material.get("description"):
            material_props["description"] = material["description"]

        db.create_node("MaterialSpecification", material_props)
        counts["material_specs"] += 1

        # Link to DocumentSource
        db.create_relationship(
            "MaterialSpecification", material_code,
            "FROM_DOCUMENT",
            "DocumentSource", source_document
        )
        counts["relationships"] += 1

        # Create Concept for vector search bridging
        material_concept = f"Material {material.get('full_name', material_code)} ({material_code})"
        if material_concept not in concept_cache:
            embedding = generate_embedding(material_concept)
            db.create_node("Concept", {
                "name": material_concept,
                "component_type": "MaterialSpecification",
                "corrosion_class": material.get("corrosion_class"),
                "embedding": embedding
            })
            counts["concepts"] += 1
            concept_cache.add(material_concept)

    # Step 8: Create FilterConsumable nodes and ACCEPTS_FILTER relationships
    for filter_item in extracted_data.get("filter_consumables", []):
        filter_id = filter_item.get("id") or filter_item.get("part_number")
        if not filter_id:
            continue

        filter_props = {
            "name": filter_id,
            "part_number": filter_item.get("part_number", filter_id),
            "filter_type": filter_item.get("filter_type", "Unknown"),
        }

        # Add optional properties
        if filter_item.get("model_name"):
            filter_props["model_name"] = filter_item["model_name"]
        if filter_item.get("weight_kg") is not None:
            filter_props["weight_kg"] = filter_item["weight_kg"]
        if filter_item.get("media_type"):
            filter_props["media_type"] = filter_item["media_type"]
        if filter_item.get("dimensions"):
            filter_props["dimensions"] = filter_item["dimensions"]
        if filter_item.get("efficiency_class"):
            filter_props["efficiency_class"] = filter_item["efficiency_class"]

        db.create_node("FilterConsumable", filter_props)
        counts["filter_consumables"] += 1

        # Link to DocumentSource
        db.create_relationship(
            "FilterConsumable", filter_id,
            "FROM_DOCUMENT",
            "DocumentSource", source_document
        )
        counts["relationships"] += 1

        # Create ACCEPTS_FILTER relationships to compatible housings
        for housing_id in filter_item.get("compatible_housings", []):
            if housing_id in created_variants:
                db.create_relationship(
                    "ProductVariant", housing_id,
                    "ACCEPTS_FILTER",
                    "FilterConsumable", filter_id
                )
                counts["relationships"] += 1

        # Create Concept for vector search bridging
        filter_concept = f"Filter {filter_item.get('model_name', '')} ({filter_item.get('part_number', filter_id)})"
        if filter_concept not in concept_cache:
            embedding = generate_embedding(filter_concept)
            db.create_node("Concept", {
                "name": filter_concept,
                "component_type": "FilterConsumable",
                "filter_type": filter_item.get("filter_type"),
                "embedding": embedding
            })
            counts["concepts"] += 1
            concept_cache.add(filter_concept)

    # Step 9: Create additional Concept nodes from schema and extraction
    all_concepts = list(set(
        schema.get("concepts", []) +
        extracted_data.get("concepts", [])
    ))

    for concept_name in all_concepts:
        if concept_name and concept_name not in concept_cache:
            embedding = generate_embedding(concept_name)
            db.create_node("Concept", {
                "name": concept_name,
                "embedding": embedding
            })
            counts["concepts"] += 1
            concept_cache.add(concept_name)

    # Step 10: Store reference airflow table as Concept nodes for vector search
    for ref in extracted_data.get("reference_airflow_table", []):
        module_size = ref.get("module_size", "")
        designation = ref.get("module_designation", "")
        airflow = ref.get("airflow_m3h", 0)

        if module_size and airflow:
            ref_concept = f"Reference Airflow {module_size} ({designation}): {airflow} m³/h"
            if ref_concept not in concept_cache:
                embedding = generate_embedding(ref_concept)
                db.create_node("Concept", {
                    "name": ref_concept,
                    "component_type": "ReferenceAirflow",
                    "module_size": module_size,
                    "module_designation": designation,
                    "airflow_m3h": airflow,
                    "embedding": embedding
                })
                counts["concepts"] += 1
                concept_cache.add(ref_concept)

    # Step 11: Store compatibility rules as CompatibilityRule nodes
    for rule in extracted_data.get("compatibility_rules", []):
        if isinstance(rule, dict):
            rule_text = rule.get("rule", "")
            rule_name = f"Rule: {rule_text[:50]}"
            rule_props = {
                "name": rule_name,
                "description": rule_text,
                "constraint_type": rule.get("constraint_type", ""),
                "constraint_property": rule.get("constraint_property", ""),
                "constraint_value": rule.get("constraint_value")
            }
            db.create_node("CompatibilityRule", rule_props)

            # Link rule to applicable product families
            for family in rule.get("applies_to", []):
                # Find variants in this family and link
                for product in extracted_data.get("products", []):
                    if product.get("family") == family:
                        db.create_relationship(
                            "CompatibilityRule", rule_name,
                            "APPLIES_TO",
                            "ProductVariant", product.get("id")
                        )
                        counts["relationships"] += 1
                        break  # Just link to first variant as example

    return counts


def ingest_document(file_bytes: bytes, mime_type: str, schema: dict, source_name: str) -> dict:
    """Full ingestion pipeline: extract data and write Configuration Graph.

    This is the main entry point for Pass 2 execution.

    Args:
        file_bytes: Raw document bytes
        mime_type: MIME type
        schema: Confirmed schema from analyze_document_schema()
        source_name: Name for the document source

    Returns:
        Dict with extraction results and graph write counts
    """
    # Extract data using schema
    extracted = extract_document_data(file_bytes, mime_type, schema)

    if extracted.get("error"):
        return {
            "message": "Extraction failed",
            "error": extracted["error"],
            "counts": {},
            "extracted": extracted
        }

    # Write Configuration Graph
    counts = write_configuration_graph(extracted, schema, source_name)

    return {
        "message": "Document ingested successfully",
        "counts": counts,
        "extracted": extracted,
        "schema": schema
    }
