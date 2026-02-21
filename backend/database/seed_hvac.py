#!/usr/bin/env python3
"""
HVAC Domain Data Seeder for Generic Schema

This script migrates HVAC-specific data into the domain-agnostic schema.
It demonstrates how ANY domain can be loaded into the Universal Engine.

The data here is HVAC-specific, but the SCHEMA is generic.
To support a new domain (Insurance, E-commerce), create a new seed script.
"""

import os
import sys
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(dotenv_path="../../.env")


def get_embedding(text: str) -> list[float]:
    """Generate embedding using OpenAI."""
    import google.generativeai as genai

    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type="retrieval_document"
    )
    return result['embedding']


def seed_hvac_data(db_connection):
    """
    Seed HVAC domain data into the generic schema.

    This function populates:
    - Layer 1: Items (Products), Properties, Categories
    - Layer 2: Contexts (Environments), Constraints, Risks
    - Layer 3: Discriminators, Options, Strategies
    """

    print("🌱 Seeding HVAC domain data into generic schema...")

    # =========================================================================
    # LAYER 1: INVENTORY (Products as Items)
    # =========================================================================

    print("\n📦 Layer 1: Creating Items (Products)...")

    items = [
        # GDB Series - Duct Filter Housings
        {
            "id": "ITEM_GDB_300x300",
            "name": "GDB-300x300",
            "description": "Duct filter housing for particle filtration, compact size",
            "category": "Filter Housing"
        },
        {
            "id": "ITEM_GDB_600x600",
            "name": "GDB-600x600",
            "description": "Duct filter housing for particle filtration, standard size",
            "category": "Filter Housing"
        },
        {
            "id": "ITEM_GDB_900x600",
            "name": "GDB-900x600",
            "description": "Duct filter housing for particle filtration, large size",
            "category": "Filter Housing"
        },
        # GDMI Series - Insulated Housings
        {
            "id": "ITEM_GDMI_600x600",
            "name": "GDMI-600x600",
            "description": "Insulated duct filter housing for outdoor/rooftop installation",
            "category": "Insulated Housing"
        },
        # GDC Series - Carbon Filter Housings
        {
            "id": "ITEM_GDC_600x600",
            "name": "GDC-600x600",
            "description": "Activated carbon filter housing for gas/odor removal",
            "category": "Carbon Housing"
        },
        {
            "id": "ITEM_GDC_EX",
            "name": "GDC-EX",
            "description": "ATEX-certified carbon housing for explosive atmospheres",
            "category": "Carbon Housing"
        },
    ]

    for item in items:
        db_connection.query("""
            MERGE (i:Item {id: $id})
            SET i.name = $name,
                i.description = $description
            WITH i
            MERGE (c:Category {name: $category})
            MERGE (i)-[:IN_CATEGORY]->(c)
        """, item)
        print(f"   ✓ Item: {item['name']}")

    # =========================================================================
    # LAYER 1: PROPERTIES (Product Attributes)
    # =========================================================================

    print("\n🏷️  Layer 1: Creating Properties...")

    properties = [
        # GDB-300x300 Properties
        {"item_id": "ITEM_GDB_300x300", "key": "material", "value": "FZ"},
        {"item_id": "ITEM_GDB_300x300", "key": "airflow_max_m3h", "value": "850"},
        {"item_id": "ITEM_GDB_300x300", "key": "corrosion_class", "value": "C3"},
        {"item_id": "ITEM_GDB_300x300", "key": "width_mm", "value": "300"},
        {"item_id": "ITEM_GDB_300x300", "key": "height_mm", "value": "300"},

        # GDB-600x600 Properties (multiple material variants)
        {"item_id": "ITEM_GDB_600x600", "key": "material", "value": "FZ"},
        {"item_id": "ITEM_GDB_600x600", "key": "material_options", "value": "FZ,ZM,RF,SF"},
        {"item_id": "ITEM_GDB_600x600", "key": "airflow_max_m3h", "value": "3400"},
        {"item_id": "ITEM_GDB_600x600", "key": "corrosion_class", "value": "C3"},
        {"item_id": "ITEM_GDB_600x600", "key": "width_mm", "value": "600"},
        {"item_id": "ITEM_GDB_600x600", "key": "height_mm", "value": "600"},
        {"item_id": "ITEM_GDB_600x600", "key": "length_options_mm", "value": "550,750"},

        # GDB-900x600 Properties
        {"item_id": "ITEM_GDB_900x600", "key": "material", "value": "FZ"},
        {"item_id": "ITEM_GDB_900x600", "key": "airflow_max_m3h", "value": "5000"},
        {"item_id": "ITEM_GDB_900x600", "key": "corrosion_class", "value": "C3"},
        {"item_id": "ITEM_GDB_900x600", "key": "width_mm", "value": "900"},
        {"item_id": "ITEM_GDB_900x600", "key": "height_mm", "value": "600"},

        # GDMI-600x600 Properties
        {"item_id": "ITEM_GDMI_600x600", "key": "material", "value": "FZ"},
        {"item_id": "ITEM_GDMI_600x600", "key": "material_options", "value": "FZ,ZM,RF"},
        {"item_id": "ITEM_GDMI_600x600", "key": "airflow_max_m3h", "value": "3400"},
        {"item_id": "ITEM_GDMI_600x600", "key": "insulated", "value": "true"},
        {"item_id": "ITEM_GDMI_600x600", "key": "outdoor_rated", "value": "true"},

        # GDC-600x600 Properties
        {"item_id": "ITEM_GDC_600x600", "key": "material", "value": "FZ"},
        {"item_id": "ITEM_GDC_600x600", "key": "filtration_type", "value": "activated_carbon"},
        {"item_id": "ITEM_GDC_600x600", "key": "conductive", "value": "false"},
        {"item_id": "ITEM_GDC_600x600", "key": "requires_prefilter", "value": "true"},

        # GDC-EX Properties
        {"item_id": "ITEM_GDC_EX", "key": "material", "value": "RF"},
        {"item_id": "ITEM_GDC_EX", "key": "filtration_type", "value": "activated_carbon"},
        {"item_id": "ITEM_GDC_EX", "key": "conductive", "value": "true"},
        {"item_id": "ITEM_GDC_EX", "key": "atex_certified", "value": "true"},
        {"item_id": "ITEM_GDC_EX", "key": "requires_prefilter", "value": "true"},
    ]

    for prop in properties:
        prop_id = f"{prop['item_id']}:{prop['key']}:{prop['value']}"
        db_connection.query("""
            MATCH (i:Item {id: $item_id})
            MERGE (p:Property {id: $prop_id})
            SET p.key = $key, p.value = $value
            MERGE (i)-[:HAS_PROP]->(p)
        """, {"item_id": prop["item_id"], "prop_id": prop_id, "key": prop["key"], "value": prop["value"]})

    print(f"   ✓ Created {len(properties)} properties")

    # =========================================================================
    # LAYER 2: CONTEXTS (Application Environments)
    # =========================================================================

    print("\n🌍 Layer 2: Creating Contexts (with embeddings)...")

    contexts = [
        {
            "id": "CTX_HOSPITAL",
            "name": "Hospital",
            "description": "Medical facility requiring high hygiene standards, frequent disinfection with chlorine-based agents, VDI 6022 compliance",
            "keywords": ["hospital", "medical", "healthcare", "clinic", "surgery", "patient", "hygiene"]
        },
        {
            "id": "CTX_OFFICE",
            "name": "Office",
            "description": "Standard commercial office environment, normal humidity, no aggressive chemicals",
            "keywords": ["office", "commercial", "business", "workplace", "corporate"]
        },
        {
            "id": "CTX_KITCHEN",
            "name": "Commercial Kitchen",
            "description": "Restaurant or industrial kitchen with grease, steam, high humidity, cooking odors",
            "keywords": ["kitchen", "restaurant", "catering", "cooking", "food service", "grease"]
        },
        {
            "id": "CTX_POOL",
            "name": "Swimming Pool",
            "description": "Indoor swimming pool with chlorine atmosphere, high humidity, corrosive environment",
            "keywords": ["pool", "swimming", "aquatic", "chlorine", "spa", "wellness"]
        },
        {
            "id": "CTX_BAKERY",
            "name": "Bakery",
            "description": "Food production with flour dust, potential explosive atmosphere (ATEX Zone 22)",
            "keywords": ["bakery", "flour", "bread", "pastry", "dust", "powder"]
        },
        {
            "id": "CTX_PAINT_SHOP",
            "name": "Paint Shop",
            "description": "Spray painting facility with solvents, VOCs, overspray, potential explosive atmosphere",
            "keywords": ["paint", "spray", "coating", "lacquer", "solvent", "voc", "finishing"]
        },
        {
            "id": "CTX_OUTDOOR",
            "name": "Outdoor Installation",
            "description": "Rooftop or outdoor mounting exposed to weather, temperature variations, rain, snow",
            "keywords": ["outdoor", "rooftop", "outside", "weather", "external", "roof"]
        },
        {
            "id": "CTX_MARINE",
            "name": "Marine Environment",
            "description": "Ship or offshore installation with salt spray, vibration, extreme corrosion conditions C5-M",
            "keywords": ["marine", "ship", "offshore", "sea", "naval", "boat", "maritime"]
        },
    ]

    for ctx in contexts:
        # Generate embedding for context description
        print(f"   Generating embedding for: {ctx['name']}...")
        embedding = get_embedding(ctx["description"])

        db_connection.query("""
            MERGE (ctx:Context {id: $id})
            SET ctx.name = $name,
                ctx.description = $description,
                ctx.keywords = $keywords,
                ctx.embedding = vecf32($embedding)
        """, {
            "id": ctx["id"],
            "name": ctx["name"],
            "description": ctx["description"],
            "keywords": ctx["keywords"],
            "embedding": embedding
        })
        print(f"   ✓ Context: {ctx['name']}")

    # =========================================================================
    # LAYER 2: CONSTRAINTS (Requirements)
    # =========================================================================

    print("\n⚖️  Layer 2: Creating Constraints...")

    constraints = [
        {
            "id": "CON_MATERIAL_C5",
            "target_key": "material",
            "operator": "IN",
            "required_value": "RF,SF",
            "severity": "CRITICAL",
            "description": "Requires C5 corrosion class material (Stainless Steel)"
        },
        {
            "id": "CON_MATERIAL_C4",
            "target_key": "material",
            "operator": "IN",
            "required_value": "ZM,RF,SF",
            "severity": "WARNING",
            "description": "Requires C4 or higher corrosion class material"
        },
        {
            "id": "CON_INSULATED",
            "target_key": "insulated",
            "operator": "EQUALS",
            "required_value": "true",
            "severity": "CRITICAL",
            "description": "Requires insulated housing"
        },
        {
            "id": "CON_CONDUCTIVE",
            "target_key": "conductive",
            "operator": "EQUALS",
            "required_value": "true",
            "severity": "CRITICAL",
            "description": "Requires conductive/grounded construction for ATEX"
        },
        {
            "id": "CON_ATEX",
            "target_key": "atex_certified",
            "operator": "EQUALS",
            "required_value": "true",
            "severity": "CRITICAL",
            "description": "Requires ATEX certification for explosive atmospheres"
        },
        {
            "id": "CON_OUTDOOR",
            "target_key": "outdoor_rated",
            "operator": "EQUALS",
            "required_value": "true",
            "severity": "WARNING",
            "description": "Outdoor installation recommended"
        },
        {
            "id": "CON_PREFILTER",
            "target_key": "requires_prefilter",
            "operator": "EQUALS",
            "required_value": "true",
            "severity": "WARNING",
            "description": "Pre-filtration required to protect carbon media"
        },
    ]

    for con in constraints:
        db_connection.query("""
            MERGE (con:Constraint {id: $id})
            SET con.target_key = $target_key,
                con.operator = $operator,
                con.required_value = $required_value,
                con.severity = $severity,
                con.description = $description
        """, con)
        print(f"   ✓ Constraint: {con['id']}")

    # =========================================================================
    # LAYER 2: CONTEXT → CONSTRAINT RELATIONSHIPS
    # =========================================================================

    print("\n🔗 Layer 2: Linking Contexts to Constraints...")

    context_constraints = [
        # Hospital requires C5 corrosion resistance
        {"context_id": "CTX_HOSPITAL", "constraint_id": "CON_MATERIAL_C5",
         "reason": "VDI 6022 hygiene requirements, chlorine-based disinfectants"},

        # Pool requires C5 corrosion resistance
        {"context_id": "CTX_POOL", "constraint_id": "CON_MATERIAL_C5",
         "reason": "Chlorine atmosphere causes rapid corrosion of standard steel"},

        # Marine requires C5 corrosion resistance
        {"context_id": "CTX_MARINE", "constraint_id": "CON_MATERIAL_C5",
         "reason": "Salt spray environment, ISO 12944-2 C5-M classification"},

        # Kitchen requires C4 or higher
        {"context_id": "CTX_KITCHEN", "constraint_id": "CON_MATERIAL_C4",
         "reason": "Grease and steam exposure accelerates corrosion"},

        # Outdoor requires insulation
        {"context_id": "CTX_OUTDOOR", "constraint_id": "CON_INSULATED",
         "reason": "Temperature differential causes condensation without insulation"},
        {"context_id": "CTX_OUTDOOR", "constraint_id": "CON_OUTDOOR",
         "reason": "Weather protection and thermal performance"},

        # Bakery requires ATEX (explosive dust)
        {"context_id": "CTX_BAKERY", "constraint_id": "CON_CONDUCTIVE",
         "reason": "Flour dust creates explosive atmosphere (Zone 22)"},
        {"context_id": "CTX_BAKERY", "constraint_id": "CON_ATEX",
         "reason": "ATEX 2014/34/EU compliance for explosive dust"},

        # Paint shop requires ATEX (explosive vapors)
        {"context_id": "CTX_PAINT_SHOP", "constraint_id": "CON_CONDUCTIVE",
         "reason": "Solvent vapors create explosive atmosphere"},
        {"context_id": "CTX_PAINT_SHOP", "constraint_id": "CON_ATEX",
         "reason": "ATEX 2014/34/EU compliance for explosive vapors"},
        {"context_id": "CTX_PAINT_SHOP", "constraint_id": "CON_PREFILTER",
         "reason": "Overspray particles will clog carbon filters rapidly"},
    ]

    for link in context_constraints:
        db_connection.query("""
            MATCH (ctx:Context {id: $context_id})
            MATCH (con:Constraint {id: $constraint_id})
            MERGE (ctx)-[r:IMPLIES_CONSTRAINT]->(con)
            SET r.reason = $reason
        """, link)

    print(f"   ✓ Created {len(context_constraints)} context-constraint links")

    # =========================================================================
    # LAYER 2: RISKS
    # =========================================================================

    print("\n⚠️  Layer 2: Creating Risks...")

    risks = [
        {
            "id": "RISK_CORROSION",
            "name": "Material Corrosion",
            "description": "Steel corrosion due to aggressive chemical environment",
            "severity": "CRITICAL"
        },
        {
            "id": "RISK_HYGIENE",
            "name": "Hygiene Failure",
            "description": "Failure to meet hygiene standards for medical/food applications",
            "severity": "CRITICAL"
        },
        {
            "id": "RISK_EXPLOSION",
            "name": "Explosion Hazard",
            "description": "Risk of dust or vapor explosion in ungrounded equipment",
            "severity": "CRITICAL"
        },
        {
            "id": "RISK_CONDENSATION",
            "name": "Condensation Damage",
            "description": "Water condensation inside housing due to temperature differential",
            "severity": "WARNING"
        },
        {
            "id": "RISK_CLOGGING",
            "name": "Filter Clogging",
            "description": "Premature filter clogging due to inadequate pre-filtration",
            "severity": "WARNING"
        },
    ]

    for risk in risks:
        db_connection.query("""
            MERGE (r:Risk {id: $id})
            SET r.name = $name,
                r.description = $description,
                r.severity = $severity
        """, risk)
        print(f"   ✓ Risk: {risk['name']}")

    # Context generates Risk
    context_risks = [
        {"context_id": "CTX_HOSPITAL", "risk_id": "RISK_CORROSION", "probability": "high"},
        {"context_id": "CTX_HOSPITAL", "risk_id": "RISK_HYGIENE", "probability": "high"},
        {"context_id": "CTX_POOL", "risk_id": "RISK_CORROSION", "probability": "high"},
        {"context_id": "CTX_KITCHEN", "risk_id": "RISK_CORROSION", "probability": "medium"},
        {"context_id": "CTX_BAKERY", "risk_id": "RISK_EXPLOSION", "probability": "high"},
        {"context_id": "CTX_PAINT_SHOP", "risk_id": "RISK_EXPLOSION", "probability": "high"},
        {"context_id": "CTX_PAINT_SHOP", "risk_id": "RISK_CLOGGING", "probability": "high"},
        {"context_id": "CTX_OUTDOOR", "risk_id": "RISK_CONDENSATION", "probability": "high"},
    ]

    for link in context_risks:
        db_connection.query("""
            MATCH (ctx:Context {id: $context_id})
            MATCH (r:Risk {id: $risk_id})
            MERGE (ctx)-[rel:GENERATES_RISK]->(r)
            SET rel.probability = $probability
        """, link)

    print(f"   ✓ Created {len(context_risks)} context-risk links")

    # =========================================================================
    # LAYER 3: DISCRIMINATORS (Questions)
    # =========================================================================

    print("\n❓ Layer 3: Creating Discriminators...")

    discriminators = [
        {
            "id": "DISC_AIRFLOW",
            "name": "airflow",
            "question": "What is the required airflow capacity (m³/h)?",
            "priority": 1
        },
        {
            "id": "DISC_HOUSING_LENGTH",
            "name": "housing_length",
            "question": "What housing length do you need (for filter depth)?",
            "priority": 2
        },
        {
            "id": "DISC_MATERIAL",
            "name": "material",
            "question": "What material grade do you need?",
            "priority": 3
        },
        {
            "id": "DISC_FILTRATION_TYPE",
            "name": "filtration_type",
            "question": "What type of filtration do you need?",
            "priority": 1
        },
        {
            "id": "DISC_INSTALLATION",
            "name": "installation_location",
            "question": "Where will the housing be installed?",
            "priority": 2
        },
    ]

    for disc in discriminators:
        db_connection.query("""
            MERGE (d:Discriminator {id: $id})
            SET d.name = $name,
                d.question = $question,
                d.priority = $priority
        """, disc)
        print(f"   ✓ Discriminator: {disc['name']}")

    # =========================================================================
    # LAYER 3: OPTIONS
    # =========================================================================

    print("\n📋 Layer 3: Creating Options...")

    options = [
        # Airflow options
        {"disc_id": "DISC_AIRFLOW", "value": "850", "description": "Small office unit (~300x300mm)"},
        {"disc_id": "DISC_AIRFLOW", "value": "3400", "description": "Standard office (~600x600mm)"},
        {"disc_id": "DISC_AIRFLOW", "value": "5000", "description": "Large installation (~900x600mm)"},

        # Housing length options
        {"disc_id": "DISC_HOUSING_LENGTH", "value": "550", "description": "Short housing for filters up to 450mm"},
        {"disc_id": "DISC_HOUSING_LENGTH", "value": "750", "description": "Long housing for filters up to 650mm"},

        # Material options
        {"disc_id": "DISC_MATERIAL", "value": "FZ", "description": "Galvanized steel (standard, C3)"},
        {"disc_id": "DISC_MATERIAL", "value": "ZM", "description": "Zinc-Magnesium (enhanced, C4)"},
        {"disc_id": "DISC_MATERIAL", "value": "RF", "description": "Stainless Steel (premium, C5)"},

        # Filtration type options
        {"disc_id": "DISC_FILTRATION_TYPE", "value": "particles", "description": "Dust and particles (GDB/GDMI)"},
        {"disc_id": "DISC_FILTRATION_TYPE", "value": "gases", "description": "Gases and odors (GDC)"},
        {"disc_id": "DISC_FILTRATION_TYPE", "value": "both", "description": "Particles + gases (multi-stage)"},

        # Installation location options
        {"disc_id": "DISC_INSTALLATION", "value": "indoor", "description": "Indoor installation"},
        {"disc_id": "DISC_INSTALLATION", "value": "outdoor", "description": "Outdoor/rooftop installation"},
    ]

    for opt in options:
        opt_id = f"{opt['disc_id']}:{opt['value']}"
        db_connection.query("""
            MATCH (d:Discriminator {id: $disc_id})
            MERGE (o:Option {id: $opt_id})
            SET o.value = $value,
                o.description = $description
            MERGE (d)-[:HAS_OPTION]->(o)
        """, {"disc_id": opt["disc_id"], "opt_id": opt_id, "value": opt["value"], "description": opt["description"]})

    print(f"   ✓ Created {len(options)} options")

    # =========================================================================
    # LAYER 3: PROPERTY → DISCRIMINATOR LINKS
    # =========================================================================

    print("\n🔗 Layer 3: Linking Properties to Discriminators...")

    # Properties that depend on discriminators (variable properties)
    prop_disc_links = [
        # Material property depends on material discriminator
        {"prop_key": "material", "disc_id": "DISC_MATERIAL"},
        # Airflow determines which size item to select
        {"prop_key": "airflow_max_m3h", "disc_id": "DISC_AIRFLOW"},
        # Housing length options
        {"prop_key": "length_options_mm", "disc_id": "DISC_HOUSING_LENGTH"},
    ]

    for link in prop_disc_links:
        db_connection.query("""
            MATCH (p:Property)
            WHERE p.key = $prop_key
            MATCH (d:Discriminator {id: $disc_id})
            MERGE (p)-[:DEPENDS_ON]->(d)
        """, link)

    print(f"   ✓ Created {len(prop_disc_links)} property-discriminator links")

    # =========================================================================
    # LAYER 3: STRATEGIES
    # =========================================================================

    print("\n🎯 Layer 3: Creating Strategies...")

    strategies = [
        {
            "id": "STRAT_PREFILTER",
            "name": "Pre-filter Cross-sell",
            "type": "cross_sell",
            "message": "Consider adding a G4/M5 pre-filter to extend main filter life",
            "priority": 1
        },
        {
            "id": "STRAT_MATERIAL_UPGRADE",
            "name": "Material Upgrade",
            "type": "recommendation",
            "message": "For this environment, consider upgrading to corrosion-resistant material",
            "priority": 1
        },
        {
            "id": "STRAT_INSULATION",
            "name": "Insulation Recommendation",
            "type": "recommendation",
            "message": "Outdoor installation benefits from insulated housing (GDMI series)",
            "priority": 2
        },
    ]

    for strat in strategies:
        db_connection.query("""
            MERGE (s:Strategy {id: $id})
            SET s.name = $name,
                s.type = $type,
                s.message = $message,
                s.priority = $priority
        """, strat)
        print(f"   ✓ Strategy: {strat['name']}")

    # Link strategies to contexts
    context_strategies = [
        {"context_id": "CTX_HOSPITAL", "strategy_id": "STRAT_MATERIAL_UPGRADE"},
        {"context_id": "CTX_POOL", "strategy_id": "STRAT_MATERIAL_UPGRADE"},
        {"context_id": "CTX_KITCHEN", "strategy_id": "STRAT_MATERIAL_UPGRADE"},
        {"context_id": "CTX_OUTDOOR", "strategy_id": "STRAT_INSULATION"},
        {"context_id": "CTX_PAINT_SHOP", "strategy_id": "STRAT_PREFILTER"},
    ]

    for link in context_strategies:
        db_connection.query("""
            MATCH (ctx:Context {id: $context_id})
            MATCH (s:Strategy {id: $strategy_id})
            MERGE (ctx)-[:TRIGGERS_STRATEGY]->(s)
        """, link)

    print(f"   ✓ Created {len(context_strategies)} context-strategy links")

    # =========================================================================
    # CREATE VECTOR INDEX (FalkorDB specific)
    # =========================================================================

    print("\n🔍 Creating vector index on Context embeddings...")

    try:
        db_connection.query("""
            CALL db.idx.vector.createNodeIndex('Context', 'embedding', 768, 'cosine')
        """)
        print("   ✓ Vector index created")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("   ⊘ Vector index already exists")
        else:
            print(f"   ⚠ Vector index creation: {e}")

    print("\n✅ HVAC domain data seeding complete!")


def main():
    """Main entry point."""
    from falkordb import FalkorDB

    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", 6379))
    password = os.getenv("FALKORDB_PASSWORD", None)
    graph_name = os.getenv("FALKORDB_GRAPH", "hvac")

    print(f"📊 Connecting to FalkorDB at {host}:{port}...")
    db = FalkorDB(host=host, port=port, password=password)
    graph = db.select_graph(graph_name)
    seed_hvac_data(graph)


if __name__ == "__main__":
    main()
