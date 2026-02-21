"""
Graph Audit Debate Orchestrator.

Runs a 3-round debate protocol to verify knowledge graph integrity against a PDF catalog:
  Round 1: AUDIT      — Each LLM independently audits graph data vs PDF (parallel)
  Round 2: CRITIQUE   — Each LLM reviews the others' findings (parallel)
  Round 3: SYNTHESIS  — One LLM merges everything into a consensus report

Yields SSE-compatible event dicts throughout the process.
"""

import json
import logging
import os
import time
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncGenerator, Optional

from llm_providers import LLMProvider, LLMResponse
from debate_orchestrator import _clean_json_response, _parse_json_safe
from graph_audit_prompts import (
    AUDIT_SYSTEM_PROMPT,
    AUDIT_USER_PROMPT_TEMPLATE,
    CRITIQUE_PROMPT,
    SYNTHESIS_PROMPT,
)
from db_result_helpers import result_to_dicts

logger = logging.getLogger(__name__)

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def build_graph_data_snapshot(db_connection) -> str:
    """Query the graph for all Layer 1 & 2 data and format as a structured markdown string."""
    graph = db_connection.connect()
    sections = []

    # 1. Product Families with materials
    pf_records = result_to_dicts(graph.query("""
        MATCH (pf:ProductFamily)
        OPTIONAL MATCH (pf)-[r:AVAILABLE_IN_MATERIAL]->(m:Material)
        WITH pf, collect(DISTINCT {code: m.code, is_default: r.is_default, on_request: r.on_request}) AS materials
        OPTIONAL MATCH (pf)-[:HAS_LENGTH_VARIANT]->(vl)
        WITH pf, materials, collect(DISTINCT {mm: vl.length_mm, f40_mm: vl.length_f40_mm, max_cartridge_length: vl.max_cartridge_length_mm, max_filter_depth: vl.max_filter_depth_mm, is_default: vl.is_default, description: vl.description, order_code_length: vl.order_code_length, compatibility_modes: vl.compatibility_modes}) AS lengths
        OPTIONAL MATCH (pf)-[:HAS_OPTION]->(opt)
        WITH pf, materials, lengths, collect(DISTINCT {code: opt.code, name: opt.name, length_variant_link: opt.length_variant_link}) AS options
        OPTIONAL MATCH (pf)-[:HAS_VARIABLE_FEATURE]->(vf)
        WITH pf, materials, lengths, options, collect(DISTINCT {name: vf.feature_name, property_key: vf.property_key, values: vf.allowed_values}) AS features
        OPTIONAL MATCH (pf)-[:HAS_STANDARD_FEATURE]->(sf)
        RETURN pf, materials, lengths, options, features,
               collect(DISTINCT sf.feature_name) AS standard_features
        ORDER BY pf.selection_priority
    """))

    if pf_records:
        sections.append("## PRODUCT FAMILIES IN GRAPH (Layer 1)\n")
        for i, rec in enumerate(pf_records, 1):
            pf = rec["pf"]
            props = dict(pf) if hasattr(pf, '__iter__') else pf
            name = props.get("name", props.get("id", "Unknown"))
            fam_id = props.get("id", "")
            sections.append(f"### {i}. {name} ({fam_id})")
            sections.append(f"- Type: {props.get('display_name', 'N/A')}")
            if props.get("construction_type"):
                sections.append(f"- Construction: {props['construction_type']} (source: {props.get('construction_type_source', 'N/A')})")
            if props.get("corrosion_class"):
                sections.append(f"- Corrosion class: {props['corrosion_class']}")
            if props.get("indoor_only") is not None:
                sections.append(f"- Indoor only: {props['indoor_only']}")
            if props.get("outdoor_safe") is not None:
                sections.append(f"- Outdoor safe: {props['outdoor_safe']}")
            if props.get("selection_priority") is not None:
                sections.append(f"- Selection priority: {props['selection_priority']}")
            if props.get("code_format"):
                sections.append(f"- Code format: {props['code_format']}")
            if props.get("service_access_type"):
                sections.append(f"- Service access: {props['service_access_type']}")
            if props.get("door_insulation"):
                sections.append(f"- Door insulation: {props['door_insulation']}")
            if props.get("hinge_type"):
                sections.append(f"- Hinge type: {props['hinge_type']}, Lock type: {props.get('lock_type', 'N/A')}")
            if props.get("corrosion_class_note"):
                sections.append(f"- Corrosion note: {props['corrosion_class_note']}")
            if props.get("max_filter_depth_mm"):
                sections.append(f"- Max filter depth: {props['max_filter_depth_mm']}mm")
            if props.get("default_frame_depth"):
                sections.append(f"- Default frame depth: {props['default_frame_depth']}mm, available: {props.get('available_frame_depths', 'N/A')}")
            if props.get("airflow_basis"):
                sections.append(f"- Airflow basis: {props['airflow_basis']}")
            if props.get("housing_construction"):
                sections.append(f"- Housing construction: {props['housing_construction']}, Door construction: {props.get('door_construction', 'N/A')}")
            if props.get("accepted_filter_frame_thickness_mm"):
                sections.append(f"- Accepted filter frame: {props['accepted_filter_frame_thickness_mm']}mm")
            if props.get("mounting_type"):
                sections.append(f"- Mounting: {props['mounting_type']}, Filter bank: {props.get('supports_filter_bank', False)}, Frame thickness: {props.get('compatible_filter_frame_thickness_mm', 'N/A')}mm")
            if props.get("compatible_filter_types"):
                sections.append(f"- Compatible filters: {props['compatible_filter_types']} - {props.get('filter_description', '')}")
            if props.get("material_exclusions"):
                sections.append(f"- Material exclusions: {props['material_exclusions']} ({props.get('material_exclusion_note', '')})")
            if props.get("available_depths_mm"):
                sections.append(f"- Available depths: {props['available_depths_mm']}mm")
            if props.get("source_conflicts"):
                for sc in props["source_conflicts"]:
                    sections.append(f"- SOURCE CONFLICT: {sc}")

            # Materials
            mats = rec.get("materials", [])
            mats = [m for m in mats if m.get("code")]
            if mats:
                mat_strs = []
                for m in mats:
                    s = m["code"]
                    if m.get("is_default"):
                        s += " (default)"
                    elif m.get("on_request"):
                        s += " (on request)"
                    mat_strs.append(s)
                sections.append(f"- Available materials: {', '.join(mat_strs)}")

            # Lengths
            lens = rec.get("lengths", [])
            lens = [l for l in lens if l.get("mm")]
            if lens:
                len_strs = []
                for l in lens:
                    pg = l['mm']
                    f40 = l.get('f40_mm')
                    s = f"{pg}/{f40}mm (PG/F40)" if f40 and f40 != pg else f"{pg}mm"
                    if l.get("order_code_length"):
                        s += f" [code: {l['order_code_length']}]"
                    if l.get("max_cartridge_length"):
                        s += f" [max cartridge length {l['max_cartridge_length']}mm]"
                    elif l.get("max_filter_depth"):
                        s += f" [max filter depth {l['max_filter_depth']}mm]"
                    if l.get("compatibility_modes"):
                        s += f" [modes: {l['compatibility_modes']}]"
                    if l.get("description"):
                        s += f" - {l['description']}"
                    if l.get("is_default"):
                        s += " [default]"
                    len_strs.append(s)
                sections.append(f"- Length variants: {', '.join(len_strs)}")

            # Options
            opts = rec.get("options", [])
            opts = [o for o in opts if o.get("code") or o.get("name")]
            if opts:
                opt_strs = []
                for o in opts:
                    s = f"{o.get('name', '')} (code: {o.get('code', 'N/A')})"
                    if o.get("length_variant_link"):
                        s += f" [length: {o['length_variant_link']}]"
                    opt_strs.append(s)
                sections.append(f"- Options: {', '.join(opt_strs)}")

            # Features
            feats = rec.get("features", [])
            feats = [f for f in feats if f.get("name")]
            if feats:
                feat_strs = [f"{f.get('name', '')} (values: {f.get('values', 'N/A')})" for f in feats]
                sections.append(f"- Variable features: {', '.join(feat_strs)}")

            # Standard features
            std_feats = rec.get("standard_features", [])
            std_feats = [f for f in std_feats if f]
            if std_feats:
                sections.append(f"- Standard features: {', '.join(std_feats)}")

            sections.append("")

    # 2. DimensionModules (sizes + airflow + weights + all properties) grouped by family
    dm_records = result_to_dicts(graph.query("""
        MATCH (pf:ProductFamily)-[:AVAILABLE_IN_SIZE]->(dm:DimensionModule)
        RETURN pf.name AS family, pf.id AS family_id,
               dm.width_mm AS width, dm.height_mm AS height,
               dm.reference_airflow_m3h AS airflow,
               dm.unit_weight_kg AS weight,
               dm.reference_length_mm AS ref_length,
               dm.reference_length_f40_mm AS ref_length_f40,
               dm.reference_length_long_mm AS ref_length_long,
               dm.reference_length_long_f40_mm AS ref_length_long_f40,
               dm.unit_weight_kg_750 AS weight_750,
               dm.unit_weight_kg_900 AS weight_900,
               dm.unit_weight_kg_600 AS weight_600,
               dm.unit_weight_kg_850 AS weight_850,
               dm.unit_weight_kg_1100 AS weight_1100,
               dm.cartridge_count AS cartridge_count,
               dm.nippelmatt_mm AS nippelmatt,
               dm.standard_length_mm AS std_length,
               dm.filter_module_quarter AS fm_quarter,
               dm.filter_module_half AS fm_half,
               dm.filter_module_full AS fm_full,
               dm.round_duct_diameter_mm AS duct_diameter,
               dm.depth_mm AS depth,
               dm.pff_frame_count AS pff_frames,
               dm.pff_frame_size AS pff_frame_size,
               dm.passar_filter_width AS passar_w,
               dm.passar_filter_height AS passar_h,
               dm.exact_width_mm AS exact_w,
               dm.exact_height_mm AS exact_h,
               dm.data_quality_flag AS dq_flag,
               dm.data_quality_note AS dq_note
        ORDER BY pf.name, dm.width_mm, dm.height_mm
    """))

    if dm_records:
        sections.append("## DIMENSION MODULES / SIZES (Layer 1)\n")
        current_family = None
        for rec in dm_records:
            if rec["family"] != current_family:
                current_family = rec["family"]
                sections.append(f"\n### {current_family}")
                fam_recs = [r for r in dm_records if r["family"] == current_family]
                has_dual_weight = any(r.get("weight_750") or r.get("weight_900") or r.get("weight_600") or r.get("weight_850") or r.get("weight_1100") for r in fam_recs)
                has_cartridge = any(r.get("cartridge_count") for r in fam_recs)
                has_nippelmatt = any(r.get("nippelmatt") for r in fam_recs)
                has_modules = any(r.get("fm_full") is not None for r in fam_recs)
                has_duct = any(r.get("duct_diameter") for r in fam_recs)
                has_depth = any(r.get("depth") for r in fam_recs)
                has_pff = any(r.get("pff_frames") for r in fam_recs)
                has_passar = any(r.get("passar_w") for r in fam_recs)
                has_exact = any(r.get("exact_w") for r in fam_recs)

                header = "| Size (WxH) | Airflow (m³/h) | Weight (kg) | Ref Length PG/F40 (mm) |"
                sep = "|------------|----------------|-------------|------------------------|"
                if has_dual_weight:
                    long_len = ""
                    for r in fam_recs:
                        if r.get("weight_750"): long_len = "750"; break
                        if r.get("weight_900"): long_len = "900"; break
                        if r.get("weight_850"): long_len = "850"; break
                        if r.get("weight_1100"): long_len = "1100"; break
                    wt_label = f" Weight Long (kg {long_len}) |" if long_len else " Weight Long (kg) |"
                    header += wt_label
                    sep += "-" * (len(wt_label) - 2) + "|"
                if has_cartridge:
                    header += " Cartridges |"
                    sep += "------------|"
                if has_nippelmatt:
                    header += " Nippelmått Ø (mm) | Std Length (mm) |"
                    sep += "--------------------|-----------------|"
                if has_modules:
                    header += " Modules (¼/½/1) |"
                    sep += "------------------|"
                if has_duct:
                    header += " Duct Ø (mm) |"
                    sep += "--------------|"
                if has_depth:
                    header += " Depth (mm) |"
                    sep += "-------------|"
                if has_pff:
                    header += " PFF Frames | PFF Size |"
                    sep += "------------|----------|"
                if has_passar:
                    header += " Passar Filter |"
                    sep += "---------------|"
                if has_exact:
                    header += " Exact (BxH) |"
                    sep += "--------------|"
                sections.append(header)
                sections.append(sep)

            w = rec.get("width", "?")
            h = rec.get("height", "?")
            af = rec.get("airflow", "N/A")
            wt = rec.get("weight", "N/A")
            rl = rec.get("ref_length", "N/A")
            rl_f40 = rec.get("ref_length_f40", "")
            ref_str = f"{rl}" + (f"/{rl_f40}" if rl_f40 else "")
            rl_long = rec.get("ref_length_long", "")
            rl_long_f40 = rec.get("ref_length_long_f40", "")
            if rl_long:
                ref_str += f" & {rl_long}" + (f"/{rl_long_f40}" if rl_long_f40 else "")

            row = f"| {w}x{h} | {af} | {wt} | {ref_str} |"

            if has_dual_weight:
                wt2 = rec.get("weight_750") or rec.get("weight_900") or rec.get("weight_600") or rec.get("weight_850") or rec.get("weight_1100") or "N/A"
                row += f" {wt2} |"
            if has_cartridge:
                row += f" {rec.get('cartridge_count', 'N/A')} |"
            if has_nippelmatt:
                row += f" {rec.get('nippelmatt', 'N/A')} | {rec.get('std_length', 'N/A')} |"
            if has_modules:
                fmq = rec.get("fm_quarter", 0) or 0
                fmh = rec.get("fm_half", 0) or 0
                fmf = rec.get("fm_full", 0) or 0
                row += f" {fmq}/{fmh}/{fmf} |"
            if has_duct:
                row += f" {rec.get('duct_diameter', 'N/A')} |"
            if has_depth:
                row += f" {rec.get('depth', 'N/A')} |"
            if has_pff:
                row += f" {rec.get('pff_frames', 'N/A')} | {rec.get('pff_frame_size', 'N/A')} |"
            if has_passar:
                pw = rec.get('passar_w', '')
                ph = rec.get('passar_h', '')
                row += f" {pw}x{ph} |" if pw else " N/A |"
            if has_exact:
                ew = rec.get('exact_w', '')
                eh = rec.get('exact_h', '')
                row += f" {ew}x{eh} |" if ew else " N/A |"
            if rec.get('dq_flag'):
                row += f" ⚠ {rec['dq_flag']}"
                if rec.get('dq_note'):
                    row += f" ({rec['dq_note']})"

            sections.append(row)
        sections.append("")

    # 3. Materials table
    mat_records = result_to_dicts(graph.query("""
        MATCH (m:Material)
        RETURN m.code AS code, m.name AS name,
               m.corrosion_class AS corrosion_class,
               m.steel_specification AS steel_spec
        ORDER BY m.code
    """))

    if mat_records:
        sections.append("## MATERIALS IN GRAPH (Layer 1)\n")
        sections.append("| Code | Name | Corrosion Class | Steel Spec |")
        sections.append("|------|------|----------------|------------|")
        for rec in mat_records:
            sections.append(f"| {rec.get('code', '?')} | {rec.get('name', '?')} | {rec.get('corrosion_class', '?')} | {rec.get('steel_spec', '-')} |")
        sections.append("")

    # 4. Capacity rules (cartridge counts)
    cap_records = result_to_dicts(graph.query("""
        MATCH (pf:ProductFamily)-[:HAS_CAPACITY]->(cr:CapacityRule)
        RETURN pf.name AS family,
               cr.module_descriptor AS module_descriptor,
               cr.cartridge_count AS cartridge_count,
               cr.capacity_per_component AS capacity_per_component
        ORDER BY pf.name, cr.module_descriptor
    """))

    if cap_records:
        sections.append("## CAPACITY RULES (Layer 1)\n")
        sections.append("| Family | Module | Cartridge Count | Capacity/Component |")
        sections.append("|--------|--------|-----------------|--------------------|")
        for rec in cap_records:
            sections.append(f"| {rec.get('family', '?')} | {rec.get('module_descriptor', '?')} | {rec.get('cartridge_count', '?')} | {rec.get('capacity_per_component', '?')} |")
        sections.append("")

    # 5. Environments
    env_records = result_to_dicts(graph.query("""
        MATCH (e:Environment)
        RETURN e.id AS id, e.name AS name, e.keywords AS keywords,
               e.temperature_variation AS temp_var,
               e.humidity_exposure AS humidity
        ORDER BY e.id
    """))

    if env_records:
        sections.append("## ENVIRONMENTS (Layer 2)\n")
        for rec in env_records:
            kw = rec.get("keywords", [])
            kw_str = f" (keywords: {', '.join(kw)})" if kw else ""
            sections.append(f"- **{rec.get('id', '?')}**: {rec.get('name', '?')}{kw_str}")
        sections.append("")

    # 6. Applications
    app_records = result_to_dicts(graph.query("""
        MATCH (a:Application)
        RETURN a.id AS id, a.name AS name, a.keywords AS keywords
        ORDER BY a.id
    """))

    if app_records:
        sections.append("## APPLICATIONS (Layer 2)\n")
        for rec in app_records:
            kw = rec.get("keywords", [])
            kw_str = f" (keywords: {', '.join(kw)})" if kw else ""
            sections.append(f"- **{rec.get('id', '?')}**: {rec.get('name', '?')}{kw_str}")
        sections.append("")

    # 7. Environmental Stressors
    stressor_records = result_to_dicts(graph.query("""
        MATCH (es:EnvironmentalStressor)
        RETURN es.id AS id, es.name AS name, es.severity AS severity,
               es.demands AS demands
        ORDER BY es.id
    """))

    if stressor_records:
        sections.append("## ENVIRONMENTAL STRESSORS (Layer 2)\n")
        for rec in stressor_records:
            demands = rec.get("demands", "N/A")
            sections.append(f"- **{rec.get('name', '?')}** ({rec.get('severity', '?')}): {demands}")
        sections.append("")

    # 8. Installation Constraints
    ic_records = result_to_dicts(graph.query("""
        MATCH (ic:InstallationConstraint)
        RETURN ic.id AS id, ic.name AS name, ic.type AS type,
               ic.description AS description
        ORDER BY ic.id
    """))

    if ic_records:
        sections.append("## INSTALLATION CONSTRAINTS (Layer 2)\n")
        for rec in ic_records:
            sections.append(f"- **{rec.get('name', '?')}** (type: {rec.get('type', '?')}): {rec.get('description', 'N/A')}")
        sections.append("")

    # 9. Dependency Rules
    dep_records = result_to_dicts(graph.query("""
        MATCH (dr:DependencyRule)
        RETURN dr.id AS id, dr.name AS name, dr.description AS description
        ORDER BY dr.id
    """))

    if dep_records:
        sections.append("## DEPENDENCY RULES (Layer 2)\n")
        for rec in dep_records:
            sections.append(f"- **{rec.get('name', '?')}**: {rec.get('description', 'N/A')}")
        sections.append("")

    # 10. Node type counts (individual queries — FalkorDB doesn't support CALL {} subqueries)
    node_labels = [
        "ProductFamily", "DimensionModule", "Material", "Environment",
        "Application", "EnvironmentalStressor", "CapacityRule", "DependencyRule",
        "InstallationConstraint", "Stressor", "CausalRule", "AssemblyRule",
        "Trait", "SizeProperty",
    ]
    count_records = []
    for label in sorted(node_labels):
        rows = result_to_dicts(graph.query(
            f"MATCH (n:{label}) RETURN '{label}' AS label, count(n) AS cnt"
        ))
        if rows:
            count_records.append(rows[0])

    if count_records:
        sections.append("## NODE TYPE COUNTS\n")
        sections.append("| Node Type | Count |")
        sections.append("|-----------|-------|")
        for rec in count_records:
            sections.append(f"| {rec['label']} | {rec['cnt']} |")
        sections.append("")

    return "\n".join(sections)


@dataclass
class GraphAuditConfig:
    """Configuration for a graph audit debate session."""
    selected_providers: list[str] = field(default_factory=lambda: ["openai", "gemini_pro", "anthropic_opus"])
    audit_scope: str = "full"  # "full", "layer1", "layer2"


class GraphAuditOrchestrator:
    """Orchestrates the 3-round multi-LLM graph audit debate."""

    def __init__(
        self,
        providers: list[LLMProvider],
        pdf_bytes: bytes,
        graph_data_str: str,
        pdf_mime_type: str = "application/pdf",
        config: Optional[GraphAuditConfig] = None,
    ):
        self.providers = {p.name: p for p in providers}
        self.pdf_bytes = pdf_bytes
        self.graph_data_str = graph_data_str
        self.pdf_mime_type = pdf_mime_type
        self.config = config or GraphAuditConfig()
        self.audit_results: dict[str, dict] = {}
        self.critiques: dict[str, dict] = {}
        self.final_report: Optional[dict] = None
        self.session_id = str(uuid.uuid4())[:8]
        self._executor = ThreadPoolExecutor(max_workers=3)

    async def _run_provider(self, provider: LLMProvider, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Run a provider call in the thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            provider.generate,
            system_prompt,
            user_prompt,
            self.pdf_bytes,
            self.pdf_mime_type,
            16384,   # max_tokens — audit responses are large
            0.1,     # temperature — low for factual accuracy
        )

    async def run_debate(self) -> AsyncGenerator[dict, None]:
        """Run the full 3-round audit debate, yielding SSE events."""
        debate_start = time.time()
        provider_names = list(self.providers.keys())

        yield {"type": "audit_start", "session_id": self.session_id,
               "providers": provider_names, "total_rounds": 3}

        # ── Round 1: INDEPENDENT AUDIT (parallel) ─────────────────────
        yield {"type": "phase", "phase": "audit", "status": "started",
               "description": "Each LLM independently audits the knowledge graph against the PDF catalog"}

        audit_user_prompt = AUDIT_USER_PROMPT_TEMPLATE.format(graph_data=self.graph_data_str)

        audit_tasks = {}
        for name, provider in self.providers.items():
            yield {"type": "provider_progress", "provider": name,
                   "phase": "audit", "status": "active"}
            audit_tasks[name] = asyncio.create_task(
                self._run_provider(provider, AUDIT_SYSTEM_PROMPT, audit_user_prompt)
            )

        for name, task in audit_tasks.items():
            try:
                response = await asyncio.wait_for(task, timeout=300)
                if response.error:
                    yield {"type": "provider_error", "provider": name,
                           "phase": "audit", "error": response.error}
                    continue

                logger.info(f"[AUDIT] {name} response ({len(response.content)} chars): {response.content[:500]}")
                parsed = _parse_json_safe(response.content, name)
                if parsed is None or not isinstance(parsed, dict):
                    logger.error(f"[AUDIT] {name} JSON parse FAILED. Content:\n{response.content[:2000]}")
                    yield {"type": "provider_error", "provider": name,
                           "phase": "audit", "error": "Failed to parse audit JSON"}
                    continue

                self.audit_results[name] = parsed
                findings = parsed.get("findings", [])
                severity_breakdown = {}
                for f in findings:
                    sev = f.get("severity", "UNKNOWN")
                    severity_breakdown[sev] = severity_breakdown.get(sev, 0) + 1

                yield {"type": "audit_finding", "provider": name,
                       "findings_count": len(findings),
                       "severity_breakdown": severity_breakdown,
                       "overall_score": parsed.get("overall_score", 0),
                       "duration_s": response.duration_s}
                yield {"type": "provider_progress", "provider": name,
                       "phase": "audit", "status": "complete",
                       "data": {"findings_count": len(findings),
                                "overall_score": parsed.get("overall_score", 0),
                                "duration_s": response.duration_s}}

            except asyncio.TimeoutError:
                yield {"type": "provider_error", "provider": name,
                       "phase": "audit", "error": "Timed out after 300s"}
            except Exception as e:
                yield {"type": "provider_error", "provider": name,
                       "phase": "audit", "error": str(e)}

        total_findings = sum(
            len(r.get("findings", [])) for r in self.audit_results.values()
        )
        yield {"type": "phase", "phase": "audit", "status": "complete",
               "data": {"providers_completed": list(self.audit_results.keys()),
                        "total_findings": total_findings}}

        if not self.audit_results:
            yield {"type": "error", "detail": "All providers failed in audit round. Cannot continue."}
            return

        # ── Round 2: CROSS-CRITIQUE (parallel) ────────────────────────
        if len(self.audit_results) >= 2:
            yield {"type": "phase", "phase": "critique", "status": "started",
                   "description": "Each LLM reviews the other evaluators' findings"}

            critique_tasks = {}
            for name, provider in self.providers.items():
                if name not in self.audit_results:
                    continue

                own_findings = json.dumps(self.audit_results[name], indent=2, ensure_ascii=False)
                others = {k: v for k, v in self.audit_results.items() if k != name}
                other_text = ""
                for other_name, other_result in others.items():
                    # Truncate to fit context
                    other_json = json.dumps(other_result, indent=2, ensure_ascii=False)[:8000]
                    other_text += f"\n\n--- {other_name} AUDIT ---\n{other_json}"

                critique_user = CRITIQUE_PROMPT.format(
                    own_findings=own_findings[:8000],
                    other_findings=other_text,
                )

                yield {"type": "provider_progress", "provider": name,
                       "phase": "critique", "status": "active"}
                critique_tasks[name] = asyncio.create_task(
                    self._run_provider(
                        provider,
                        "You are reviewing audit findings from multiple evaluators. The PDF catalog is attached as ground truth.",
                        critique_user,
                    )
                )

            for name, task in critique_tasks.items():
                try:
                    response = await asyncio.wait_for(task, timeout=300)
                    if response.error:
                        yield {"type": "provider_error", "provider": name,
                               "phase": "critique", "error": response.error}
                        continue

                    parsed = _parse_json_safe(response.content, name)
                    if parsed is None:
                        yield {"type": "provider_error", "provider": name,
                               "phase": "critique", "error": "Failed to parse critique JSON"}
                        continue

                    self.critiques[name] = parsed
                    confirmed = parsed.get("confirmed_findings", []) if isinstance(parsed, dict) else []
                    challenged = parsed.get("challenged_findings", []) if isinstance(parsed, dict) else []
                    new_findings = parsed.get("new_findings", []) if isinstance(parsed, dict) else []

                    yield {"type": "critique_result", "critic": name,
                           "confirmed_count": len(confirmed),
                           "challenged_count": len(challenged),
                           "new_count": len(new_findings),
                           "consensus_score": parsed.get("consensus_score", 0),
                           "duration_s": response.duration_s}
                    yield {"type": "provider_progress", "provider": name,
                           "phase": "critique", "status": "complete",
                           "data": {"confirmed": len(confirmed),
                                    "challenged": len(challenged),
                                    "new": len(new_findings),
                                    "duration_s": response.duration_s}}

                except asyncio.TimeoutError:
                    yield {"type": "provider_error", "provider": name,
                           "phase": "critique", "error": "Timed out after 300s"}
                except Exception as e:
                    yield {"type": "provider_error", "provider": name,
                           "phase": "critique", "error": str(e)}

            yield {"type": "phase", "phase": "critique", "status": "complete",
                   "data": {"critics_completed": list(self.critiques.keys())}}
        else:
            yield {"type": "phase", "phase": "critique", "status": "skipped",
                   "description": "Only 1 provider available — skipping cross-critique"}

        # ── Round 3: CONSENSUS SYNTHESIS (sequential) ─────────────────
        yield {"type": "phase", "phase": "synthesis", "status": "started",
               "description": "Merging all audit findings and critiques into a consensus report"}

        # Pick synthesizer (prefer Claude Opus > Gemini Pro > OpenAI)
        synth_priority = ["anthropic_opus", "gemini_pro", "openai"]
        synthesizer_name = None
        synthesizer = None
        for pname in synth_priority:
            if pname in self.providers and pname in self.audit_results:
                synthesizer_name = pname
                synthesizer = self.providers[pname]
                break

        if not synthesizer:
            synthesizer_name = list(self.audit_results.keys())[0]
            synthesizer = self.providers[synthesizer_name]

        yield {"type": "provider_progress", "provider": synthesizer_name,
               "phase": "synthesis", "status": "active"}

        synth_user = SYNTHESIS_PROMPT.format(
            n_providers=len(self.audit_results),
            all_findings=json.dumps(
                {k: v for k, v in self.audit_results.items()}, indent=2, ensure_ascii=False
            ),
            all_critiques=json.dumps(
                {k: v for k, v in self.critiques.items()}, indent=2, ensure_ascii=False
            ) if self.critiques else "No critiques available (single-provider mode).",
        )

        try:
            response = await asyncio.wait_for(
                self._run_provider(
                    synthesizer,
                    "You are the lead auditor producing the final consensus report. The PDF catalog is attached as ground truth.",
                    synth_user,
                ),
                timeout=300,
            )

            if response.error:
                yield {"type": "provider_error", "provider": synthesizer_name,
                       "phase": "synthesis", "error": response.error}
                self.final_report = self._fallback_report()
            else:
                parsed = _parse_json_safe(response.content, synthesizer_name)
                if parsed and isinstance(parsed, dict):
                    self.final_report = parsed
                else:
                    self.final_report = self._fallback_report()

                yield {"type": "provider_progress", "provider": synthesizer_name,
                       "phase": "synthesis", "status": "complete",
                       "data": {"total_findings": len(self.final_report.get("findings", [])),
                                "overall_score": self.final_report.get("overall_score", 0),
                                "duration_s": response.duration_s}}

        except asyncio.TimeoutError:
            yield {"type": "provider_error", "provider": synthesizer_name,
                   "phase": "synthesis", "error": "Timed out after 300s"}
            self.final_report = self._fallback_report()

        total_duration = round(time.time() - debate_start, 1)

        yield {"type": "phase", "phase": "synthesis", "status": "complete",
               "data": {"total_findings": len(self.final_report.get("findings", []))}}

        # ── Save report ───────────────────────────────────────────────
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"graph_audit_debate_{timestamp}.json"
        report_path = os.path.join(REPORTS_DIR, report_filename)

        full_report = {
            "meta": {
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat(),
                "providers": list(self.audit_results.keys()),
                "synthesizer": synthesizer_name,
                "duration_s": total_duration,
                "audit_scope": self.config.audit_scope,
            },
            "round1_audits": self.audit_results,
            "round2_critiques": self.critiques,
            "final_report": self.final_report,
        }

        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(full_report, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"[AUDIT] Report saved to {report_path}")
        except Exception as e:
            logger.error(f"[AUDIT] Failed to save report: {e}")

        # ── Final events ──────────────────────────────────────────────
        severity_breakdown = {}
        for finding in self.final_report.get("findings", []):
            sev = finding.get("severity", "UNKNOWN")
            severity_breakdown[sev] = severity_breakdown.get(sev, 0) + 1

        yield {"type": "result", "report": self.final_report,
               "summary": {
                   "total_findings": len(self.final_report.get("findings", [])),
                   "overall_score": self.final_report.get("overall_score", 0),
                   "confidence": self.final_report.get("confidence", 0),
                   "severity_breakdown": severity_breakdown,
                   "providers_used": list(self.audit_results.keys()),
                   "critiques_completed": list(self.critiques.keys()),
                   "synthesizer": synthesizer_name,
                   "duration_s": total_duration,
                   "report_file": report_filename,
               }}

        yield {"type": "audit_complete", "session_id": self.session_id,
               "total_findings": len(self.final_report.get("findings", [])),
               "overall_score": self.final_report.get("overall_score", 0),
               "confidence": self.final_report.get("confidence", 0),
               "duration_s": total_duration}

    def _fallback_report(self) -> dict:
        """Build a fallback report from raw audit results when synthesis fails."""
        all_findings = []
        fid = 1
        for provider_name, result in self.audit_results.items():
            for finding in result.get("findings", []):
                finding["id"] = fid
                finding["confidence"] = 0.5
                finding["agreed_by"] = [provider_name]
                finding["challenged_by"] = []
                all_findings.append(finding)
                fid += 1

        scores = [r.get("overall_score", 50) for r in self.audit_results.values()]
        avg_score = round(sum(scores) / len(scores)) if scores else 50

        return {
            "overall_score": avg_score,
            "confidence": 0.4,
            "total_findings": len(all_findings),
            "findings": all_findings,
            "recommendations": ["Synthesis failed — review individual audit results manually"],
            "summary": "Synthesis round failed. This report contains raw unmerged findings from individual auditors.",
        }
