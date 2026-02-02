"""Case study ingestion pipeline for the Hybrid GraphRAG Sales Assistant."""

import os
import json
import base64
from google import genai
from google.genai import types
from dotenv import load_dotenv

from database import db
from embeddings import generate_embedding
from prompts import EXTRACTION_PROMPT, EVENT_GRAPH_EXTRACTION_PROMPT
from models import ExtractionResult, ExtractedHardData, ExtractedSoftKnowledge

load_dotenv(dotenv_path="../.env")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
LLM_MODEL = "gemini-2.0-flash"
VISION_MODEL = "gemini-1.5-pro"  # Better for vision tasks with large context


def extract_knowledge(text: str, project_name: str) -> ExtractionResult:
    """Use LLM to extract structured knowledge from case study text.

    Args:
        text: The case study text
        project_name: Name of the project/case

    Returns:
        ExtractionResult with hard_data and soft_knowledge
    """
    prompt = EXTRACTION_PROMPT.format(text=text, project_name=project_name)

    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    # Parse the JSON response
    try:
        data = json.loads(response.text)
        return ExtractionResult(
            hard_data=ExtractedHardData(**data.get("hard_data", {})),
            soft_knowledge=ExtractedSoftKnowledge(**data.get("soft_knowledge", {}))
        )
    except (json.JSONDecodeError, KeyError) as e:
        # Return empty result if parsing fails
        print(f"Warning: Failed to parse LLM response: {e}")
        return ExtractionResult(
            hard_data=ExtractedHardData(),
            soft_knowledge=ExtractedSoftKnowledge()
        )


def ingest_case(text: str, project_name: str, customer: str = None) -> dict:
    """Ingest a case study into the knowledge graph.

    This pipeline:
    1. Extracts hard data + soft knowledge using LLM
    2. Creates Product/CompetitorProduct nodes with EQUIVALENT_TO relationships
    3. Creates Project, Concept (with embeddings), Observation, Action nodes
    4. Creates relationships: HAS_OBSERVATION, RELATES_TO, LED_TO

    Args:
        text: The case study text
        project_name: Name for this project/case
        customer: Optional customer name

    Returns:
        Dict with counts of created nodes and relationships
    """
    # Step 1: LLM extraction
    extraction = extract_knowledge(text, project_name)

    counts = {
        "products": 0,
        "competitor_products": 0,
        "concepts": 0,
        "observations": 0,
        "actions": 0,
        "relationships": 0
    }

    # Step 2: Create Product nodes
    for product in extraction.hard_data.products:
        props = {"name": product.name}
        if product.sku:
            props["sku"] = product.sku
        if product.price is not None:
            props["price"] = product.price
        if product.dimensions:
            props["dimensions"] = product.dimensions
        if product.type:
            props["type"] = product.type.value
        db.create_node("Product", props)
        counts["products"] += 1

    # Step 3: Create CompetitorProduct nodes and EQUIVALENT_TO relationships
    for cp in extraction.hard_data.competitor_products:
        props = {"name": cp.name}
        if cp.manufacturer:
            props["manufacturer"] = cp.manufacturer
        db.create_node("CompetitorProduct", props)
        counts["competitor_products"] += 1

    # Create product mappings
    for mapping in extraction.hard_data.product_mappings:
        # Find our product by SKU or name and link to competitor
        our_product_ref = mapping.our_product_sku or mapping.our_product_name
        if our_product_ref and mapping.competitor_product:
            db.create_relationship(
                "CompetitorProduct", mapping.competitor_product,
                "EQUIVALENT_TO",
                "Product", our_product_ref
            )
            counts["relationships"] += 1

    # Step 4: Create Project node
    project_props = {"name": project_name}
    if customer:
        project_props["customer"] = customer
    db.create_node("Project", project_props)

    # Step 5: Create Concept nodes with embeddings
    for concept_name in extraction.soft_knowledge.concepts:
        embedding = generate_embedding(concept_name)
        db.create_node("Concept", {
            "name": concept_name,
            "embedding": embedding
        })
        counts["concepts"] += 1

    # Step 6: Create Observation nodes and link to Project and Concepts
    for i, obs_text in enumerate(extraction.soft_knowledge.observations):
        obs_name = f"{project_name}_obs_{i+1}"
        db.create_node("Observation", {
            "name": obs_name,
            "description": obs_text
        })
        counts["observations"] += 1

        # Link Project -> Observation
        db.create_relationship(
            "Project", project_name,
            "HAS_OBSERVATION",
            "Observation", obs_name
        )
        counts["relationships"] += 1

        # Link Observation -> Concepts (all concepts relate to all observations in same case)
        for concept_name in extraction.soft_knowledge.concepts:
            db.create_relationship(
                "Observation", obs_name,
                "RELATES_TO",
                "Concept", concept_name
            )
            counts["relationships"] += 1

    # Step 7: Create Action nodes and link to Observations
    for i, action_text in enumerate(extraction.soft_knowledge.actions):
        action_name = f"{project_name}_action_{i+1}"

        # Parse outcome if present (format: "action -> outcome")
        if " -> " in action_text:
            parts = action_text.split(" -> ", 1)
            description = parts[0]
            outcome = parts[1] if len(parts) > 1 else None
        else:
            description = action_text
            outcome = None

        props = {"name": action_name, "description": description}
        if outcome:
            props["outcome"] = outcome

        db.create_node("Action", props)
        counts["actions"] += 1

        # Link all Observations -> Action
        for j in range(len(extraction.soft_knowledge.observations)):
            obs_name = f"{project_name}_obs_{j+1}"
            db.create_relationship(
                "Observation", obs_name,
                "LED_TO",
                "Action", action_name
            )
            counts["relationships"] += 1

    return counts


def extract_event_graph_from_text(thread_text: str) -> dict:
    """Use Gemini to extract Event Graph from email thread text.

    Args:
        thread_text: The email thread as text

    Returns:
        Dict with project, timeline, concepts, and causality
    """
    prompt = f"{EVENT_GRAPH_EXTRACTION_PROMPT}\n\n---\nEMAIL THREAD:\n---\n{thread_text}"

    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    # Parse the JSON response
    try:
        data = json.loads(response.text)
        return data
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Warning: Failed to parse LLM response: {e}")
        print(f"Raw response: {response.text}")
        return {
            "project": "Unknown Project",
            "timeline": [],
            "concepts": [],
            "causality": []
        }


def extract_event_graph(image_data: bytes, mime_type: str = "image/png") -> dict:
    """Use Gemini Vision to extract Event Graph from an email thread image.

    Args:
        image_data: Raw image bytes (screenshot of email thread)
        mime_type: MIME type of the image (image/png, image/jpeg, application/pdf)

    Returns:
        Dict with project, timeline, concepts, and causality
    """
    # Encode image as base64
    image_b64 = base64.b64encode(image_data).decode("utf-8")

    # Create the content with image and prompt
    response = client.models.generate_content(
        model=VISION_MODEL,
        contents=[
            types.Content(
                parts=[
                    types.Part(
                        inline_data=types.Blob(
                            mime_type=mime_type,
                            data=image_b64
                        )
                    ),
                    types.Part(text=EVENT_GRAPH_EXTRACTION_PROMPT)
                ]
            )
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    # Parse the JSON response
    try:
        data = json.loads(response.text)
        return data
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Warning: Failed to parse vision LLM response: {e}")
        print(f"Raw response: {response.text}")
        return {
            "project": "Unknown Project",
            "timeline": [],
            "concepts": [],
            "causality": []
        }


def ingest_email_thread_image(image_data: bytes, mime_type: str = "image/png") -> dict:
    """Ingest an email thread image into the knowledge graph using Event Graph schema.

    This pipeline creates a rich Event Graph that preserves:
    - Individual emails as Event nodes (chronological chain)
    - Person nodes for senders
    - Observation nodes (Symptom/Constraint/Blocker) linked to events
    - Action nodes (Standard/Workaround) linked to events
    - Concepts linked ONLY to the specific step where they appear (granular assignment)
    - Causality relationships (REVEALED, ADDRESSES)

    Schema:
    - (:Project {name})
    - (:Person {name, email})
    - (:Event {type: 'Email', date, summary})
    - (:Concept {name, embedding})
    - (:Observation {type, description})
    - (:Action {type, description})

    Relationships:
    - (Event)-[:NEXT_EVENT]->(Event) - Chronological chain
    - (Event)-[:PART_OF]->(Project)
    - (Event)-[:SENT_BY]->(Person)
    - (Event)-[:REPORTED]->(Observation)
    - (Event)-[:PROPOSED]->(Action)
    - (Observation)-[:RELATES_TO]->(Concept) - ONLY local concepts for this step
    - (Action)-[:RELATES_TO]->(Concept) - ONLY local concepts for this step
    - (Observation)-[:REVEALED]->(Observation) - Causality
    - (Action)-[:ADDRESSES]->(Observation) - Solution addresses problem

    Args:
        image_data: Raw image bytes (screenshot of email thread)
        mime_type: MIME type of the image

    Returns:
        Dict with extraction results and counts of created nodes
    """
    # Step 1: Vision analysis to extract Event Graph
    extraction = extract_event_graph(image_data, mime_type)

    project_name = extraction.get("project", "Unknown Project")
    timeline = extraction.get("timeline", [])
    causality = extraction.get("causality", [])

    counts = {
        "project": project_name,
        "persons": 0,
        "events": 0,
        "concepts": 0,
        "observations": 0,
        "actions": 0,
        "relationships": 0
    }

    # Step 2: Create Project node
    db.create_node("Project", {"name": project_name})

    # Track created nodes for relationship building
    event_nodes = {}  # step -> event_name
    logic_nodes = {}  # step -> (label, name) for Observations/Actions
    person_cache = set()  # track created persons
    concept_cache = set()  # track created concepts (avoid duplicate embeddings)
    all_concepts = []  # collect all concepts for response

    # Step 3: Create Event chain and associated nodes
    previous_event_name = None

    for entry in sorted(timeline, key=lambda x: x.get("step", 0)):
        step = entry.get("step", 1)
        sender = entry.get("sender", "Unknown")
        sender_email = entry.get("sender_email")
        date = entry.get("date", "Unknown")
        summary = entry.get("summary", "")
        logic_type = entry.get("logic_type")
        logic_desc = entry.get("logic_description", "")
        citation = entry.get("citation", "")
        local_concepts = entry.get("local_concepts", [])

        # Create unique event name
        event_name = f"{project_name}_event_{step}"
        event_nodes[step] = event_name

        # Create Event node
        db.create_node("Event", {
            "name": event_name,
            "type": "Email",
            "date": date,
            "summary": summary,
            "step": step
        })
        counts["events"] += 1

        # Link Event -> Project
        db.create_relationship(
            "Event", event_name,
            "PART_OF",
            "Project", project_name
        )
        counts["relationships"] += 1

        # Create Person node if not exists
        person_key = sender_email or sender
        if person_key not in person_cache:
            person_props = {"name": sender}
            if sender_email:
                person_props["email"] = sender_email
            db.create_node("Person", person_props)
            counts["persons"] += 1
            person_cache.add(person_key)

        # Link Event -> Person (SENT_BY)
        db.create_relationship(
            "Event", event_name,
            "SENT_BY",
            "Person", sender
        )
        counts["relationships"] += 1

        # Create NEXT_EVENT chain
        if previous_event_name is not None:
            db.create_relationship(
                "Event", previous_event_name,
                "NEXT_EVENT",
                "Event", event_name
            )
            counts["relationships"] += 1

        previous_event_name = event_name

        # Create Logic node (Observation or Action) if present
        if logic_type and logic_desc:
            logic_name = f"{project_name}_logic_{step}"
            logic_label = None

            if logic_type == "SAFETY_CRITICAL":
                # Create SafetyRisk node (dual label: Observation:SafetyRisk)
                # This triggers priority safety checking in retrieval
                safety_props = {
                    "name": logic_name,
                    "type": "SAFETY_CRITICAL",
                    "description": logic_desc,
                    "hazard_trigger": entry.get("hazard_trigger", ""),
                    "hazard_environment": entry.get("hazard_environment", ""),
                    "safe_alternative": entry.get("safe_alternative", "")
                }
                if citation:
                    safety_props["citation"] = citation
                db.create_safety_risk_node(safety_props)
                counts["observations"] += 1
                if "safety_risks" not in counts:
                    counts["safety_risks"] = 0
                counts["safety_risks"] += 1
                logic_nodes[step] = ("SafetyRisk", logic_name)
                logic_label = "SafetyRisk"

                # Link Event -> SafetyRisk (REPORTED)
                db.create_relationship(
                    "Event", event_name,
                    "REPORTED",
                    "SafetyRisk", logic_name
                )
                counts["relationships"] += 1

            elif logic_type in ("Symptom", "Constraint", "Blocker"):
                # Create Observation node with citation for explainability
                obs_props = {
                    "name": logic_name,
                    "type": logic_type,
                    "description": logic_desc
                }
                if citation:
                    obs_props["citation"] = citation
                db.create_node("Observation", obs_props)
                counts["observations"] += 1
                logic_nodes[step] = ("Observation", logic_name)
                logic_label = "Observation"

                # Link Event -> Observation (REPORTED)
                db.create_relationship(
                    "Event", event_name,
                    "REPORTED",
                    "Observation", logic_name
                )
                counts["relationships"] += 1

            elif logic_type in ("Standard", "Workaround", "ProductMapping", "Commercial"):
                # Create Action node with citation for explainability
                # ProductMapping captures product selections, pricing, and competitor equivalences
                action_props = {
                    "name": logic_name,
                    "type": logic_type,
                    "description": logic_desc
                }
                if citation:
                    action_props["citation"] = citation
                db.create_node("Action", action_props)
                counts["actions"] += 1
                logic_nodes[step] = ("Action", logic_name)
                logic_label = "Action"

                # Link Event -> Action (PROPOSED)
                db.create_relationship(
                    "Event", event_name,
                    "PROPOSED",
                    "Action", logic_name
                )
                counts["relationships"] += 1

            # Create LOCAL Concept nodes and link ONLY to this specific logic node
            # For ProductMapping, concepts should be specific product names (e.g., "GDR Nano 1/1", "Camfil Cambox")
            if logic_label and local_concepts:
                for concept_name in local_concepts:
                    # Create Concept node if not already created
                    if concept_name not in concept_cache:
                        embedding = generate_embedding(concept_name)
                        db.create_node("Concept", {
                            "name": concept_name,
                            "embedding": embedding
                        })
                        counts["concepts"] += 1
                        concept_cache.add(concept_name)
                        all_concepts.append(concept_name)

                    # Link THIS logic node -> THIS concept (granular relationship)
                    db.create_relationship(
                        logic_label, logic_name,
                        "RELATES_TO",
                        "Concept", concept_name
                    )
                    counts["relationships"] += 1

                    # For ProductMapping: Also create CompetitorProduct node if concept looks like competitor
                    # This ensures competitor products are searchable via search_competitor_mentions()
                    if logic_type == "ProductMapping":
                        known_competitors = ["camfil", "donaldson", "aaf", "freudenberg", "mann", "hengst", "nordic"]
                        if any(comp in concept_name.lower() for comp in known_competitors):
                            manufacturer = next((comp.title() for comp in known_competitors if comp in concept_name.lower()), None)
                            db.create_node("CompetitorProduct", {
                                "name": concept_name,
                                "manufacturer": manufacturer
                            })

                    # For SAFETY_CRITICAL: Create TRIGGERS_RISK relationship from concept to SafetyRisk
                    # This enables priority safety detection during retrieval
                    if logic_type == "SAFETY_CRITICAL":
                        db.create_triggers_risk_relationship(concept_name, logic_name)
                        counts["relationships"] += 1

    # Step 4: Create Causality relationships
    for causal_link in causality:
        if len(causal_link) == 3:
            from_step, rel_type, to_step = causal_link

            if from_step in logic_nodes and to_step in logic_nodes:
                from_label, from_name = logic_nodes[from_step]
                to_label, to_name = logic_nodes[to_step]

                if rel_type == "REVEALED":
                    db.create_relationship(
                        from_label, from_name,
                        "REVEALED",
                        to_label, to_name
                    )
                    counts["relationships"] += 1

                elif rel_type == "ADDRESSES":
                    db.create_relationship(
                        from_label, from_name,
                        "ADDRESSES",
                        to_label, to_name
                    )
                    counts["relationships"] += 1

    # Step 5: Create KnowledgeCandidate nodes for discovered external sources (Forensic Discovery)
    discovered_knowledge = extraction.get("discovered_knowledge", [])
    knowledge_candidates = []

    for dk in discovered_knowledge:
        raw_name = dk.get("raw_name", "")
        source_type = dk.get("type", "Software")
        # Support both old 'context' and new 'inference_logic' field names
        inference_logic = dk.get("inference_logic") or dk.get("context", "")
        citation = dk.get("citation", "")
        mentioned_in_step = dk.get("mentioned_in_step")

        if raw_name:
            # Find the event name for this step
            event_name = event_nodes.get(mentioned_in_step, f"{project_name}_event_1")

            candidate = db.create_knowledge_candidate(
                raw_name=raw_name,
                source_type=source_type,
                inference_logic=inference_logic,
                citation=citation,
                event_name=event_name
            )
            if candidate:
                knowledge_candidates.append(candidate)
                counts["knowledge_candidates"] = counts.get("knowledge_candidates", 0) + 1

    # Return results including extracted data for preview
    return {
        "message": "Email thread ingested successfully",
        "counts": counts,
        "extracted": {
            "project": project_name,
            "timeline": timeline,
            "concepts": all_concepts,
            "causality": causality,
            "discovered_knowledge": discovered_knowledge,
            "knowledge_candidates": knowledge_candidates
        }
    }


def ingest_email_thread_text(thread_text: str) -> dict:
    """Ingest an email thread (as text) into the knowledge graph using Event Graph schema.

    This pipeline creates a rich Event Graph that preserves:
    - Individual emails as Event nodes (chronological chain)
    - Person nodes for senders
    - Observation nodes (Symptom/Constraint/Blocker) linked to events
    - Action nodes (Standard/Workaround) linked to events
    - Concepts linked ONLY to the specific step where they appear (granular assignment)
    - Causality relationships (REVEALED, ADDRESSES)

    Args:
        thread_text: The email thread as plain text

    Returns:
        Dict with extraction results and counts of created nodes
    """
    # Step 1: LLM analysis to extract Event Graph
    extraction = extract_event_graph_from_text(thread_text)

    project_name = extraction.get("project", "Unknown Project")
    timeline = extraction.get("timeline", [])
    causality = extraction.get("causality", [])

    counts = {
        "project": project_name,
        "persons": 0,
        "events": 0,
        "concepts": 0,
        "observations": 0,
        "actions": 0,
        "relationships": 0
    }

    # Step 2: Create Project node
    db.create_node("Project", {"name": project_name})

    # Track created nodes for relationship building
    event_nodes = {}  # step -> event_name
    logic_nodes = {}  # step -> (label, name) for Observations/Actions
    person_cache = set()  # track created persons
    concept_cache = set()  # track created concepts (avoid duplicate embeddings)
    all_concepts = []  # collect all concepts for response

    # Step 3: Create Event chain and associated nodes
    previous_event_name = None

    for entry in sorted(timeline, key=lambda x: x.get("step", 0)):
        step = entry.get("step", 1)
        sender = entry.get("sender", "Unknown")
        sender_email = entry.get("sender_email")
        date = entry.get("date", "Unknown")
        summary = entry.get("summary", "")
        logic_type = entry.get("logic_type")
        logic_desc = entry.get("logic_description", "")
        citation = entry.get("citation", "")
        local_concepts = entry.get("local_concepts", [])

        # Create unique event name
        event_name = f"{project_name}_event_{step}"
        event_nodes[step] = event_name

        # Create Event node
        db.create_node("Event", {
            "name": event_name,
            "type": "Email",
            "date": date,
            "summary": summary,
            "step": step
        })
        counts["events"] += 1

        # Link Event -> Project
        db.create_relationship(
            "Event", event_name,
            "PART_OF",
            "Project", project_name
        )
        counts["relationships"] += 1

        # Create Person node if not exists
        person_key = sender_email or sender
        if person_key not in person_cache:
            person_props = {"name": sender}
            if sender_email:
                person_props["email"] = sender_email
            db.create_node("Person", person_props)
            counts["persons"] += 1
            person_cache.add(person_key)

        # Link Event -> Person (SENT_BY)
        db.create_relationship(
            "Event", event_name,
            "SENT_BY",
            "Person", sender
        )
        counts["relationships"] += 1

        # Create NEXT_EVENT chain
        if previous_event_name is not None:
            db.create_relationship(
                "Event", previous_event_name,
                "NEXT_EVENT",
                "Event", event_name
            )
            counts["relationships"] += 1

        previous_event_name = event_name

        # Create Logic node (Observation or Action) if present
        if logic_type and logic_desc:
            logic_name = f"{project_name}_logic_{step}"
            logic_label = None

            if logic_type == "SAFETY_CRITICAL":
                # Create SafetyRisk node (dual label: Observation:SafetyRisk)
                # This triggers priority safety checking in retrieval
                safety_props = {
                    "name": logic_name,
                    "type": "SAFETY_CRITICAL",
                    "description": logic_desc,
                    "hazard_trigger": entry.get("hazard_trigger", ""),
                    "hazard_environment": entry.get("hazard_environment", ""),
                    "safe_alternative": entry.get("safe_alternative", "")
                }
                if citation:
                    safety_props["citation"] = citation
                db.create_safety_risk_node(safety_props)
                counts["observations"] += 1
                if "safety_risks" not in counts:
                    counts["safety_risks"] = 0
                counts["safety_risks"] += 1
                logic_nodes[step] = ("SafetyRisk", logic_name)
                logic_label = "SafetyRisk"

                # Link Event -> SafetyRisk (REPORTED)
                db.create_relationship(
                    "Event", event_name,
                    "REPORTED",
                    "SafetyRisk", logic_name
                )
                counts["relationships"] += 1

            elif logic_type in ("Symptom", "Constraint", "Blocker"):
                # Create Observation node with citation for explainability
                obs_props = {
                    "name": logic_name,
                    "type": logic_type,
                    "description": logic_desc
                }
                if citation:
                    obs_props["citation"] = citation
                db.create_node("Observation", obs_props)
                counts["observations"] += 1
                logic_nodes[step] = ("Observation", logic_name)
                logic_label = "Observation"

                # Link Event -> Observation (REPORTED)
                db.create_relationship(
                    "Event", event_name,
                    "REPORTED",
                    "Observation", logic_name
                )
                counts["relationships"] += 1

            elif logic_type in ("Standard", "Workaround", "ProductMapping", "Commercial"):
                # Create Action node with citation for explainability
                # ProductMapping captures product selections, pricing, and competitor equivalences
                action_props = {
                    "name": logic_name,
                    "type": logic_type,
                    "description": logic_desc
                }
                if citation:
                    action_props["citation"] = citation
                db.create_node("Action", action_props)
                counts["actions"] += 1
                logic_nodes[step] = ("Action", logic_name)
                logic_label = "Action"

                # Link Event -> Action (PROPOSED)
                db.create_relationship(
                    "Event", event_name,
                    "PROPOSED",
                    "Action", logic_name
                )
                counts["relationships"] += 1

            # Create LOCAL Concept nodes and link ONLY to this specific logic node
            # For ProductMapping, concepts should be specific product names (e.g., "GDR Nano 1/1", "Camfil Cambox")
            if logic_label and local_concepts:
                for concept_name in local_concepts:
                    # Create Concept node if not already created
                    if concept_name not in concept_cache:
                        embedding = generate_embedding(concept_name)
                        db.create_node("Concept", {
                            "name": concept_name,
                            "embedding": embedding
                        })
                        counts["concepts"] += 1
                        concept_cache.add(concept_name)
                        all_concepts.append(concept_name)

                    # Link THIS logic node -> THIS concept (granular relationship)
                    db.create_relationship(
                        logic_label, logic_name,
                        "RELATES_TO",
                        "Concept", concept_name
                    )
                    counts["relationships"] += 1

                    # For ProductMapping: Also create CompetitorProduct node if concept looks like competitor
                    # This ensures competitor products are searchable via search_competitor_mentions()
                    if logic_type == "ProductMapping":
                        known_competitors = ["camfil", "donaldson", "aaf", "freudenberg", "mann", "hengst", "nordic"]
                        if any(comp in concept_name.lower() for comp in known_competitors):
                            manufacturer = next((comp.title() for comp in known_competitors if comp in concept_name.lower()), None)
                            db.create_node("CompetitorProduct", {
                                "name": concept_name,
                                "manufacturer": manufacturer
                            })

                    # For SAFETY_CRITICAL: Create TRIGGERS_RISK relationship from concept to SafetyRisk
                    # This enables priority safety detection during retrieval
                    if logic_type == "SAFETY_CRITICAL":
                        db.create_triggers_risk_relationship(concept_name, logic_name)
                        counts["relationships"] += 1

    # Step 4: Create Causality relationships
    for causal_link in causality:
        if len(causal_link) == 3:
            from_step, rel_type, to_step = causal_link

            if from_step in logic_nodes and to_step in logic_nodes:
                from_label, from_name = logic_nodes[from_step]
                to_label, to_name = logic_nodes[to_step]

                if rel_type == "REVEALED":
                    db.create_relationship(
                        from_label, from_name,
                        "REVEALED",
                        to_label, to_name
                    )
                    counts["relationships"] += 1

                elif rel_type == "ADDRESSES":
                    db.create_relationship(
                        from_label, from_name,
                        "ADDRESSES",
                        to_label, to_name
                    )
                    counts["relationships"] += 1

    # Step 5: Create KnowledgeCandidate nodes for discovered external sources (Forensic Discovery)
    discovered_knowledge = extraction.get("discovered_knowledge", [])
    knowledge_candidates = []

    for dk in discovered_knowledge:
        raw_name = dk.get("raw_name", "")
        source_type = dk.get("type", "Software")
        # Support both old 'context' and new 'inference_logic' field names
        inference_logic = dk.get("inference_logic") or dk.get("context", "")
        citation = dk.get("citation", "")
        mentioned_in_step = dk.get("mentioned_in_step")

        if raw_name:
            # Find the event name for this step
            event_name = event_nodes.get(mentioned_in_step, f"{project_name}_event_1")

            candidate = db.create_knowledge_candidate(
                raw_name=raw_name,
                source_type=source_type,
                inference_logic=inference_logic,
                citation=citation,
                event_name=event_name
            )
            if candidate:
                knowledge_candidates.append(candidate)
                counts["knowledge_candidates"] = counts.get("knowledge_candidates", 0) + 1

    # Return results including extracted data for preview
    return {
        "message": "Email thread ingested successfully",
        "counts": counts,
        "extracted": {
            "project": project_name,
            "timeline": timeline,
            "concepts": all_concepts,
            "causality": causality,
            "discovered_knowledge": discovered_knowledge,
            "knowledge_candidates": knowledge_candidates
        }
    }
