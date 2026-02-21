#!/usr/bin/env python3
"""
Fix Inventory Logic and Enhance Option Display Labels

This script:
1. Removes incorrect cross-sell relationships (GDB → PFF)
2. Adds correct cross-sell relationships (GDB → Spare Filters, Pre-filters)
3. Enhances FeatureOption nodes with display_label for better UX

Run this script ONCE to fix the inventory logic.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from db_result_helpers import result_to_dicts, result_single, result_value
from falkordb import FalkorDB

load_dotenv(dotenv_path="../.env")


def fix_cross_sell_relationships(graph):
    """Remove incorrect and add correct cross-sell relationships."""

    print("\n" + "-" * 50)
    print("FIXING CROSS-SELL RELATIONSHIPS")
    print("-" * 50)

    # Step 1: Remove incorrect GDB → PFF relationship
    print("\n🔧 Removing incorrect cross-sell: GDB → PFF...")
    result = graph.query("""
        MATCH (gdb:ProductFamily)-[r:SUGGESTS_CROSS_SELL]->(pff:ProductFamily)
        WHERE (gdb.id = 'FAM_GDB' OR gdb.name CONTAINS 'GDB')
          AND (pff.id = 'FAM_PFF' OR pff.name CONTAINS 'PFF' OR pff.name CONTAINS 'Frame')
        DELETE r
        RETURN count(r) AS deleted
    """)
    deleted = result_single(result)["deleted"]
    print(f"   Deleted {deleted} incorrect relationship(s)")

    # Step 2: Add correct cross-sell relationships for GDB
    print("\n🔧 Adding correct cross-sell relationships for GDB...")

    # Create consumable nodes if they don't exist
    graph.query("""
        // Create or update Spare Filters consumable
        MERGE (bags:Consumable {id: 'CONS_BAGS'})
        SET bags.name = 'Spare Bag Filters',
            bags.description = 'Replacement bag filters for GDB/GDMI housings',
            bags.category = 'Consumable',
            bags.why_suggest = 'Bag filters require periodic replacement (typically 6-12 months)'

        // Create or update Pre-filter solution
        MERGE (prefilter:Consumable {id: 'CONS_PREFILTER'})
        SET prefilter.name = 'Pre-filter (G4/M5)',
            prefilter.description = 'Coarse pre-filter to extend main filter life',
            prefilter.category = 'Accessory',
            prefilter.why_suggest = 'Pre-filtration extends main filter lifespan 2-3x'

        // Create or update Differential Pressure Gauge
        MERGE (gauge:Accessory {id: 'ACC_DPGAUGE'})
        SET gauge.name = 'Differential Pressure Gauge',
            gauge.description = 'Monitor filter loading for optimal replacement timing',
            gauge.category = 'Accessory',
            gauge.why_suggest = 'Enables condition-based maintenance instead of time-based'
    """)

    # Link GDB to correct cross-sells
    graph.query("""
        MATCH (gdb:ProductFamily)
        WHERE gdb.id = 'FAM_GDB' OR gdb.name CONTAINS 'GDB Kanalfilterskåp'

        MATCH (bags:Consumable {id: 'CONS_BAGS'})
        MERGE (gdb)-[:SUGGESTS_CROSS_SELL {reason: 'Replacement filters', priority: 1}]->(bags)

        WITH gdb
        MATCH (prefilter:Consumable {id: 'CONS_PREFILTER'})
        MERGE (gdb)-[:SUGGESTS_CROSS_SELL {reason: 'Extend filter life', priority: 2}]->(prefilter)

        WITH gdb
        MATCH (gauge:Accessory {id: 'ACC_DPGAUGE'})
        MERGE (gdb)-[:SUGGESTS_CROSS_SELL {reason: 'Maintenance monitoring', priority: 3}]->(gauge)
    """)
    print("   ✓ GDB cross-sell relationships updated")

    # Do the same for GDMI
    graph.query("""
        MATCH (gdmi:ProductFamily)
        WHERE gdmi.id = 'FAM_GDMI' OR gdmi.name CONTAINS 'GDMI'

        MATCH (bags:Consumable {id: 'CONS_BAGS'})
        MERGE (gdmi)-[:SUGGESTS_CROSS_SELL {reason: 'Replacement filters', priority: 1}]->(bags)

        WITH gdmi
        MATCH (prefilter:Consumable {id: 'CONS_PREFILTER'})
        MERGE (gdmi)-[:SUGGESTS_CROSS_SELL {reason: 'Extend filter life', priority: 2}]->(prefilter)
    """)
    print("   ✓ GDMI cross-sell relationships updated")


def enhance_option_display_labels(graph):
    """Add display_label and benefit properties to FeatureOption nodes."""

    print("\n" + "-" * 50)
    print("ENHANCING OPTION DISPLAY LABELS")
    print("-" * 50)

    # GDB Housing Length options
    print("\n🏷️  Updating GDB housing length options...")
    graph.query("""
        MATCH (opt:FeatureOption {id: 'OPT_GDB_LEN_550'})
        SET opt.display_label = '550mm (Compact / Tight Spaces)',
            opt.benefit = 'Ideal for limited installation space or short bag filters up to 450mm',
            opt.use_case = 'Compact installations, retrofit projects'
    """)
    graph.query("""
        MATCH (opt:FeatureOption {id: 'OPT_GDB_LEN_750'})
        SET opt.display_label = '750mm (Standard / Energy Efficient)',
            opt.benefit = 'Larger filter surface area means lower pressure drop and energy savings',
            opt.use_case = 'New installations, energy-conscious projects',
            opt.is_recommended = true
    """)
    print("   ✓ GDB options enhanced")

    # GDMI Housing Length options
    print("\n🏷️  Updating GDMI housing length options...")
    graph.query("""
        MATCH (opt:FeatureOption {id: 'OPT_GDMI_LEN_600'})
        SET opt.display_label = '600mm (Compact / Indoor)',
            opt.benefit = 'Sufficient for most indoor installations with short filters',
            opt.use_case = 'Indoor AHUs, space-constrained installations'
    """)
    graph.query("""
        MATCH (opt:FeatureOption {id: 'OPT_GDMI_LEN_850'})
        SET opt.display_label = '850mm (Standard / Outdoor)',
            opt.benefit = 'Accommodates long bag filters with maximum surface area',
            opt.use_case = 'Rooftop units, outdoor installations',
            opt.is_recommended = true
    """)
    print("   ✓ GDMI options enhanced")

    # GDC Housing Length options
    print("\n🏷️  Updating GDC housing length options...")
    graph.query("""
        MATCH (opt:FeatureOption {id: 'OPT_GDC_LEN_750'})
        SET opt.display_label = '750mm (Standard Carbon)',
            opt.benefit = 'Standard configuration for 300mm carbon cylinders',
            opt.use_case = 'General odor/VOC removal'
    """)
    graph.query("""
        MATCH (opt:FeatureOption {id: 'OPT_GDC_LEN_900'})
        SET opt.display_label = '900mm (Extended + Polishing)',
            opt.benefit = 'Fits 450mm cylinders plus polishing filter for higher efficiency',
            opt.use_case = 'High-load applications, critical odor control'
    """)
    print("   ✓ GDC options enhanced")


def verify_changes(graph):
    """Verify the changes were applied correctly."""

    print("\n" + "-" * 50)
    print("VERIFYING CHANGES")
    print("-" * 50)

    # Check cross-sell relationships
    print("\n📋 Cross-sell relationships for GDB:")
    result = graph.query("""
        MATCH (gdb:ProductFamily)-[r:SUGGESTS_CROSS_SELL]->(target)
        WHERE gdb.id = 'FAM_GDB' OR gdb.name CONTAINS 'GDB Kanalfilterskåp'
        RETURN target.name AS suggested, r.reason AS reason
        ORDER BY r.priority
    """)
    for record in result_to_dicts(result):
        print(f"   → {record['suggested']} ({record['reason']})")

    # Check PFF is NOT suggested
    result = graph.query("""
        MATCH (gdb:ProductFamily)-[:SUGGESTS_CROSS_SELL]->(pff)
        WHERE (gdb.name CONTAINS 'GDB') AND (pff.name CONTAINS 'PFF' OR pff.name CONTAINS 'Frame')
        RETURN count(*) AS bad_links
    """)
    bad_links = result_single(result)["bad_links"]
    if bad_links == 0:
        print("   ✓ No incorrect PFF cross-sell found")
    else:
        print(f"   ⚠️ Found {bad_links} incorrect PFF links still present!")

    # Check display labels
    print("\n📋 Option display labels:")
    result = graph.query("""
        MATCH (opt:FeatureOption)
        WHERE opt.display_label IS NOT NULL
        RETURN opt.id AS id, opt.display_label AS label, opt.benefit AS benefit
        ORDER BY opt.id
    """)
    for record in result_to_dicts(result):
        print(f"   {record['id']}: {record['label']}")


def main():
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", 6379))
    password = os.getenv("FALKORDB_PASSWORD", None)
    graph_name = os.getenv("FALKORDB_GRAPH", "hvac")

    # FalkorDB connects with defaults if env vars not set

    print("=" * 60)
    print("FIX INVENTORY LOGIC & ENHANCE DISPLAY LABELS")
    print("=" * 60)

    print(f"\nConnecting to FalkorDB at {uri}...")
    db = FalkorDB(host=host, port=port, password=password)
    graph = db.select_graph(graph_name)

    try:
        result = graph.query("RETURN 1 AS test")
        if result_single(result)["test"] != 1:
            raise Exception("Connection test failed")
        print("Connected successfully!")

        fix_cross_sell_relationships(graph)
        enhance_option_display_labels(graph)
        verify_changes(graph)

        print("\n" + "=" * 60)
        print("INVENTORY FIX COMPLETE")
        print("=" * 60)
        print("\n✅ Cross-sell relationships corrected")
        print("✅ Option display labels enhanced")
        print("\nRestart the backend to apply changes.")

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
    finally:
        pass  # FalkorDB connection auto-managed


if __name__ == "__main__":
    main()
