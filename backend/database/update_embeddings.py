#!/usr/bin/env python3
"""
Embedding Migration Script for Hybrid Search

This script prepares Neo4j nodes for vector-based semantic search by:
1. Generating embeddings for Application, Risk, Substance, and Requirement nodes
2. Creating vector indexes for efficient similarity search

Run this script ONCE to hydrate your graph with embeddings.
After running, the GraphReasoningEngine will use hybrid search automatically.

Usage:
    python database/update_embeddings.py
"""

import os
import sys
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(dotenv_path="../.env")

# Embedding configuration - using Gemini to match existing infrastructure
EMBEDDING_MODEL = "models/text-embedding-004"
EMBEDDING_DIMENSIONS = 3072

# Vector index configuration
APPLICATION_INDEX = "application_embeddings"
RISK_INDEX = "risk_embeddings"
SUBSTANCE_INDEX = "substance_embeddings"


def get_embedding(text: str) -> list[float]:
    """Generate embedding using Google's Gemini embedding model."""
    try:
        # Try new google.genai package first
        from google import genai
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
        result = client.models.embed_content(
            model="gemini-embedding-001",
            contents=text
        )
        return list(result.embeddings[0].values)
    except ImportError:
        # Fallback to deprecated package
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=text,
            task_type="retrieval_document"
        )
        return result['embedding']


def create_vector_indexes(driver, database: str):
    """Create vector indexes for semantic search on domain nodes."""
    indexes = [
        (APPLICATION_INDEX, "Application"),
        (RISK_INDEX, "Risk"),
        (SUBSTANCE_INDEX, "Substance"),
    ]

    with driver.session(database=database) as session:
        for index_name, label in indexes:
            try:
                # Try to create the vector index (IF NOT EXISTS handles duplicates)
                session.run(f"""
                    CREATE VECTOR INDEX {index_name} IF NOT EXISTS
                    FOR (n:{label})
                    ON (n.embedding)
                    OPTIONS {{
                        indexConfig: {{
                            `vector.dimensions`: {EMBEDDING_DIMENSIONS},
                            `vector.similarity_function`: 'cosine'
                        }}
                    }}
                """)
                print(f"   Created/verified vector index: {index_name} on {label}")

            except Exception as e:
                error_msg = str(e).lower()
                if "already exists" in error_msg or "equivalent" in error_msg:
                    print(f"   Index '{index_name}' already exists")
                else:
                    print(f"   Warning: Could not create index {index_name}: {e}")


def update_application_embeddings(driver, database: str):
    """Add embeddings to Application nodes."""
    print("\n   Fetching Application nodes...")

    with driver.session(database=database) as session:
        # Get all applications
        result = session.run("""
            MATCH (app:Application)
            WHERE app.embedding IS NULL
            RETURN app.id AS id, app.name AS name, app.keywords AS keywords
        """)

        applications = list(result)

        if not applications:
            print("   No Application nodes need embeddings (already embedded or none exist)")
            return 0

        print(f"   Found {len(applications)} Application nodes to embed...")

        embedded_count = 0
        for app in applications:
            app_id = app["id"]
            name = app["name"]
            keywords = app["keywords"] or []

            # Create rich text for embedding: name + keywords + semantic expansion
            # This improves semantic matching (e.g., "Surgery Center" -> "Hospital")
            text_for_embedding = f"{name}. Keywords: {', '.join(keywords)}."

            # Add semantic context based on domain knowledge
            semantic_expansions = {
                "Hospital": "medical facility, healthcare, surgery center, clinic, operating room, patient care, hygiene critical environment",
                "Swimming Pool": "aquatic facility, chlorinated water, natatorium, water park, leisure pool, swim center",
                "Commercial Kitchen": "food service, restaurant kitchen, culinary facility, food preparation, cooking area",
                "Paint Shop": "painting facility, spray booth, coating, finishing, automotive painting, industrial coating",
                "Marine/Offshore": "ship, vessel, offshore platform, maritime, sea environment, coastal, salt spray",
                "Laboratory": "research facility, cleanroom, pharmaceutical, scientific, sterile environment",
                "Office/Commercial": "workplace, business center, corporate, commercial building, standard environment"
            }

            if name in semantic_expansions:
                text_for_embedding += f" Related concepts: {semantic_expansions[name]}"

            try:
                embedding = get_embedding(text_for_embedding)

                # Update the node with embedding
                # Neo4j accepts float arrays directly as properties
                session.run("""
                    MATCH (app:Application {id: $id})
                    SET app.embedding = $embedding,
                        app.embedding_text = $text
                """, id=app_id, embedding=embedding, text=text_for_embedding)

                embedded_count += 1
                print(f"      Embedded: {name}")

            except Exception as e:
                print(f"      Error embedding {name}: {e}")

        return embedded_count


def update_risk_embeddings(driver, database: str):
    """Add embeddings to Risk nodes."""
    print("\n   Fetching Risk nodes...")

    with driver.session(database=database) as session:
        result = session.run("""
            MATCH (r:Risk)
            WHERE r.embedding IS NULL
            RETURN r.id AS id, r.name AS name, r.desc AS description, r.severity AS severity
        """)

        risks = list(result)

        if not risks:
            print("   No Risk nodes need embeddings")
            return 0

        print(f"   Found {len(risks)} Risk nodes to embed...")

        embedded_count = 0
        for risk in risks:
            risk_id = risk["id"]
            name = risk["name"]
            description = risk["description"] or ""
            severity = risk["severity"] or ""

            text_for_embedding = f"Risk: {name}. {description}. Severity: {severity}"

            try:
                embedding = get_embedding(text_for_embedding)

                session.run("""
                    MATCH (r:Risk {id: $id})
                    SET r.embedding = $embedding,
                        r.embedding_text = $text
                """, id=risk_id, embedding=embedding, text=text_for_embedding)

                embedded_count += 1
                print(f"      Embedded: {name}")

            except Exception as e:
                print(f"      Error embedding {name}: {e}")

        return embedded_count


def update_substance_embeddings(driver, database: str):
    """Add embeddings to Substance nodes."""
    print("\n   Fetching Substance nodes...")

    with driver.session(database=database) as session:
        result = session.run("""
            MATCH (s:Substance)
            WHERE s.embedding IS NULL
            RETURN s.id AS id, s.name AS name
        """)

        substances = list(result)

        if not substances:
            print("   No Substance nodes need embeddings")
            return 0

        print(f"   Found {len(substances)} Substance nodes to embed...")

        embedded_count = 0
        for sub in substances:
            sub_id = sub["id"]
            name = sub["name"]

            # Add context for substances
            substance_context = {
                "Chlorine": "chemical disinfectant, pool treatment, corrosive gas, bleach",
                "Salt Spray": "marine environment, coastal, sea salt, sodium chloride aerosol",
                "Grease": "cooking oil, kitchen exhaust, lipids, animal fat",
                "Water Vapor": "humidity, moisture, condensation, steam",
                "Paint Mist": "overspray, coating particles, aerosol paint, VOC",
                "Solvent Gases": "volatile organic compounds, paint thinner, chemical fumes"
            }

            context = substance_context.get(name, "")
            text_for_embedding = f"Substance: {name}. {context}" if context else f"Substance: {name}"

            try:
                embedding = get_embedding(text_for_embedding)

                session.run("""
                    MATCH (s:Substance {id: $id})
                    SET s.embedding = $embedding,
                        s.embedding_text = $text
                """, id=sub_id, embedding=embedding, text=text_for_embedding)

                embedded_count += 1
                print(f"      Embedded: {name}")

            except Exception as e:
                print(f"      Error embedding {name}: {e}")

        return embedded_count


def main():
    """Run the embedding migration."""
    print("=" * 60)
    print("HYBRID SEARCH EMBEDDING MIGRATION")
    print("=" * 60)

    # Connect to Neo4j
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    if not all([uri, user, password]):
        print("Error: Missing Neo4j connection environment variables")
        print("Required: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD")
        sys.exit(1)

    print(f"\nConnecting to Neo4j at {uri}...")
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        # Verify connection
        with driver.session(database=database) as session:
            result = session.run("RETURN 1 AS test")
            if result.single()["test"] != 1:
                raise Exception("Connection test failed")
        print("   Connected successfully!")

        # Step 1: Create vector indexes
        print("\n" + "-" * 40)
        print("STEP 1: Creating Vector Indexes")
        print("-" * 40)
        create_vector_indexes(driver, database)

        # Step 2: Embed Application nodes
        print("\n" + "-" * 40)
        print("STEP 2: Embedding Application Nodes")
        print("-" * 40)
        app_count = update_application_embeddings(driver, database)

        # Step 3: Embed Risk nodes
        print("\n" + "-" * 40)
        print("STEP 3: Embedding Risk Nodes")
        print("-" * 40)
        risk_count = update_risk_embeddings(driver, database)

        # Step 4: Embed Substance nodes
        print("\n" + "-" * 40)
        print("STEP 4: Embedding Substance Nodes")
        print("-" * 40)
        sub_count = update_substance_embeddings(driver, database)

        # Summary
        print("\n" + "=" * 60)
        print("MIGRATION COMPLETE")
        print("=" * 60)
        print(f"   Applications embedded: {app_count}")
        print(f"   Risks embedded:        {risk_count}")
        print(f"   Substances embedded:   {sub_count}")
        print(f"   Total:                 {app_count + risk_count + sub_count}")
        print("\nHybrid search is now enabled!")
        print("Restart the backend to use the new vector search capabilities.")

    except Exception as e:
        print(f"\nError during migration: {e}")
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
