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

logger = logging.getLogger(__name__)

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def build_graph_data_snapshot(db_connection) -> str:
    """Query Neo4j for all Layer 1 & 2 data and format as a structured markdown string."""
    driver = db_connection.connect()
    sections = []

    with driver.session(database=db_connection.database) as session:
        # 1. Product Families with materials
        pf_records = session.run("""
            MATCH (pf:ProductFamily)
            OPTIONAL MATCH (pf)-[r:AVAILABLE_IN_MATERIAL]->(m:Material)
            WITH pf, collect(DISTINCT {code: m.code, is_default: r.is_default}) AS materials
            OPTIONAL MATCH (pf)-[:HAS_LENGTH_VARIANT]->(vl)
            WITH pf, materials, collect(DISTINCT {mm: vl.mm, max_filter_depth: vl.max_filter_depth, is_default: vl.is_default}) AS lengths
            OPTIONAL MATCH (pf)-[:HAS_OPTION]->(opt)
            WITH pf, materials, lengths, collect(DISTINCT {code: opt.code, name: opt.name}) AS options
            OPTIONAL MATCH (pf)-[:HAS_VARIABLE_FEATURE]->(vf)
            RETURN pf, materials, lengths, options,
                   collect(DISTINCT {name: vf.feature_name, property_key: vf.property_key, values: vf.allowed_values}) AS features
            ORDER BY pf.selection_priority
        """).data()

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

                # Materials
                mats = rec.get("materials", [])
                mats = [m for m in mats if m.get("code")]
                if mats:
                    mat_strs = []
                    for m in mats:
                        s = m["code"]
                        if m.get("is_default"):
                            s += " (default)"
                        mat_strs.append(s)
                    sections.append(f"- Available materials: {', '.join(mat_strs)}")

                # Lengths
                lens = rec.get("lengths", [])
                lens = [l for l in lens if l.get("mm")]
                if lens:
                    len_strs = []
                    for l in lens:
                        s = f"{l['mm']}mm"
                        if l.get("max_filter_depth"):
                            s += f" (max filter depth {l['max_filter_depth']}mm)"
                        if l.get("is_default"):
                            s += " [default]"
                        len_strs.append(s)
                    sections.append(f"- Length variants: {', '.join(len_strs)}")

                # Options
                opts = rec.get("options", [])
                opts = [o for o in opts if o.get("code") or o.get("name")]
                if opts:
                    opt_strs = [f"{o.get('name', '')} ({o.get('code', '')})" for o in opts]
                    sections.append(f"- Options: {', '.join(opt_strs)}")

                # Features
                feats = rec.get("features", [])
                feats = [f for f in feats if f.get("name")]
                if feats:
                    feat_strs = [f.get("name", "") for f in feats]
                    sections.append(f"- Variable features: {', '.join(feat_strs)}")

                sections.append("")

        # 2. DimensionModules (sizes + airflow + weights) grouped by family
        dm_records = session.run("""
            MATCH (pf:ProductFamily)-[:AVAILABLE_IN_SIZE]->(dm:DimensionModule)
            RETURN pf.name AS family, pf.id AS family_id,
                   dm.width_mm AS width, dm.height_mm AS height,
                   dm.reference_airflow_m3h AS airflow,
                   dm.unit_weight_kg AS weight,
                   dm.reference_length_mm AS ref_length
            ORDER BY pf.name, dm.width_mm, dm.height_mm
        """).data()

        if dm_records:
            sections.append("## DIMENSION MODULES / SIZES (Layer 1)\n")
            current_family = None
            for rec in dm_records:
                if rec["family"] != current_family:
                    current_family = rec["family"]
                    sections.append(f"\n### {current_family}")
                    sections.append("| Size (WxH) | Airflow (m³/h) | Weight (kg) | Ref Length (mm) |")
                    sections.append("|------------|----------------|-------------|-----------------|")
                w = rec.get("width", "?")
                h = rec.get("height", "?")
                af = rec.get("airflow", "N/A")
                wt = rec.get("weight", "N/A")
                rl = rec.get("ref_length", "N/A")
                sections.append(f"| {w}x{h} | {af} | {wt} | {rl} |")
            sections.append("")

        # 3. Materials table
        mat_records = session.run("""
            MATCH (m:Material)
            RETURN m.code AS code, m.name AS name,
                   m.corrosion_class AS corrosion_class,
                   m.max_chlorine_ppm AS max_chlorine_ppm
            ORDER BY m.code
        """).data()

        if mat_records:
            sections.append("## MATERIALS IN GRAPH (Layer 1)\n")
            sections.append("| Code | Name | Corrosion Class | Max Chlorine PPM |")
            sections.append("|------|------|----------------|------------------|")
            for rec in mat_records:
                sections.append(f"| {rec.get('code', '?')} | {rec.get('name', '?')} | {rec.get('corrosion_class', '?')} | {rec.get('max_chlorine_ppm', '?')} |")
            sections.append("")

        # 4. Capacity rules (cartridge counts)
        cap_records = session.run("""
            MATCH (pf:ProductFamily)-[:HAS_CAPACITY]->(cr:CapacityRule)
            RETURN pf.name AS family,
                   cr.module_descriptor AS module_descriptor,
                   cr.cartridge_count AS cartridge_count,
                   cr.capacity_per_component AS capacity_per_component
            ORDER BY pf.name, cr.module_descriptor
        """).data()

        if cap_records:
            sections.append("## CAPACITY RULES (Layer 1)\n")
            sections.append("| Family | Module | Cartridge Count | Capacity/Component |")
            sections.append("|--------|--------|-----------------|--------------------|")
            for rec in cap_records:
                sections.append(f"| {rec.get('family', '?')} | {rec.get('module_descriptor', '?')} | {rec.get('cartridge_count', '?')} | {rec.get('capacity_per_component', '?')} |")
            sections.append("")

        # 5. Environments
        env_records = session.run("""
            MATCH (e:Environment)
            RETURN e.id AS id, e.name AS name, e.keywords AS keywords,
                   e.temperature_variation AS temp_var,
                   e.humidity_exposure AS humidity
            ORDER BY e.id
        """).data()

        if env_records:
            sections.append("## ENVIRONMENTS (Layer 2)\n")
            for rec in env_records:
                kw = rec.get("keywords", [])
                kw_str = f" (keywords: {', '.join(kw)})" if kw else ""
                sections.append(f"- **{rec.get('id', '?')}**: {rec.get('name', '?')}{kw_str}")
            sections.append("")

        # 6. Applications
        app_records = session.run("""
            MATCH (a:Application)
            RETURN a.id AS id, a.name AS name, a.keywords AS keywords
            ORDER BY a.id
        """).data()

        if app_records:
            sections.append("## APPLICATIONS (Layer 2)\n")
            for rec in app_records:
                kw = rec.get("keywords", [])
                kw_str = f" (keywords: {', '.join(kw)})" if kw else ""
                sections.append(f"- **{rec.get('id', '?')}**: {rec.get('name', '?')}{kw_str}")
            sections.append("")

        # 7. Environmental Stressors
        stressor_records = session.run("""
            MATCH (es:EnvironmentalStressor)
            RETURN es.id AS id, es.name AS name, es.severity AS severity,
                   es.demands AS demands
            ORDER BY es.id
        """).data()

        if stressor_records:
            sections.append("## ENVIRONMENTAL STRESSORS (Layer 2)\n")
            for rec in stressor_records:
                demands = rec.get("demands", "N/A")
                sections.append(f"- **{rec.get('name', '?')}** ({rec.get('severity', '?')}): {demands}")
            sections.append("")

        # 8. Installation Constraints
        ic_records = session.run("""
            MATCH (ic:InstallationConstraint)
            RETURN ic.id AS id, ic.name AS name, ic.type AS type,
                   ic.description AS description
            ORDER BY ic.id
        """).data()

        if ic_records:
            sections.append("## INSTALLATION CONSTRAINTS (Layer 2)\n")
            for rec in ic_records:
                sections.append(f"- **{rec.get('name', '?')}** (type: {rec.get('type', '?')}): {rec.get('description', 'N/A')}")
            sections.append("")

        # 9. Dependency Rules
        dep_records = session.run("""
            MATCH (dr:DependencyRule)
            RETURN dr.id AS id, dr.name AS name, dr.description AS description
            ORDER BY dr.id
        """).data()

        if dep_records:
            sections.append("## DEPENDENCY RULES (Layer 2)\n")
            for rec in dep_records:
                sections.append(f"- **{rec.get('name', '?')}**: {rec.get('description', 'N/A')}")
            sections.append("")

        # 10. Node type counts (for completeness check)
        count_records = session.run("""
            CALL {
                MATCH (pf:ProductFamily) RETURN 'ProductFamily' AS label, count(pf) AS cnt
                UNION ALL
                MATCH (dm:DimensionModule) RETURN 'DimensionModule' AS label, count(dm) AS cnt
                UNION ALL
                MATCH (m:Material) RETURN 'Material' AS label, count(m) AS cnt
                UNION ALL
                MATCH (e:Environment) RETURN 'Environment' AS label, count(e) AS cnt
                UNION ALL
                MATCH (a:Application) RETURN 'Application' AS label, count(a) AS cnt
                UNION ALL
                MATCH (es:EnvironmentalStressor) RETURN 'EnvironmentalStressor' AS label, count(es) AS cnt
                UNION ALL
                MATCH (cr:CapacityRule) RETURN 'CapacityRule' AS label, count(cr) AS cnt
                UNION ALL
                MATCH (dr:DependencyRule) RETURN 'DependencyRule' AS label, count(dr) AS cnt
                UNION ALL
                MATCH (ic:InstallationConstraint) RETURN 'InstallationConstraint' AS label, count(ic) AS cnt
                UNION ALL
                MATCH (s:Stressor) RETURN 'Stressor' AS label, count(s) AS cnt
                UNION ALL
                MATCH (cr:CausalRule) RETURN 'CausalRule' AS label, count(cr) AS cnt
                UNION ALL
                MATCH (ar:AssemblyRule) RETURN 'AssemblyRule' AS label, count(ar) AS cnt
                UNION ALL
                MATCH (t:Trait) RETURN 'Trait' AS label, count(t) AS cnt
                UNION ALL
                MATCH (sp:SizeProperty) RETURN 'SizeProperty' AS label, count(sp) AS cnt
            }
            RETURN label, cnt ORDER BY label
        """).data()

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
