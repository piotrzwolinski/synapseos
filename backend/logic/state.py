"""Technical State Manager for Cumulative Engineering Specifications.

This module manages persistent state across conversation turns, ensuring:
1. Parameters are never forgotten once established
2. Decisions (material, project) are locked and persist
3. Multi-tag specifications are tracked separately
4. Housing length is auto-resolved from filter depth

The state acts as a "Cumulative Engineering Specification" that grows with each turn.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class MaterialCode(str, Enum):
    """Material codes for housing variants."""
    RF = "RF"  # Stainless Steel (Rostfri)
    FZ = "FZ"  # Galvanized
    ZM = "ZM"  # Zinc-Magnesium
    SF = "SF"  # Sendzimir


@dataclass
class TagSpecification:
    """Specification for a single tag/item in the engineering request."""
    tag_id: str

    # Filter dimensions (from user input)
    filter_width: Optional[int] = None   # e.g., 305 -> maps to 300 housing
    filter_height: Optional[int] = None  # e.g., 610 -> maps to 600 housing
    filter_depth: Optional[int] = None   # e.g., 292mm

    # Housing dimensions (derived from filter)
    housing_width: Optional[int] = None   # e.g., 300
    housing_height: Optional[int] = None  # e.g., 600
    housing_length: Optional[int] = None  # e.g., 550 (auto-derived from depth)

    # Performance requirements
    airflow_m3h: Optional[int] = None

    # Product selection
    product_family: Optional[str] = None  # GDB, GDC, GDP, GDMI
    product_code: Optional[str] = None    # Full code: GDB-300x600-550-R-PG-RF

    # Additional specs
    quantity: int = 1
    weight_kg: Optional[float] = None

    # Multi-module aggregation (from sizing arrangement)
    modules_needed: int = 1                    # Parallel units from sizing arrangement
    total_weight_kg: Optional[float] = None    # weight_kg × modules_needed
    total_airflow_m3h: Optional[int] = None    # airflow_m3h × modules_needed
    rated_airflow_m3h: Optional[int] = None    # Catalog rated capacity per module (from DimensionModule)

    # Material (per-tag override when global locked_material is incompatible)
    material_override: Optional[str] = None   # e.g., "AZ" if locked "FZ" isn't available for this tag's family

    # Assembly membership (multi-stage filtration)
    assembly_role: Optional[str] = None       # "PROTECTOR" or "TARGET"
    assembly_group_id: Optional[str] = None   # Links sibling assembly tags

    # Derived/computed flags
    is_complete: bool = False
    missing_params: list[str] = field(default_factory=list)

    def get_housing_size_string(self) -> Optional[str]:
        """Get housing size as WxH string."""
        if self.housing_width and self.housing_height:
            return f"{self.housing_width}x{self.housing_height}"
        return None

    def compute_housing_from_filter(self):
        """Map filter dimensions to standard housing sizes."""
        # Standard mapping: filter dimension -> housing dimension
        DIMENSION_MAP = {
            # Width/Height mappings
            287: 300, 305: 300, 300: 300,
            592: 600, 610: 600, 600: 600,
            495: 500, 500: 500,
        }

        if self.filter_width:
            self.housing_width = DIMENSION_MAP.get(self.filter_width, self.filter_width)
        if self.filter_height:
            self.housing_height = DIMENSION_MAP.get(self.filter_height, self.filter_height)

        # Apply orientation normalization after mapping
        self.normalize_orientation()

    def normalize_orientation(self):
        """Normalize housing dimensions to enforce HVAC industry standard.

        HVAC RULE: For small modular housings (up to 600x600), the LARGER
        dimension is ALWAYS the HEIGHT (vertical). This is critical for:
        - 305x610 filter → 300x600 housing → 600mm is HEIGHT (vertical)
        - 610x305 filter → 300x600 housing → 600mm is HEIGHT (vertical)

        For larger housings (any dimension > 600mm), the orientation is
        determined by the sizing arrangement and user constraints (e.g.,
        max_height_mm), so we do NOT swap.
        """
        if not self.housing_width or not self.housing_height:
            return

        # Only apply orientation normalization for small modular sizes
        # where industry convention dictates height >= width.
        # For larger modules (e.g., 1800x900), the sizing engine
        # determines orientation based on spatial constraints.
        if self.housing_width <= 600 and self.housing_height <= 600:
            if self.housing_width > self.housing_height:
                self.housing_width, self.housing_height = self.housing_height, self.housing_width
                if self.filter_width and self.filter_height:
                    if self.filter_width > self.filter_height:
                        self.filter_width, self.filter_height = self.filter_height, self.filter_width

    def compute_housing_length_from_depth(self):
        """Auto-derive housing length from filter depth using engineering rules.

        Only runs when housing_length is not already explicitly set.

        Rules (from inventory/engineering specs):
        - depth <= 150mm -> length = 550mm
        - 150 < depth <= 292mm -> length = 550mm
        - 292 < depth <= 450mm -> length = 750mm
        - depth > 450mm -> length = 900mm
        """
        if self.housing_length is not None:
            return
        if self.filter_depth is None:
            return

        if self.filter_depth <= 292:
            self.housing_length = 550
        elif self.filter_depth <= 450:
            self.housing_length = 750
        else:
            self.housing_length = 900

    def check_completeness(self) -> tuple[bool, list[str]]:
        """Check if specification is complete for product selection."""
        missing = []

        if not self.housing_width or not self.housing_height:
            if not self.filter_width or not self.filter_height:
                missing.append("filter_dimensions")

        if not self.housing_length:
            if not self.filter_depth:
                missing.append("filter_depth")

        if not self.airflow_m3h:
            missing.append("airflow")

        self.missing_params = missing
        self.is_complete = len(missing) == 0
        return self.is_complete, missing


@dataclass
class TechnicalState:
    """Cumulative technical state for an engineering session.

    This state persists across conversation turns and is never lost.
    New information is MERGED, never replaced.
    """

    # Project-level locks
    project_name: Optional[str] = None
    locked_material: Optional[MaterialCode] = None

    # Per-tag specifications
    tags: dict[str, TagSpecification] = field(default_factory=dict)

    # Session metadata
    turn_count: int = 0
    last_resolved_params: list[str] = field(default_factory=list)

    # Product family detection
    detected_family: Optional[str] = None  # GDB, GDC, etc.

    # Accessories
    accessories: list[str] = field(default_factory=list)

    # Pending clarification tracking (what parameter we just asked about)
    pending_clarification: Optional[str] = None  # e.g., "airflow", "filter_depth"

    # Generic resolved parameters (graph-driven, keyed by property_key from Parameter nodes)
    # Stores answers to gate/engine clarifications that don't map to dedicated fields
    resolved_params: dict[str, str] = field(default_factory=dict)

    # Assembly tracking (multi-stage filtration)
    assembly_group: Optional[dict] = None
    # Structure: {"group_id": "assembly_item_1", "rationale": "...",
    #   "stages": [{"role": "PROTECTOR", "product_family": "GDP", "tag_id": "item_1_stage_1"}, ...]}

    # Veto persistence: product families vetoed by the engine (persisted across turns)
    vetoed_families: list[str] = field(default_factory=list)
    # e.g., ["FAM_GDC_FLEX"] — engine veto for this session, remembered on continuation turns

    def merge_tag(self, tag_id: str, **kwargs) -> TagSpecification:
        """Merge new data into a tag specification.

        IMPORTANT: Only updates fields that are None or explicitly provided.
        Never overwrites existing data with None.
        """
        if tag_id not in self.tags:
            self.tags[tag_id] = TagSpecification(tag_id=tag_id)

        tag = self.tags[tag_id]

        for key, value in kwargs.items():
            if value is not None:
                # Only update if value is provided
                if hasattr(tag, key):
                    current = getattr(tag, key)
                    # Don't overwrite with None, but do update with new values
                    setattr(tag, key, value)

        # Auto-compute derived values
        tag.compute_housing_from_filter()
        tag.compute_housing_length_from_depth()
        tag.check_completeness()

        # If this tag is part of an assembly, sync shared params to siblings
        if tag.assembly_group_id and self.assembly_group:
            self._sync_assembly_params()

        return tag

    def create_assembly_tags(self, assembly_stages: list, base_tag_id: str = "item_1") -> None:
        """Create stage-prefixed tags from engine assembly verdict.

        Naming: item_1_stage_1 (PROTECTOR), item_1_stage_2 (TARGET), etc.
        All stages share dimensions + airflow (synced from base tag).
        """
        group_id = f"assembly_{base_tag_id}"
        stages_meta = []

        # Collect shared params from existing base tag before deletion
        base_tag = self.tags.get(base_tag_id)
        shared = {}
        if base_tag:
            for attr in ('filter_width', 'filter_height', 'filter_depth',
                          'housing_width', 'housing_height', 'housing_length',
                          'airflow_m3h'):
                val = getattr(base_tag, attr, None)
                if val is not None:
                    shared[attr] = int(val) if isinstance(val, (int, float)) else val

        for i, stage in enumerate(assembly_stages, 1):
            tag_id = f"{base_tag_id}_stage_{i}"
            pf_name = getattr(stage, 'product_family_name', '') or ''
            if not pf_name:
                pf_id = getattr(stage, 'product_family_id', '') or ''
                pf_name = pf_id.replace("FAM_", "")
            # Normalize: "GDP Planfilterskåp" → "GDP" (strip descriptive suffix)
            if ' ' in pf_name:
                pf_name = pf_name.split()[0]

            self.merge_tag(tag_id, product_family=pf_name, **shared)
            tag = self.tags[tag_id]
            tag.assembly_role = getattr(stage, 'role', None)
            tag.assembly_group_id = group_id

            stages_meta.append({
                "role": getattr(stage, 'role', ''),
                "product_family": pf_name,
                "tag_id": tag_id,
                "provides_trait": getattr(stage, 'provides_trait_name', ''),
                "reason": getattr(stage, 'reason', ''),
            })

        # Remove the old base tag (replaced by stage-prefixed tags)
        if base_tag_id in self.tags:
            del self.tags[base_tag_id]

        self.assembly_group = {
            "group_id": group_id,
            "rationale": "",
            "stages": stages_meta,
        }

    def _sync_assembly_params(self) -> None:
        """Sync shared parameters across assembly siblings (in-flight working copy).

        Which properties to sync is read from domain_config.yaml (assembly.shared_properties),
        not hardcoded. The Graph layer also enforces this sync via Cypher in upsert_tag().
        Always casts to int for type safety.
        """
        if not self.assembly_group:
            return

        stage_tag_ids = [s["tag_id"] for s in self.assembly_group.get("stages", [])]
        stage_tags = [self.tags[tid] for tid in stage_tag_ids if tid in self.tags]
        if not stage_tags:
            return

        # Read shared property list from domain config — no hardcoded property names
        try:
            from backend.config_loader import get_config
            config = get_config()
            sync_attrs = tuple(config.assembly_shared_properties)
        except Exception:
            # Fallback: empty list means no sync (safe default)
            sync_attrs = ()

        if not sync_attrs:
            return

        # Find the "best" (first non-None) value from any stage and propagate to siblings
        for attr in sync_attrs:
            best = next((getattr(t, attr) for t in stage_tags if getattr(t, attr, None)), None)
            if best is not None:
                best = int(best)
                for tag in stage_tags:
                    if getattr(tag, attr, None) is None:
                        setattr(tag, attr, best)

    def lock_material(self, material: str):
        """Lock material code. Once locked, cannot be changed."""
        if self.locked_material is None:
            try:
                self.locked_material = MaterialCode(material.upper())
            except ValueError:
                # Unknown material code, try to map
                MATERIAL_ALIASES = {
                    'STAINLESS': MaterialCode.RF,
                    'STAINLESS STEEL': MaterialCode.RF,
                    'ROSTFRI': MaterialCode.RF,
                    'NIERDZEWNA': MaterialCode.RF,
                    'GALVANIZED': MaterialCode.FZ,
                    'ZINC': MaterialCode.FZ,
                    'CYNK': MaterialCode.FZ,
                }
                self.locked_material = MATERIAL_ALIASES.get(material.upper())

    def set_project(self, project_name: str):
        """Set project name. Once set, persists."""
        if self.project_name is None:
            self.project_name = project_name

    def get_all_missing_params(self) -> dict[str, list[str]]:
        """Get missing parameters per tag."""
        return {
            tag_id: tag.missing_params
            for tag_id, tag in self.tags.items()
            if tag.missing_params
        }

    def all_tags_complete(self) -> bool:
        """Check if all tags have complete specifications."""
        if not self.tags:
            return False
        return all(tag.is_complete for tag in self.tags.values())

    def to_prompt_context(self) -> str:
        """Generate context string for LLM prompt injection.

        This generates a VERY EXPLICIT context that the LLM cannot ignore.
        It includes strong prohibition rules to prevent state drift.
        """
        lines = []

        # =====================================================================
        # CRITICAL HEADER: Make the LLM understand this is non-negotiable
        # =====================================================================
        lines.append("## 🔒 CUMULATIVE PROJECT STATE (ABSOLUTE TRUTH - CANNOT BE CHANGED)")
        lines.append("")
        lines.append("**You are managing a project specification sheet. The data below is LOCKED.**")
        lines.append("**You MUST use this data exactly. Do NOT ask for information already provided.**")
        lines.append("")

        # =====================================================================
        # LOCKED PARAMETERS: These CANNOT be overwritten
        # =====================================================================
        if self.project_name or self.locked_material or self.detected_family:
            lines.append("### 📌 LOCKED PARAMETERS (IMMUTABLE)")
            lines.append("")

            if self.project_name:
                lines.append(f"- **Project:** {self.project_name}")
            if self.locked_material:
                lines.append(f"- **Material:** {self.locked_material.value} ← USE THIS IN ALL PRODUCT CODES")
                lines.append(f"  ⛔ PROHIBITION: Do NOT use FZ if RF is specified. Do NOT revert to default.")
            if self.detected_family:
                lines.append(f"- **Product Family:** {self.detected_family}")
            if self.accessories:
                lines.append(f"- **Accessories:** {', '.join(self.accessories)}")
            if self.resolved_params:
                for rp_key, rp_val in self.resolved_params.items():
                    lines.append(f"- **{rp_key}:** {rp_val}")
                    lines.append(f"  ✓ KNOWN: DO NOT ask for {rp_key}")
            lines.append("")

        # =====================================================================
        # VETOED FAMILIES: Products vetoed by the engine (persisted)
        # =====================================================================
        if self.vetoed_families:
            family_names = [fid.replace("FAM_", "") for fid in self.vetoed_families]
            lines.append("### 🚫 VETOED PRODUCT FAMILIES (ENGINEERING VETO — DO NOT RECOMMEND)")
            lines.append("")
            for fn in family_names:
                lines.append(f"- **{fn}** — VETOED due to environmental incompatibility")
            lines.append("")
            lines.append("⛔ PROHIBITION: Do NOT recommend or size these products.")
            lines.append("The veto was established by the engineering engine and is NON-NEGOTIABLE.")
            lines.append("")

        # =====================================================================
        # TAG SPECIFICATIONS: Per-tag data
        # =====================================================================
        if self.tags:
            lines.append("### 📋 TAG SPECIFICATIONS (FROM USER INPUT)")
            lines.append("")

            for tag_id, tag in self.tags.items():
                lines.append(f"**Tag {tag_id}:**")

                if tag.filter_width and tag.filter_height:
                    depth_str = f"x{tag.filter_depth}mm" if tag.filter_depth else ""
                    lines.append(f"  - Filter Dimensions: {tag.filter_width}x{tag.filter_height}{depth_str}")
                    if tag.filter_depth:
                        lines.append(f"    ✓ Depth KNOWN: {tag.filter_depth}mm → DO NOT ask for filter depth")

                if tag.housing_width and tag.housing_height:
                    lines.append(f"  - Housing Size: {tag.housing_width}x{tag.housing_height}mm")
                    lines.append(f"    ✓ Dimensions KNOWN: {tag.housing_width}x{tag.housing_height}mm → DO NOT ask for duct dimensions")

                if tag.housing_length:
                    lines.append(f"  - Housing Length: {tag.housing_length}mm (auto-derived from depth)")
                    lines.append(f"    ✓ Length RESOLVED: DO NOT ask for housing length")

                if tag.airflow_m3h:
                    if tag.rated_airflow_m3h and tag.rated_airflow_m3h != tag.airflow_m3h:
                        lines.append(f"  - Rated Airflow: {tag.rated_airflow_m3h} m³/h per module (catalog)")
                        lines.append(f"  - Requested Airflow: {tag.airflow_m3h} m³/h")
                    elif tag.modules_needed > 1 and tag.total_airflow_m3h:
                        lines.append(f"  - Airflow: {tag.total_airflow_m3h} m³/h total ({tag.modules_needed}×{tag.airflow_m3h} per unit)")
                    else:
                        lines.append(f"  - Airflow: {tag.airflow_m3h} m³/h")
                    lines.append(f"    ✓ Airflow KNOWN: DO NOT ask for airflow")

                if tag.product_code:
                    lines.append(f"  - Product Code: {tag.product_code}")
                    lines.append(f"    ✓ USE THIS EXACT CODE in entity_card specs — do NOT compose your own")

                if tag.weight_kg:
                    if tag.modules_needed > 1 and tag.total_weight_kg:
                        lines.append(f"  - Weight: {tag.total_weight_kg} kg total ({tag.modules_needed}×{tag.weight_kg}kg per unit)")
                    else:
                        lines.append(f"  - Weight: {tag.weight_kg} kg (from graph)")

                if tag.modules_needed > 1:
                    lines.append(f"  - Parallel Units: {tag.modules_needed}")

                if tag.quantity > 1:
                    lines.append(f"  - Quantity: {tag.quantity}")

                # Status with explicit instructions
                if tag.is_complete:
                    lines.append(f"  - **Status: ✅ COMPLETE** → Ready for final answer")
                elif tag.missing_params:
                    only_missing = [p for p in tag.missing_params if p != 'housing_length']
                    if only_missing:
                        lines.append(f"  - **Status: ⏳ Missing:** {', '.join(only_missing)}")
                    else:
                        lines.append(f"  - **Status: ✅ COMPLETE** (length auto-derived)")

                lines.append("")

        # =====================================================================
        # PROHIBITION RULES: Explicit "do not" instructions
        # =====================================================================
        lines.append("### ⛔ STRICT PROHIBITIONS")
        lines.append("")
        lines.append("1. **NEVER ask for data shown above** - it's already known")
        lines.append("2. **NEVER revert material to FZ** if RF/ZM/SF was specified")
        lines.append("3. **NEVER ask for housing length** if filter depth is known (auto-derived)")
        lines.append("4. **NEVER ask for filter depth** if WxHxD format was provided")
        lines.append("5. **ALWAYS use locked material suffix** in product codes (e.g., -RF not -FZ)")
        lines.append("6. **ALWAYS acknowledge previous input** before asking new questions")
        lines.append("")

        # =====================================================================
        # DERIVATION RULES: How to compute missing values
        # =====================================================================
        lines.append("### 🔧 AUTO-DERIVATION RULES")
        lines.append("")
        lines.append("| If Known | Then Derive |")
        lines.append("|----------|-------------|")
        lines.append("| Filter Depth ≤292mm | Housing Length = 550mm |")
        lines.append("| Filter Depth ≤450mm | Housing Length = 750mm |")
        lines.append("| Filter Depth >450mm | Housing Length = 900mm |")
        lines.append("| Filter 305mm | Housing 300mm |")
        lines.append("| Filter 610mm | Housing 600mm |")
        lines.append("")

        # =====================================================================
        # ASSEMBLY CONTEXT: Multi-stage system tracking
        # =====================================================================
        if self.assembly_group:
            lines.append("### 🔗 MULTI-STAGE ASSEMBLY (ALL STAGES REQUIRED)")
            lines.append("")
            rationale = self.assembly_group.get("rationale", "Multi-stage system required")
            if rationale:
                lines.append(f"**Assembly Rationale:** {rationale}")
            lines.append("")
            for stage in self.assembly_group.get("stages", []):
                role = stage.get("role", "")
                pf = stage.get("product_family", "")
                tid = stage.get("tag_id", "")
                trait = stage.get("provides_trait", "")
                lines.append(f"- Stage ({role}): **{pf}** [Tag: {tid}] — {trait}")
            lines.append("")
            lines.append("**CRITICAL: ALL stages MUST be included in the final recommendation.**")
            lines.append("**Each stage gets its own entity_card in the response array.**")
            lines.append("**Shared dimensions and airflow apply to ALL stages.**")
            lines.append("")

        # =====================================================================
        # IMMEDIATE ACTION: When all data is known
        # =====================================================================
        if self.all_tags_complete():
            lines.append("### 🎯 ACTION REQUIRED: ALL DATA COMPLETE")
            lines.append("")
            lines.append("**EVERY TAG ABOVE HAS STATUS ✅ COMPLETE**")
            lines.append("")
            lines.append("You MUST output the final recommendation table NOW. DO NOT:")
            lines.append("- Ask for any additional information")
            lines.append("- Use filler phrases like 'let me confirm' or 'I understand'")
            lines.append("- Request clarification on dimensions, airflow, or material")
            lines.append("")
            lines.append("Simply output the product codes and weights as shown in the PRE-COMPUTED ANSWER section.")
            lines.append("")

        return "\n".join(lines)

        lines.append("")
        lines.append("**CRITICAL RULES:**")
        lines.append("- NEVER ask for parameters already shown above")
        lines.append("- Housing Length is AUTO-DERIVED from Filter Depth")
        lines.append("- Always include the locked material suffix in product codes")
        lines.append("- When all parameters are known, provide WEIGHT from graph data")

        return "\n".join(lines)

    def to_compact_summary(self) -> str:
        """Compact state summary for Semantic Scribe LLM prompt.

        Token-efficient representation of current state. Unlike to_prompt_context()
        which includes prohibition rules for the main LLM, this produces a minimal
        machine-readable summary for the extraction engine.
        """
        lines = []
        if self.locked_material:
            lines.append(f"Material: {self.locked_material.value}")
        if self.detected_family:
            lines.append(f"Product Family: {self.detected_family}")
        if self.project_name:
            lines.append(f"Project: {self.project_name}")
        for tag_id, tag in self.tags.items():
            parts = [f"{tag_id}:"]
            if tag.housing_width and tag.housing_height:
                parts.append(f"{tag.housing_width}x{tag.housing_height}mm")
            if tag.housing_length:
                parts.append(f"length={tag.housing_length}mm")
            if tag.airflow_m3h:
                parts.append(f"airflow={tag.airflow_m3h}m3/h")
            if tag.product_family:
                parts.append(f"family={tag.product_family}")
            if tag.assembly_role:
                parts.append(f"role={tag.assembly_role}")
            lines.append(" ".join(parts))
        for key, val in self.resolved_params.items():
            lines.append(f"Param {key}: {val}")
        if self.pending_clarification:
            lines.append(f"Pending question: {self.pending_clarification}")
        return "\n".join(lines) if lines else "(empty state)"

    def persist_to_graph(self, session_mgr, session_id: str) -> None:
        """Sync current Python state to the graph database.

        Writes all current state (project, material, tags) to Neo4j Layer 4.
        The graph becomes the source of truth.
        """
        session_mgr.ensure_session(session_id)

        if self.project_name:
            session_mgr.set_project(session_id, self.project_name)

        if self.locked_material:
            session_mgr.lock_material(session_id, self.locked_material.value)

        if self.detected_family:
            session_mgr.set_detected_family(session_id, self.detected_family)

        # Persist pending_clarification (even None to clear previous)
        session_mgr.set_pending_clarification(session_id, self.pending_clarification)

        # Persist accessories
        if self.accessories:
            session_mgr.set_accessories(session_id, self.accessories)

        # Persist generic resolved parameters (gate answers, etc.)
        if self.resolved_params:
            session_mgr.set_resolved_params(session_id, self.resolved_params)

        # Persist assembly group metadata
        if self.assembly_group:
            session_mgr.set_assembly_group(session_id, self.assembly_group)

        # Persist vetoed families (so continuation turns remember the veto)
        if self.vetoed_families:
            session_mgr.set_vetoed_families(session_id, self.vetoed_families)

        for tag_id, tag in self.tags.items():
            session_mgr.upsert_tag(
                session_id=session_id,
                tag_id=tag_id,
                filter_width=tag.filter_width,
                filter_height=tag.filter_height,
                filter_depth=tag.filter_depth,
                airflow_m3h=tag.airflow_m3h,
                product_family=tag.product_family,
                product_code=tag.product_code,
                weight_kg=tag.weight_kg,
                quantity=tag.quantity,
                source_message=self.turn_count,
                assembly_group_id=tag.assembly_group_id,
            )

    @classmethod
    def load_from_graph(cls, session_mgr, session_id: str) -> "TechnicalState":
        """Load state from the graph database into a Python TechnicalState object.

        The graph is the source of truth; this creates a working copy.
        """
        state_data = session_mgr.get_project_state(session_id)
        ts = cls()

        project = state_data.get("project")
        if project:
            if project.get("name"):
                ts.project_name = project["name"]
            if project.get("locked_material"):
                ts.lock_material(project["locked_material"])
            if project.get("detected_family"):
                ts.detected_family = project["detected_family"]
            if project.get("pending_clarification"):
                ts.pending_clarification = project["pending_clarification"]
            if project.get("resolved_params"):
                import json as _json
                rp = project["resolved_params"]
                if isinstance(rp, str):
                    rp = _json.loads(rp)
                ts.resolved_params = rp
            if project.get("accessories"):
                ts.accessories = project["accessories"]
            # Restore assembly group
            import logging as _log
            _log.getLogger(__name__).info(f"[LOAD] project keys: {list(project.keys()) if project else 'None'}, assembly_group raw: {project.get('assembly_group')!r}")
            if project.get("assembly_group"):
                import json
                ag = project["assembly_group"]
                if isinstance(ag, str):
                    ag = json.loads(ag)
                ts.assembly_group = ag
                _log.getLogger(__name__).info(f"[LOAD] Restored assembly_group with {len(ag.get('stages', []))} stages")
            # Restore vetoed families
            if project.get("vetoed_families"):
                import json as _json2
                vf = project["vetoed_families"]
                if isinstance(vf, str):
                    vf = _json2.loads(vf)
                ts.vetoed_families = vf
                _log.getLogger(__name__).info(f"[LOAD] Restored vetoed_families: {vf}")

        for tag_data in state_data.get("tags", []):
            tag_id = tag_data.get("tag_id", "unknown")
            ts.merge_tag(
                tag_id,
                filter_width=tag_data.get("filter_width"),
                filter_height=tag_data.get("filter_height"),
                filter_depth=tag_data.get("filter_depth"),
                housing_length=tag_data.get("housing_length"),
                airflow_m3h=tag_data.get("airflow_m3h"),
                product_family=tag_data.get("product_family"),
                product_code=tag_data.get("product_code"),
                weight_kg=tag_data.get("weight_kg"),
                quantity=tag_data.get("quantity"),
            )

        # Restore assembly_role on loaded tags from assembly_group metadata
        if ts.assembly_group:
            for stage in ts.assembly_group.get("stages", []):
                tid = stage.get("tag_id")
                if tid in ts.tags:
                    ts.tags[tid].assembly_role = stage.get("role")
                    ts.tags[tid].assembly_group_id = ts.assembly_group.get("group_id")

        return ts

    def to_dict(self) -> dict:
        """Serialize state for API response."""
        return {
            "project_name": self.project_name,
            "locked_material": self.locked_material.value if self.locked_material else None,
            "detected_family": self.detected_family,
            "accessories": self.accessories,
            "pending_clarification": self.pending_clarification,
            "resolved_params": self.resolved_params,
            "assembly_group": self.assembly_group,
            "turn_count": self.turn_count,
            "tags": {
                tag_id: {
                    "tag_id": tag.tag_id,
                    "filter_width": tag.filter_width,
                    "filter_height": tag.filter_height,
                    "filter_depth": tag.filter_depth,
                    "housing_width": tag.housing_width,
                    "housing_height": tag.housing_height,
                    "housing_length": tag.housing_length,
                    "airflow_m3h": tag.airflow_m3h,
                    "product_family": tag.product_family,
                    "product_code": tag.product_code,
                    "quantity": tag.quantity,
                    "weight_kg": tag.weight_kg,
                    "modules_needed": tag.modules_needed,
                    "total_weight_kg": tag.total_weight_kg,
                    "total_airflow_m3h": tag.total_airflow_m3h,
                    "is_complete": tag.is_complete,
                    "missing_params": tag.missing_params,
                    "assembly_role": tag.assembly_role,
                    "assembly_group_id": tag.assembly_group_id,
                }
                for tag_id, tag in self.tags.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TechnicalState":
        """Deserialize state from API request."""
        state = cls()

        state.project_name = data.get("project_name")
        if data.get("locked_material"):
            try:
                state.locked_material = MaterialCode(data["locked_material"])
            except ValueError:
                pass
        state.detected_family = data.get("detected_family")
        state.accessories = data.get("accessories", [])
        state.pending_clarification = data.get("pending_clarification")
        state.resolved_params = data.get("resolved_params", {})
        state.assembly_group = data.get("assembly_group")
        state.turn_count = data.get("turn_count", 0)

        for tag_id, tag_data in data.get("tags", {}).items():
            tag = TagSpecification(tag_id=tag_id)
            tag.filter_width = tag_data.get("filter_width")
            tag.filter_height = tag_data.get("filter_height")
            tag.filter_depth = tag_data.get("filter_depth")
            tag.housing_width = tag_data.get("housing_width")
            tag.housing_height = tag_data.get("housing_height")
            tag.housing_length = tag_data.get("housing_length")
            tag.airflow_m3h = tag_data.get("airflow_m3h")
            tag.product_family = tag_data.get("product_family")
            tag.product_code = tag_data.get("product_code")
            tag.quantity = tag_data.get("quantity", 1)
            tag.weight_kg = tag_data.get("weight_kg")
            tag.modules_needed = tag_data.get("modules_needed", 1)
            tag.total_weight_kg = tag_data.get("total_weight_kg")
            tag.total_airflow_m3h = tag_data.get("total_airflow_m3h")
            tag.assembly_role = tag_data.get("assembly_role")
            tag.assembly_group_id = tag_data.get("assembly_group_id")
            # Don't use stored is_complete/missing_params - recompute them
            # BUGFIX: Ensure derived values are computed if missing
            if not tag.housing_width or not tag.housing_height:
                tag.compute_housing_from_filter()
            if not tag.housing_length and tag.filter_depth:
                tag.compute_housing_length_from_depth()
            tag.check_completeness()
            state.tags[tag_id] = tag

        return state

    @classmethod
    def from_locked_context(cls, locked_context: dict) -> "TechnicalState":
        """Initialize state from frontend locked context."""
        state = cls()

        if locked_context.get("project"):
            state.project_name = locked_context["project"]

        if locked_context.get("material"):
            state.lock_material(locked_context["material"])

        if locked_context.get("filter_depths"):
            # Filter depths are known but not yet assigned to tags
            pass

        if locked_context.get("dimension_mappings"):
            # Process dimension mappings into tags
            for i, mapping in enumerate(locked_context["dimension_mappings"]):
                tag_id = f"auto_{i+1}"
                state.merge_tag(
                    tag_id,
                    filter_width=mapping.get("width"),
                    filter_height=mapping.get("height"),
                    filter_depth=mapping.get("depth")
                )

        return state

    def build_product_code(self, tag: TagSpecification, code_format=None) -> str:
        """Build a product code using a graph-supplied template.

        The code_format comes from ProductFamily.code_format in the graph.
        Accepts either a string template or a dict with 'fmt' and optional
        'default_frame_depth' (for GDP-style codes where the code uses frame
        depth instead of housing length).

        Python fills {placeholder} tokens from tag state — no domain logic here.
        Falls back to a generic '{family}-{width}x{height}' if no template found.
        """
        # Unpack dict format (from updated get_product_family_code_format)
        fmt_str = None
        default_frame_depth = None
        if isinstance(code_format, dict):
            fmt_str = code_format.get("fmt")
            default_frame_depth = code_format.get("default_frame_depth")
        elif isinstance(code_format, str):
            fmt_str = code_format

        family = (tag.product_family or self.detected_family or "").replace("_", "-")
        material = tag.material_override or (self.locked_material.value if self.locked_material else "FZ")
        connection = self.resolved_params.get("connection_type", "PG")

        # Apply connection-specific length offset (e.g., Flange adds 50mm)
        length = int(tag.housing_length or 0)
        length_offset = int(self.resolved_params.get("connection_length_offset", 0))
        effective_length = length + length_offset if length else 0

        # Frame depth for GDP-style codes (Ram Djup: 25/50/100mm)
        frame_depth = self.resolved_params.get("frame_depth") or default_frame_depth or ""

        placeholders = {
            "family": family,
            "width": str(tag.housing_width or ""),
            "height": str(tag.housing_height or ""),
            "length": str(effective_length) if effective_length else "",
            "frame_depth": str(int(frame_depth)) if frame_depth else "",
            "material": material,
            "connection": connection,
        }

        if fmt_str:
            try:
                result = fmt_str.format(**placeholders)
                # Clean up double-dashes from empty placeholders (e.g., missing length)
                while '--' in result:
                    result = result.replace('--', '-')
                return result
            except KeyError:
                pass  # Fall through to generic

        # Generic fallback: family-WxH[-length]
        parts = [family]
        if tag.housing_width and tag.housing_height:
            parts.append(f"{tag.housing_width}x{tag.housing_height}")
        if tag.housing_length:
            parts.append(str(tag.housing_length))
        return "-".join(parts)

    def enrich_with_weights(self, db) -> None:
        """Look up weights from graph for all complete tags.

        Weight resolution order (v3.8 — family-specific first):
        1. ProductVariant exact match (AUTHORITATIVE — family-specific data)
        2. DimensionModule parametric model (FALLBACK — for sizes not in variant table)
        """
        for tag_id, tag in self.tags.items():
            if tag.is_complete and not tag.weight_kg:
                # Build product code if not set
                if not tag.product_code:
                    fam = tag.product_family or self.detected_family or ""
                    fam_id = f"FAM_{fam}" if fam and not fam.startswith("FAM_") else fam
                    code_fmt = db.get_product_family_code_format(fam_id) if fam_id else None
                    tag.product_code = self.build_product_code(tag, code_format=code_fmt)

                # PRIMARY: ProductVariant exact match (family-specific, authoritative)
                fam_name = tag.product_family or self.detected_family or ""
                if fam_name and tag.housing_width and tag.housing_height:
                    if tag.housing_length:
                        variant_key = f"{fam_name}-{tag.housing_width}x{tag.housing_height}-{tag.housing_length}"
                        weight = db.get_variant_weight(variant_key)
                        if weight:
                            tag.weight_kg = weight
                    if not tag.weight_kg:
                        variant_key = f"{fam_name}-{tag.housing_width}x{tag.housing_height}"
                        weight = db.get_variant_weight(variant_key)
                        if weight:
                            tag.weight_kg = weight

                # FALLBACK: DimensionModule parametric model
                if not tag.weight_kg and tag.housing_width and tag.housing_height:
                    dm_weight = db.get_dimension_module_weight(tag.housing_width, tag.housing_height)
                    if dm_weight and dm_weight.get("unit_weight_kg"):
                        base = dm_weight["unit_weight_kg"]
                        per_mm = dm_weight.get("weight_per_mm_length") or 0
                        ref_length = dm_weight.get("reference_length_mm") or 550
                        actual_length = tag.housing_length or ref_length
                        tag.weight_kg = round(base + (actual_length - ref_length) * per_mm, 1)

            # Guard: rebuild product code if it has double-dashes (stale from earlier turn)
            if tag.product_code and '--' in tag.product_code and tag.housing_length:
                fam = tag.product_family or self.detected_family or ""
                fam_id = f"FAM_{fam}" if fam and not fam.startswith("FAM_") else fam
                code_fmt = db.get_product_family_code_format(fam_id) if fam_id else None
                tag.product_code = self.build_product_code(tag, code_format=code_fmt)

            # Aggregate for multi-module arrangements
            if tag.weight_kg and tag.modules_needed > 1:
                tag.total_weight_kg = round(tag.weight_kg * tag.modules_needed, 1)
            else:
                tag.total_weight_kg = tag.weight_kg

            if tag.airflow_m3h and tag.modules_needed > 1:
                tag.total_airflow_m3h = tag.airflow_m3h * tag.modules_needed
            else:
                tag.total_airflow_m3h = tag.airflow_m3h

    def verify_material_codes(self) -> list[str]:
        """Verify all product codes use the locked material suffix.

        Returns:
            List of warning messages for mismatched codes
        """
        warnings = []

        if not self.locked_material:
            return warnings

        expected_suffix = f"-{self.locked_material.value}"

        for tag_id, tag in self.tags.items():
            if tag.product_code:
                if not tag.product_code.endswith(expected_suffix):
                    warnings.append(
                        f"Tag {tag_id}: Product code '{tag.product_code}' "
                        f"does not end with locked material '{expected_suffix}'"
                    )

        return warnings

    def generate_b2b_response(self) -> str:
        """Generate a structured B2B response for multi-item quotes.

        Format:
        - One header per project
        - Per-tag bullet points with specs
        - Weights MUST be included
        """
        lines = []

        if self.project_name:
            lines.append(f"## Configuration for {self.project_name} Project")
            lines.append("")

        if self.locked_material:
            lines.append(f"**Material:** {self.locked_material.value} (Locked)")
            lines.append("")

        for tag_id, tag in self.tags.items():
            lines.append(f"### Tag {tag_id}")

            if tag.product_code:
                lines.append(f"- **Product Code:** {tag.product_code}")
            elif tag.is_complete:
                # Build code if complete but not set
                tag.product_code = self.build_product_code(tag)
                lines.append(f"- **Product Code:** {tag.product_code}")

            if tag.housing_width and tag.housing_height:
                lines.append(f"- **Housing Size:** {tag.housing_width}x{tag.housing_height}mm")

            if tag.housing_length:
                lines.append(f"- **Housing Length:** {tag.housing_length}mm")

            if tag.airflow_m3h:
                if tag.rated_airflow_m3h and tag.rated_airflow_m3h != tag.airflow_m3h:
                    lines.append(f"- **Rated Airflow:** {tag.rated_airflow_m3h} m³/h per module (requested: {tag.airflow_m3h} m³/h)")
                elif tag.rated_airflow_m3h:
                    lines.append(f"- **Rated Airflow:** {tag.rated_airflow_m3h} m³/h")
                else:
                    lines.append(f"- **Airflow Capacity:** {tag.airflow_m3h} m³/h")

            if tag.weight_kg:
                lines.append(f"- **Weight:** {tag.weight_kg} kg")
            else:
                lines.append(f"- **Weight:** (lookup required)")

            if tag.modules_needed > 1:
                lines.append(f"- **Modules Required:** {tag.modules_needed} parallel units")
                if tag.total_weight_kg:
                    lines.append(f"- **Total Weight:** {tag.total_weight_kg} kg ({tag.modules_needed}×{tag.weight_kg} kg)")

            if tag.quantity > 1:
                lines.append(f"- **Quantity:** {tag.quantity}")

            if not tag.is_complete and tag.missing_params:
                lines.append(f"- **Status:** Missing: {', '.join(tag.missing_params)}")
            else:
                lines.append(f"- **Status:** Complete")

            lines.append("")

        return "\n".join(lines)


def _normalize_numeric_in_text(text: str) -> str:
    """Normalize thousand-separated numbers in text for regex extraction.

    Handles comma (25,000), space (25 000), and dot-as-thousand (25.000) separators.
    Does NOT touch dimension patterns like 600x600.
    """
    import re
    # Comma thousand separator: 6,000 or 25,000
    text = re.sub(r'(\d{1,3}),(\d{3})\b', r'\1\2', text)
    # Space thousand separator: 6 000 or 25 000
    text = re.sub(r'(\d{1,3})\s(\d{3})\b', r'\1\2', text)
    return text


def extract_tags_from_query(query: str) -> list[dict]:
    """FALLBACK: Regex-based tag/dimension extraction. Only called when Scribe LLM
    fails or returns no entities.

    Parses patterns like:
    - "Tag 5684: 305x610x150, Tag 7889: 610x610x292"
    - "Item A: 300x600 filter 150mm deep"
    - "25,000 m³/h" (comma-separated thousands)
    """
    import re

    # Normalize thousands separators BEFORE any regex matching
    query = _normalize_numeric_in_text(query)

    tags = []

    # Pattern 1: "Tag XXXX: WxHxD" or "Tag XXXX - WxHxD" (supports x, ×, X separators)
    tag_pattern = r'(?:tag|item|pos(?:ition)?)\s*[:#\-]?\s*(\w+)[:\-\s]+(\d{2,4})[x\u00d7X](\d{2,4})(?:[x\u00d7X](\d{2,4}))?'
    matches = re.findall(tag_pattern, query, re.IGNORECASE)

    for match in matches:
        tag_id, w, h, d = match
        tags.append({
            "tag_id": tag_id,
            "filter_width": int(w),
            "filter_height": int(h),
            "filter_depth": int(d) if d else None
        })

    # Pattern 2: Standalone dimensions with implied single tag (supports x, ×, X separators)
    if not tags:
        dim_pattern = r'(\d{2,4})[x\u00d7X](\d{2,4})(?:[x\u00d7X](\d{2,4}))?(?:\s*mm)?'
        dim_matches = re.findall(dim_pattern, query)

        for i, match in enumerate(dim_matches):
            w, h, d = match
            tags.append({
                "tag_id": f"item_{i+1}",
                "filter_width": int(w),
                "filter_height": int(h),
                "filter_depth": int(d) if d else None
            })

    # Pattern 3: Airflow specification (relaxed: also match m³, m3h without slash)
    # Supports up to 6 digits (up to 999,999 m³/h) after normalization
    airflow_pattern = r'(\d{3,6})\s*(?:m³/h|m3/h|m³|cbm|cubic|m3h)'
    airflow_matches = re.findall(airflow_pattern, query, re.IGNORECASE)

    # If we have airflow values and tags, try to match them
    if airflow_matches and tags:
        for i, airflow in enumerate(airflow_matches):
            if i < len(tags):
                tags[i]["airflow_m3h"] = int(airflow)

    return tags


def extract_material_from_query(query: str) -> Optional[str]:
    """FALLBACK: Regex-based material extraction. Only called when Scribe LLM
    fails or returns no material for this field.

    Uses word-boundary regex to avoid substring false positives
    (e.g. 'rf' matching inside 'airflow').
    """
    import re
    query_lower = query.lower()

    # Order: check longer/multi-word keywords first, then short codes
    MATERIAL_PATTERNS = {
        'RF': ['stainless steel', 'stainless', 'nierdzewna', 'rostfri', 'edelstahl', 'inox', 'rf'],
        'FZ': ['galvanized', 'verzinkt', 'zinc', 'cynk', 'fz'],
        'ZM': ['zinkmagnesium', 'magnelis', 'zm'],
        'SF': ['sendzimir', 'sf'],
    }

    for mat_code, keywords in MATERIAL_PATTERNS.items():
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', query_lower):
                return mat_code

    return None


def extract_project_from_query(query: str) -> Optional[str]:
    """FALLBACK: Regex-based project name extraction. Only called when Scribe LLM
    fails or returns no project_name."""
    import re

    patterns = [
        r'(?:project|projekt|for|dla)\s+([A-Z][a-zA-Z0-9]+)',
        r'([A-Z][a-zA-Z0-9]+)\s+project',
    ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def extract_accessories_from_query(query: str) -> list[str]:
    """FALLBACK: Regex-based accessory extraction. Only called when Scribe LLM
    fails or returns no accessories.

    Detects:
    - Round duct connections: "Ø500mm", "500mm round duct", "circular duct 500"
    - Transition pieces: "transition piece", "reducer", "adapter"
    """
    import re
    accessories = []

    # Round duct connections: Ø500, Ø500mm, 500mm round duct, round ducts (500mm diameter)
    duct_patterns = [
        r'[ØO\u2300]\s*(\d{2,4})\s*(?:mm)?',                                          # Ø500mm
        r'(\d{2,4})\s*mm\s+round\s+(?:ducts?|connections?|pipes?)',                    # 500mm round duct(s)
        r'round\s+(?:ducts?|connections?|pipes?)\s*\(?(\d{2,4})\s*(?:mm)?\s*(?:diameter)?\)?', # round ducts (500mm diameter)
        r'circular\s+(?:ducts?|connections?|pipes?)\s*\(?(\d{2,4})',                    # circular duct(s) (500
        r'(\d{2,4})\s*mm\s+(?:circular|round)\s+(?:ducts?|connections?|pipes?)',        # 500mm circular duct(s)
        r'(\d{2,4})\s*mm\s+diameter\s+(?:round|circular)?\s*(?:ducts?|pipes?)',        # 500mm diameter round ducts
        r'(?:round|circular)\s+(?:ducts?|pipes?)\s+(?:of\s+|with\s+)?(\d{2,4})\s*mm', # round ducts of 500mm
    ]
    for pattern in duct_patterns:
        matches = re.findall(pattern, query, re.IGNORECASE)
        for m in matches:
            acc = f"Round duct \u00d8{m}mm"
            if acc not in accessories:
                accessories.append(acc)

    # Transition/reducer mentions (only if not already captured via duct diameter)
    transition_patterns = [
        r'transition\s+piece',
        r'reducer',
        r'adapter',
    ]
    for pattern in transition_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            if not any('Round duct' in a for a in accessories):
                accessories.append("Transition piece (type TBD)")

    return accessories
