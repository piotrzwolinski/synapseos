"""Seed script for the Hybrid GraphRAG Sales Assistant.

Seeds 3 test cases:
1. Worley - Scope mismatch (filter vs housing unit)
2. Huddinge - Competitor pricing (Camfil Cambox -> GDR Nano, 20% discount)
3. Knittel - Engineering solution (height constraints, flange adapter)
"""

from database import db
from ingestor import ingest_case


# Test Case 1: Worley - Scope Mismatch
WORLEY_CASE = """
Project: Worley Engineering HVAC Retrofit
Customer: Worley Engineering

Summary:
The customer initially requested a quote for replacement HEPA filters for their cleanroom.
After reviewing their existing system, we discovered they were using outdated housing units
that couldn't accommodate modern high-efficiency filters properly.

Problem Identified:
- Customer asked for "filters" but their real need was a complete housing unit upgrade
- Their current Donaldson housings were 15 years old and seals were degrading
- The filter frames didn't match our standard sizes

Solution:
We proposed our GDR-3000 housing unit with integrated HEPA filtration instead of just filters.
This was a more expensive solution but addressed the root cause of their air quality issues.

Outcome:
- Customer initially pushed back on the higher cost
- We offered a site visit to demonstrate the seal degradation issues
- After seeing the evidence, they approved the full housing unit replacement
- Project value increased from $12,000 (filters only) to $85,000 (complete system)

Products involved:
- GDR-3000 Housing Unit: $45,000 (Capital equipment)
- GDR-H13 HEPA Filters: $2,500 each, 16 units needed (Consumables)

Lessons:
- Always verify the actual scope before quoting
- "Filter replacement" requests often indicate larger system issues
- Site visits are powerful tools for demonstrating hidden problems
"""

# Test Case 2: Huddinge - Competitor Pricing
HUDDINGE_CASE = """
Project: Huddinge Hospital Air Handling Upgrade
Customer: Huddinge Hospital (Stockholm Region Healthcare)

Summary:
Competitive bid situation where customer had an existing quote from Camfil for their
Cambox air handling units. We needed to displace the incumbent with our GDR Nano series.

Competitive Situation:
- Camfil quoted their Cambox 2000 series at $32,000 per unit (8 units needed)
- Total Camfil quote: $256,000
- Customer had good relationship with Camfil rep

Our Approach:
- Positioned GDR Nano as technically superior (better energy efficiency, lower pressure drop)
- Offered 20% discount from list price to be competitive
- Emphasized lower total cost of ownership (TCO) over 5 years
- Provided energy savings calculation showing $15,000/year savings vs Camfil

Final Quote:
- GDR Nano units: $28,000 each (after 20% discount from $35,000 list)
- Total: $224,000 (12% below Camfil)
- Plus 5-year service contract at $8,000/year

Outcome:
- Won the bid based on combination of price and TCO analysis
- Customer appreciated the detailed energy savings breakdown
- Established new relationship in Stockholm healthcare market

Products:
- GDR Nano 2000: List price $35,000, offered at $28,000
- Competitor equivalent: Camfil Cambox 2000

Key Learnings:
- Always ask if customer has competitive quotes
- 20% discount is maximum approved without regional manager approval
- TCO analysis is very effective in healthcare sector
- Energy efficiency claims must be backed by data
"""

# Test Case 3: Knittel - Engineering Solution
KNITTEL_CASE = """
Project: Knittel Pharmaceuticals Clean Room Installation
Customer: Knittel Pharmaceuticals GmbH

Summary:
Customer needed ceiling-mounted HEPA filtration for new cleanroom but had severe height
constraints due to existing ductwork and structural limitations.

Technical Challenge:
- Available ceiling height: 2.4m (standard requirement: 2.7m minimum)
- Standard GDR ceiling units require 400mm clearance above drop ceiling
- Only 250mm clearance available in customer's facility
- Customer was considering a competitor low-profile solution

Engineering Solution:
We designed a custom flange adapter that reduced the clearance requirement:
- Standard unit modified with low-profile flange adapter (Part: GDR-FLA-150)
- Reduced clearance requirement from 400mm to 200mm
- Required engineering approval from product team (3-day turnaround)
- Custom solution added $800 per unit in adapter costs

Installation Notes:
- Flange adapter required specific mounting orientation
- Gasket seals needed to be applied on-site
- Training provided to installation contractor

Outcome:
- Successfully installed 24 ceiling units in constrained space
- Customer avoided costly building modifications ($50,000+ savings)
- Solution has been standardized for future low-clearance installations

Products:
- GDR Ceiling Mount HEPA Unit: $3,200 each
- GDR-FLA-150 Flange Adapter: $800 each (custom solution)
- Installation gasket kit: $45 each

Lessons:
- Height and space constraints are common in retrofit projects
- Custom engineering solutions can win deals that seem lost
- Document custom solutions for future reference
- Flange adapters are now a standard catalog item due to this project
"""


def seed_database():
    """Seed the database with test cases."""
    print("Initializing vector index...")
    db.create_vector_index()

    print("\nIngesting Worley case (scope mismatch)...")
    counts1 = ingest_case(
        text=WORLEY_CASE,
        project_name="Worley Engineering",
        customer="Worley Engineering"
    )
    print(f"  Created: {counts1}")

    print("\nIngesting Huddinge case (competitor pricing)...")
    counts2 = ingest_case(
        text=HUDDINGE_CASE,
        project_name="Huddinge Hospital",
        customer="Stockholm Region Healthcare"
    )
    print(f"  Created: {counts2}")

    print("\nIngesting Knittel case (engineering solution)...")
    counts3 = ingest_case(
        text=KNITTEL_CASE,
        project_name="Knittel Pharmaceuticals",
        customer="Knittel Pharmaceuticals GmbH"
    )
    print(f"  Created: {counts3}")

    print("\nSeeding complete!")
    print(f"Total nodes: {db.get_node_count()}")
    print(f"Total relationships: {db.get_relationship_count()}")


if __name__ == "__main__":
    seed_database()
