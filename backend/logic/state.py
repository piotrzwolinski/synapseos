"""Technical State Manager for Cumulative Engineering Specifications.

This module manages persistent state across conversation turns, ensuring:
1. Parameters are never forgotten once established
2. Decisions (material, project) are locked and persist
3. Multi-tag specifications are tracked separately
4. Housing length is auto-resolved from filter depth

The state acts as a "Cumulative Engineering Specification" that grows with each turn.
"""

from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum


class MaterialCode(str, Enum):
    """Material codes for product variants.

    DEPRECATED: Kept for backward compatibility. New code should use plain
    strings validated against config.material_codes_extended.
    Since this is a str enum, enum members compare equal to their string values,
    so existing comparisons with plain strings still work.
    """
    RF = "RF"
    FZ = "FZ"
    ZM = "ZM"
    SF = "SF"


@dataclass
class TagSpecification:
    """Specification for a single tag/item in the engineering request.

    Typed fields (filter_width, housing_width, etc.) are kept for backward
    compatibility. The `properties` dict provides a generic bag for any
    tenant-specific data. get_prop/set_prop unify access across both.
    """
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
    product_family: Optional[str] = None  # Product family identifier
    product_code: Optional[str] = None    # Full product code

    # Additional specs
    quantity: int = 1
    weight_kg: Optional[float] = None

    # Multi-module aggregation (from sizing arrangement)
    modules_needed: int = 1                    # Parallel units from sizing arrangement
    total_weight_kg: Optional[float] = None    # weight_kg × modules_needed
    total_airflow_m3h: Optional[int] = None    # airflow_m3h × modules_needed
    rated_airflow_m3h: Optional[int] = None    # Catalog rated capacity per module (from DimensionModule)

    # Material (per-tag override when global locked_material is incompatible)
    material_override: Optional[str] = None   # Override when global locked material is incompatible with this tag's family

    # Assembly membership (multi-stage filtration)
    assembly_role: Optional[str] = None       # "PROTECTOR" or "TARGET"
    assembly_group_id: Optional[str] = None   # Links sibling assembly tags

    # Derived/computed flags
    is_complete: bool = False
    missing_params: list[str] = field(default_factory=list)

    # Generic property bag — tenant-specific data stored here
    properties: dict[str, Any] = field(default_factory=dict)

    def get_prop(self, key: str, default: Any = None) -> Any:
        """Get a property value. Checks typed field first, then properties dict."""
        if hasattr(self, key) and key != "properties":
            val = getattr(self, key)
            if val is not None:
                return val
        return self.properties.get(key, default)

    def set_prop(self, key: str, value: Any) -> None:
        """Set a property value. Sets typed field if it exists, always sets in properties."""
        if hasattr(self, key) and key != "properties":
            setattr(self, key, value)
        self.properties[key] = value

    def get_housing_size_string(self) -> Optional[str]:
        """Get housing size as WxH string."""
        if self.housing_width and self.housing_height:
            return f"{self.housing_width}x{self.housing_height}"
        return None

    def compute_housing_from_filter(self):
        """Map filter dimensions to standard housing sizes."""
        from logic.dimension_tables import get_dimension_map
        dim_map = get_dimension_map()

        if self.filter_width:
            self.housing_width = dim_map.get(self.filter_width, self.filter_width)
        if self.filter_height:
            self.housing_height = dim_map.get(self.filter_height, self.filter_height)

        # Apply orientation normalization after mapping
        self.normalize_orientation()

    def normalize_orientation(self):
        """Normalize dimensions to enforce orientation standard.

        For small modular units (up to threshold), the LARGER dimension
        is ALWAYS the HEIGHT (vertical). For larger units the orientation
        is determined by the sizing arrangement and user constraints.
        Threshold loaded from domain config.
        """
        if not self.housing_width or not self.housing_height:
            return

        # Only apply orientation normalization for small modular sizes
        # where industry convention dictates height >= width.
        # For larger modules (e.g., 1800x900), the sizing engine
        # determines orientation based on spatial constraints.
        from logic.dimension_tables import get_orientation_threshold
        threshold = get_orientation_threshold()
        if self.housing_width <= threshold and self.housing_height <= threshold:
            if self.housing_width > self.housing_height:
                self.housing_width, self.housing_height = self.housing_height, self.housing_width
                if self.filter_width and self.filter_height:
                    if self.filter_width > self.filter_height:
                        self.filter_width, self.filter_height = self.filter_height, self.filter_width

    def compute_housing_length_from_depth(self):
        """Auto-derive housing length from filter depth using engineering rules.

        Only runs when housing_length is not already explicitly set.
        Uses unified family-specific derivation from dimension_tables.
        """
        if self.housing_length is not None:
            return
        if self.filter_depth is None:
            return

        from logic.dimension_tables import derive_housing_length
        from config_loader import get_config
        _default_family = get_config().default_product_family or ""
        self.housing_length = derive_housing_length(
            self.filter_depth, self.product_family or _default_family
        )

    def check_completeness(self) -> tuple[bool, list[str]]:
        """Check if specification is complete for product selection.

        Uses config.completeness_required if available, otherwise falls back
        to the legacy hardcoded logic (identical behavior for MH tenant).
        """
        try:
            from config_loader import get_config
            required = get_config().completeness_required
        except Exception:
            required = []

        if required:
            return self._check_completeness_from_config(required)
        return self._check_completeness_legacy()

    def _check_completeness_from_config(self, required: list[dict]) -> tuple[bool, list[str]]:
        """Config-driven completeness check.

        Each entry in required is a dict:
          {"key": "label", "fields": ["primary", "fallback1", ...]}
        The check passes if ANY field in the list has a truthy value.
        """
        missing = []
        for req in required:
            fields = req.get("fields", [])
            label = req.get("key", fields[0] if fields else "unknown")
            if not any(self.get_prop(f) for f in fields):
                missing.append(label)

        self.missing_params = missing
        self.is_complete = len(missing) == 0
        return self.is_complete, missing

    def _check_completeness_legacy(self) -> tuple[bool, list[str]]:
        """Legacy hardcoded completeness check (backward compat)."""
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
    locked_material: Optional[str] = None  # Plain string, validated against config codes

    # Per-tag specifications
    tags: dict[str, TagSpecification] = field(default_factory=dict)

    # Session metadata
    turn_count: int = 0
    last_resolved_params: list[str] = field(default_factory=list)

    # Product family detection
    detected_family: Optional[str] = None  # Detected from user query or graph

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
    #   "stages": [{"role": "PROTECTOR", "product_family": "FAMILY_X", "tag_id": "item_1_stage_1"}, ...]}

    # Veto persistence: product families vetoed by the engine (persisted across turns)
    vetoed_families: list[str] = field(default_factory=list)
    # e.g., ["FAM_EXAMPLE"] — engine veto for this session, remembered on continuation turns

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
                # Always mirror into the generic property bag
                tag.properties[key] = value

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
            # Normalize: "FAMILY Description" → "FAMILY" (strip descriptive suffix)
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
        """Lock material code. Once locked, cannot be changed.

        Validates against config material codes first, then MaterialCode enum
        as legacy fallback. Stores as plain string.
        """
        if self.locked_material is not None:
            return

        upper = material.upper()

        # 1. Direct match against config-known codes
        known = self._get_known_material_codes()
        if upper in known:
            self.locked_material = upper
            return

        # 2. Check aliases from config
        aliases = self._get_material_aliases()
        resolved = aliases.get(upper)
        if resolved:
            self.locked_material = resolved
            return

        # 3. Legacy fallback: MaterialCode enum
        try:
            self.locked_material = MaterialCode(upper).value
        except ValueError:
            pass

    @staticmethod
    def _get_known_material_codes() -> set[str]:
        """Get set of known material codes from config."""
        try:
            from config_loader import get_config
            cfg = get_config()
            if cfg.material_codes_extended:
                return {mat.code.upper() for mat in cfg.material_codes_extended}
        except Exception:
            pass
        # Legacy fallback
        return {m.value for m in MaterialCode}

    @staticmethod
    def _get_material_aliases() -> dict[str, str]:
        """Build material alias map from config. Returns {ALIAS: CODE} as plain strings."""
        try:
            from config_loader import get_config
            cfg = get_config()
            if cfg.material_codes_extended:
                aliases = {}
                for mat in cfg.material_codes_extended:
                    for alias in mat.aliases:
                        aliases[alias.upper()] = mat.code.upper()
                return aliases
        except Exception:
            pass
        return {}

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

        Uses config (prompt_context section) when available, falling back
        to legacy hardcoded rendering for backward compatibility.
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
                mat_code = self.locked_material
                from logic.dimension_tables import get_corrosion_map
                corr_class = get_corrosion_map().get(mat_code, "unknown")
                lines.append(f"- **Material:** {mat_code} (corrosion class {corr_class}) ← USE THIS IN ALL PRODUCT CODES")
                lines.append(f"  ⛔ PROHIBITION: Do NOT use FZ if {mat_code} is specified. Do NOT revert to default.")
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
        # MATERIAL REFERENCE: Built dynamically from config — no hardcoded data
        # =====================================================================
        from logic.dimension_tables import get_corrosion_map
        corr_map = get_corrosion_map()
        if corr_map:
            ref = ", ".join(f"{k}={v}" for k, v in corr_map.items())
            lines.append("### Material ↔ Corrosion Class Reference")
            lines.append(ref)
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
        # TAG SPECIFICATIONS: Per-tag data (config-driven or legacy)
        # =====================================================================
        tag_fields_cfg = self._get_prompt_tag_fields()

        if self.tags:
            lines.append("### 📋 TAG SPECIFICATIONS (FROM USER INPUT)")
            lines.append("")

            for tag_id, tag in self.tags.items():
                lines.append(f"**Tag {tag_id}:**")

                if tag_fields_cfg:
                    self._render_tag_from_config(tag, tag_fields_cfg, lines)
                else:
                    self._render_tag_legacy(tag, lines)

                # Status with explicit instructions (universal)
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
        # PROHIBITION RULES (config-driven or legacy)
        # =====================================================================
        prohibitions = self._get_prompt_prohibitions()
        lines.append("### ⛔ STRICT PROHIBITIONS")
        lines.append("")
        for i, rule in enumerate(prohibitions, 1):
            lines.append(f"{i}. **{rule}**")
        lines.append("")

        # =====================================================================
        # DERIVATION RULES (config-driven or legacy)
        # =====================================================================
        derivation_rules = self._get_prompt_derivation_rules()
        lines.append("### 🔧 AUTO-DERIVATION RULES")
        lines.append("")
        lines.append("| If Known | Then Derive |")
        lines.append("|----------|-------------|")
        for rule in derivation_rules:
            lines.append(f"| {rule['if_known']} | {rule['then_derive']} |")
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
        # IMMEDIATE ACTION + PRE-COMPUTED ENTITY CARDS
        # =====================================================================
        if self.all_tags_complete():
            lines.append("### 🎯 ALL DATA COMPLETE — DELIVER FINAL ANSWER")
            lines.append("")
            # Pre-compute entity cards — the LLM MUST copy these verbatim
            import json as _json
            cards = self._build_entity_cards()
            lines.append("### PRE-COMPUTED ENTITY CARD (copy EXACTLY into entity_card)")
            lines.append("```json")
            lines.append(_json.dumps(cards, indent=2))
            lines.append("```")
            lines.append("Use these cards verbatim. Write narrative text explaining the configuration.")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _get_prompt_tag_fields() -> list[dict]:
        """Load tag display field config, or empty list for legacy fallback."""
        try:
            from config_loader import get_config
            return get_config().prompt_tag_fields
        except Exception:
            return []

    @staticmethod
    def _get_prompt_prohibitions() -> list[str]:
        """Load prohibition rules from config, or legacy defaults."""
        try:
            from config_loader import get_config
            rules = get_config().prompt_prohibitions
            if rules:
                return rules
        except Exception:
            pass
        # Legacy fallback
        return [
            "NEVER ask for data shown above - it's already known",
            "NEVER revert material to FZ if RF/ZM/SF was specified",
            "NEVER ask for housing length if filter depth is known (auto-derived)",
            "NEVER ask for filter depth if WxHxD format was provided",
            "ALWAYS use locked material suffix in product codes (e.g., -RF not -FZ)",
            "ALWAYS acknowledge previous input before asking new questions",
        ]

    @staticmethod
    def _get_prompt_derivation_rules() -> list[dict]:
        """Load derivation rules from config, or legacy defaults."""
        try:
            from config_loader import get_config
            rules = get_config().prompt_derivation_rules
            if rules:
                return rules
        except Exception:
            pass
        # Legacy fallback
        return [
            {"if_known": "Filter Depth ≤292mm", "then_derive": "Housing Length = 550mm"},
            {"if_known": "Filter Depth ≤450mm", "then_derive": "Housing Length = 750mm"},
            {"if_known": "Filter Depth >450mm", "then_derive": "Housing Length = 900mm"},
            {"if_known": "Filter 305mm", "then_derive": "Housing 300mm"},
            {"if_known": "Filter 610mm", "then_derive": "Housing 600mm"},
        ]

    def _render_tag_from_config(self, tag: "TagSpecification", fields_cfg: list[dict], lines: list[str]) -> None:
        """Render tag fields using config-driven field definitions.

        Each field entry has a 'type' that determines rendering:
        - dimension_pair: width × height with optional depth
        - single: simple value with optional format
        - aggregate: value with multi-module support
        """
        for entry in fields_cfg:
            ftype = entry.get("type", "single")

            if ftype == "dimension_pair":
                self._render_dimension_pair(tag, entry, lines)
            elif ftype == "aggregate":
                self._render_aggregate_field(tag, entry, lines)
            elif ftype == "single":
                self._render_single_field(tag, entry, lines)

    @staticmethod
    def _render_dimension_pair(tag: "TagSpecification", entry: dict, lines: list[str]) -> None:
        """Render a width×height dimension pair with optional depth extension."""
        w_field = entry.get("width", "")
        h_field = entry.get("height", "")
        d_field = entry.get("depth")
        label = entry.get("label", "Dimensions")

        w = tag.get_prop(w_field)
        h = tag.get_prop(h_field)
        if not w or not h:
            return

        depth_str = ""
        if d_field:
            d = tag.get_prop(d_field)
            if d:
                depth_str = f"x{d}mm"

        lines.append(f"  - {label}: {w}x{h}{depth_str}")

        # Depth suppression hint
        if d_field and tag.get_prop(d_field):
            depth_supp = entry.get("depth_suppression", "")
            if depth_supp:
                lines.append(f"    ✓ {depth_supp.format(depth=tag.get_prop(d_field))}")

        # Main suppression hint (for housing size etc.)
        suppression = entry.get("suppression", "")
        if suppression:
            lines.append(f"    ✓ {suppression.format(width=w, height=h)}")

    @staticmethod
    def _render_single_field(tag: "TagSpecification", entry: dict, lines: list[str]) -> None:
        """Render a single scalar field."""
        field_name = entry.get("field", "")
        label = entry.get("label", field_name)
        fmt = entry.get("format", "{value}")
        min_val = entry.get("min_display_value")

        value = tag.get_prop(field_name)
        if value is None:
            return
        if min_val is not None and value < min_val:
            return

        display = fmt.format(value=value)
        lines.append(f"  - {label}: {display}")

        suppression = entry.get("suppression", "")
        if suppression:
            lines.append(f"    ✓ {suppression}")

    @staticmethod
    def _render_aggregate_field(tag: "TagSpecification", entry: dict, lines: list[str]) -> None:
        """Render an aggregate field with multi-module support."""
        field_name = entry.get("field", "")
        label = entry.get("label", field_name)
        unit = entry.get("unit", "")
        single_suffix = entry.get("single_suffix", "")

        value = tag.get_prop(field_name)
        if not value:
            return

        total_field = entry.get("total_field", "")
        rated_field = entry.get("rated_field", "")
        count_field = entry.get("count_field", "modules_needed")

        total = tag.get_prop(total_field) if total_field else None
        rated = tag.get_prop(rated_field) if rated_field else None
        count = tag.get_prop(count_field, 1)

        # Rated vs requested (airflow specific)
        if rated and rated != value:
            lines.append(f"  - Rated {label}: {rated} {unit} per module (catalog)")
            lines.append(f"  - Requested {label}: {value} {unit}")
        elif count > 1 and total:
            lines.append(f"  - {label}: {total} {unit} total ({count}×{value} per unit)")
        else:
            suffix = f" {single_suffix}" if single_suffix else ""
            lines.append(f"  - {label}: {value} {unit}{suffix}")

        suppression = entry.get("suppression", "")
        if suppression:
            lines.append(f"    ✓ {suppression}")

    def _render_tag_legacy(self, tag: "TagSpecification", lines: list[str]) -> None:
        """Legacy hardcoded tag rendering (backward compat when no config)."""
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

    def _build_entity_cards(self) -> dict | list:
        """Pre-compute entity_card(s) from finalized tag data.

        v4.3: Cards are built in Python from authoritative graph data, then
        injected into the prompt so the LLM copies them verbatim. This prevents
        hallucination of weights, product codes, and corrosion classes.

        Uses config.prompt_entity_card when available, falls back to legacy.
        """
        card_cfg = self._get_entity_card_config()
        if card_cfg and card_cfg.get("specs"):
            return self._build_entity_cards_from_config(card_cfg)
        return self._build_entity_cards_legacy()

    @staticmethod
    def _get_entity_card_config() -> dict:
        """Load entity card config, or empty dict for legacy fallback."""
        try:
            from config_loader import get_config
            return get_config().prompt_entity_card
        except Exception:
            return {}

    def _build_entity_cards_from_config(self, card_cfg: dict) -> dict | list:
        """Config-driven entity card builder."""
        from logic.dimension_tables import get_corrosion_map, get_known_material_codes
        _known_mats = get_known_material_codes()
        CORROSION_MAP = get_corrosion_map()

        title_template = card_cfg.get("title_template", "{family} ({housing_width}x{housing_height}mm)")
        specs_cfg = card_cfg.get("specs", [])

        cards = []
        for tag_id, tag in self.tags.items():
            fam = tag.product_family or self.detected_family or "Unknown"
            mat_code = self._resolve_material_code(tag, _known_mats)
            corr = CORROSION_MAP.get(mat_code, "")

            # Build specs from config
            specs = {}
            for spec in specs_cfg:
                spec_type = spec.get("type", "")
                label = spec.get("label", "")

                if spec_type == "material":
                    specs[label] = f"{mat_code} (corrosion class {corr})" if corr else mat_code
                elif spec_type == "resolved_param":
                    param = spec.get("param", "")
                    default = spec.get("default", "")
                    specs[label] = self.resolved_params.get(param, default)
                else:
                    # Field-based spec
                    field_name = spec.get("field")
                    fields = spec.get("fields", [])
                    fmt = spec.get("format", "")
                    total_field = spec.get("total_field", "")
                    count_field = spec.get("count_field", "modules_needed")
                    unit = spec.get("unit", "")
                    prefix = spec.get("prefix", "")

                    if fields:
                        # Multi-field format (e.g., WxH)
                        vals = {f: tag.get_prop(f) for f in fields}
                        if all(vals.values()):
                            specs[label] = fmt.format(**vals)
                    elif field_name:
                        value = tag.get_prop(field_name)
                        if value is None:
                            continue
                        count = tag.get_prop(count_field, 1)
                        total = tag.get_prop(total_field) if total_field else None

                        if count > 1 and total:
                            specs[label] = f"{prefix}{total} {unit} ({count}×{value})".strip()
                        else:
                            if fmt:
                                specs[label] = fmt.format(**{field_name: value})
                            else:
                                specs[label] = f"{prefix}{value} {unit}".strip()

            # Build title
            assembly_label = ""
            if tag.assembly_role:
                stage_num = 1 if tag.assembly_role == "PROTECTOR" else 2
                assembly_label = f"Stage {stage_num} ({tag.assembly_role}): "

            title = title_template.format(
                assembly_label=assembly_label,
                family=fam,
                housing_width=tag.get_prop("housing_width", ""),
                housing_height=tag.get_prop("housing_height", ""),
            )

            cards.append({"title": title, "specs": specs})

        if len(cards) == 1:
            return cards[0]
        return cards

    def _resolve_material_code(self, tag: "TagSpecification", known_mats: set) -> str:
        """Resolve the material code for a tag (locked → product code → default)."""
        if self.locked_material:
            return self.locked_material
        if tag.product_code:
            last_seg = tag.product_code.rsplit("-", 1)[-1]
            if last_seg in known_mats:
                return last_seg
        try:
            from config_loader import get_config
            return get_config().default_material or ""
        except Exception:
            return ""

    def _build_entity_cards_legacy(self) -> dict | list:
        """Legacy hardcoded entity card builder (backward compat)."""
        from logic.dimension_tables import get_corrosion_map, get_known_material_codes
        _known_mats = get_known_material_codes()
        CORROSION_MAP = get_corrosion_map()
        cards = []
        for tag_id, tag in self.tags.items():
            fam = tag.product_family or self.detected_family or "Unknown"
            mat_code = self._resolve_material_code(tag, _known_mats)
            corr = CORROSION_MAP.get(mat_code, "")

            specs = {}
            if tag.product_code:
                specs["Product Code"] = tag.product_code
            if tag.housing_width and tag.housing_height:
                specs["Housing Size"] = f"{tag.housing_width}x{tag.housing_height}mm"
            if tag.housing_length:
                specs["Housing Length"] = f"{tag.housing_length}mm"
            specs["Material"] = f"{mat_code} (corrosion class {corr})" if corr else mat_code
            conn = self.resolved_params.get("connection_type", "PG")
            specs["Connection"] = conn
            if tag.airflow_m3h:
                if tag.modules_needed > 1 and tag.total_airflow_m3h:
                    specs["Rated Airflow"] = f"{tag.total_airflow_m3h} m³/h ({tag.modules_needed}×{tag.airflow_m3h})"
                else:
                    specs["Rated Airflow"] = f"{tag.airflow_m3h} m³/h"
            if tag.weight_kg:
                if tag.modules_needed > 1 and tag.total_weight_kg:
                    specs["Weight"] = f"~{tag.total_weight_kg} kg ({tag.modules_needed}×{tag.weight_kg}kg)"
                else:
                    specs["Weight"] = f"~{tag.weight_kg} kg"

            assembly_label = ""
            if tag.assembly_role:
                stage_num = 1 if tag.assembly_role == "PROTECTOR" else 2
                assembly_label = f"Stage {stage_num} ({tag.assembly_role}): "

            cards.append({
                "title": f"{assembly_label}{fam} Housing ({tag.housing_width}x{tag.housing_height}mm)",
                "specs": specs,
            })

        if len(cards) == 1:
            return cards[0]
        return cards

    def to_compact_summary(self) -> str:
        """Compact state summary for Semantic Scribe LLM prompt.

        Token-efficient representation of current state. Unlike to_prompt_context()
        which includes prohibition rules for the main LLM, this produces a minimal
        machine-readable summary for the extraction engine.
        """
        lines = []
        if self.locked_material:
            lines.append(f"Material: {self.locked_material}")
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
            session_mgr.lock_material(session_id, self.locked_material)

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

        # Persist tags — build field dict from typed fields + property bag
        _typed_tag_fields = (
            "filter_width", "filter_height", "filter_depth", "airflow_m3h",
            "product_family", "product_code", "weight_kg", "quantity",
            "assembly_group_id",
        )
        for tag_id, tag in self.tags.items():
            tag_fields = {}
            for attr in _typed_tag_fields:
                val = getattr(tag, attr, None)
                if val is not None:
                    tag_fields[attr] = val
            # Merge any extra properties from the generic bag
            for k, v in tag.properties.items():
                if k not in tag_fields and v is not None:
                    tag_fields[k] = v
            tag_fields["source_message"] = self.turn_count
            session_mgr.upsert_tag(session_id, tag_id, **tag_fields)

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

        # Load tags generically — pass all graph fields to merge_tag
        _graph_meta_keys = {"tag_id", "id", "session_id", "source_message", "is_complete"}
        for tag_data in state_data.get("tags", []):
            tag_id = tag_data.get("tag_id", "unknown")
            fields = {k: v for k, v in tag_data.items()
                      if k not in _graph_meta_keys and v is not None}
            ts.merge_tag(tag_id, **fields)

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
            "locked_material": self.locked_material if self.locked_material else None,
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
                    "properties": tag.properties,
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
            state.lock_material(data["locked_material"])
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
            tag.properties = tag_data.get("properties", {})
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
        'default_frame_depth' (for products where the code uses frame
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
        default_mat = ""
        try:
            from config_loader import get_config
            default_mat = get_config().default_material or ""
        except Exception:
            pass
        material = tag.material_override or (self.locked_material if self.locked_material else default_mat)
        connection = self.resolved_params.get("connection_type", "PG")

        # Apply connection-specific length offset (e.g., Flange adds 50mm)
        length = int(tag.housing_length or 0)
        length_offset = int(self.resolved_params.get("connection_length_offset", 0))
        effective_length = length + length_offset if length else 0

        # Frame depth for products that use frame depth in code format
        frame_depth = self.resolved_params.get("frame_depth") or default_frame_depth or ""

        # Side parameter for FLEX products (R = Right, L = Left)
        side = self.resolved_params.get("side", "R")

        placeholders = {
            "family": family,
            "width": str(tag.housing_width or ""),
            "height": str(tag.housing_height or ""),
            "length": str(effective_length) if effective_length else "",
            "frame_depth": str(int(frame_depth)) if frame_depth else "",
            "material": material,
            "connection": connection,
            "side": side,
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

    def _infer_housing_length(self, tag: "TagSpecification", db) -> None:
        """Infer housing_length from product code or length variant default.

        v4.1: Fixes weight lookup bug where housing_length stays None even when
        the product code contains a length (e.g., FAMILY-900x900-750-...).
        Called before weight lookup to ensure correct short/long selection.
        """
        if tag.housing_length is not None:
            return

        # 1. Extract from product code if it contains a numeric length segment
        if tag.product_code:
            import re
            # Product code format: FAM-WxH-LENGTH-CONN-TYPE-MAT
            # Length is a 3-4 digit number after the WxH segment
            m = re.search(r'-(\d{3,4})-', tag.product_code)
            if m:
                candidate = int(m.group(1))
                # Sanity check: housing lengths are typically 550-1100mm
                if 400 <= candidate <= 1200:
                    tag.housing_length = candidate
                    print(f"📐 [WEIGHT] Inferred housing_length={candidate} from product code {tag.product_code}")
                    return

        # 2. Query the default length variant from graph
        fam = tag.product_family or self.detected_family or ""
        fam_id = f"FAM_{fam}" if fam and not fam.startswith("FAM_") else fam
        if fam_id:
            default_length = db.get_default_length_variant(fam_id)
            if default_length:
                tag.housing_length = default_length
                print(f"📐 [WEIGHT] Inferred housing_length={default_length} from default length variant for {fam_id}")

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

                # v4.1: Infer housing_length before weight lookup
                self._infer_housing_length(tag, db)

                # PRIMARY: ProductVariant exact match (family-specific, authoritative)
                # v4.0: Pass housing_length to select correct weight for dual-length products
                fam_name = tag.product_family or self.detected_family or ""
                if fam_name and tag.housing_width and tag.housing_height:
                    variant_key = f"{fam_name}-{tag.housing_width}x{tag.housing_height}"
                    weight = db.get_variant_weight(variant_key, housing_length=tag.housing_length)
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
        """Verify and ENFORCE that all product codes use the locked material suffix.

        v4.1: Now rewrites mismatched product codes instead of just warning.
        This fixes the bug where the engine correctly detects material constraints
        but the product code still uses FZ as fallback.

        Returns:
            List of warning messages for codes that were rewritten
        """
        warnings = []

        if not self.locked_material:
            return warnings

        from logic.dimension_tables import get_known_material_codes
        expected_mat = self.locked_material
        expected_suffix = f"-{expected_mat}"
        known_materials = get_known_material_codes()

        for tag_id, tag in self.tags.items():
            if tag.product_code:
                if not tag.product_code.endswith(expected_suffix):
                    old_code = tag.product_code
                    # Replace the material suffix at the end of the product code
                    parts = tag.product_code.rsplit("-", 1)
                    if len(parts) == 2 and parts[1] in known_materials:
                        tag.product_code = f"{parts[0]}-{expected_mat}"
                        tag.material_override = None  # Clear any override
                        warnings.append(
                            f"Tag {tag_id}: Rewrote '{old_code}' → '{tag.product_code}' "
                            f"(enforced locked material {expected_mat})"
                        )
                        print(f"🔧 [MATERIAL-ENFORCE] {tag_id}: {old_code} → {tag.product_code}")
                    else:
                        warnings.append(
                            f"Tag {tag_id}: Product code '{tag.product_code}' "
                            f"does not end with locked material '{expected_suffix}' (could not auto-fix)"
                        )

        return warnings

    def enforce_available_materials(self, db) -> list[str]:
        """When locked_material is None, ensure product codes use a material
        that's actually available for the product family.

        v4.2: Fixes bug where some product codes default to a material not available for that family.
        """
        if self.locked_material:
            return []  # Already handled by verify_material_codes

        from logic.dimension_tables import get_known_material_codes
        warnings = []
        known_materials = get_known_material_codes()
        # Cache per-family lookups
        _cache = {}

        for tag_id, tag in self.tags.items():
            if not tag.product_code:
                continue
            fam = tag.product_family or self.detected_family or ""
            if not fam:
                continue
            fam_id = f"FAM_{fam}" if not fam.startswith("FAM_") else fam

            # Get available materials (cached)
            if fam_id not in _cache:
                mats = db.get_available_materials(fam_id)
                _cache[fam_id] = [m["code"] for m in mats] if mats else []
            available = _cache[fam_id]
            if not available:
                continue

            # Check current material suffix
            parts = tag.product_code.rsplit("-", 1)
            if len(parts) == 2 and parts[1] in known_materials:
                current_mat = parts[1]
                if current_mat not in available:
                    new_mat = available[0]
                    old_code = tag.product_code
                    tag.product_code = f"{parts[0]}-{new_mat}"
                    warnings.append(
                        f"Tag {tag_id}: '{old_code}' -> '{tag.product_code}' "
                        f"({current_mat} not available for {fam}, using {new_mat})"
                    )
                    print(f"🔧 [MATERIAL-DEFAULT] {tag_id}: {old_code} -> {tag.product_code}")

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
            lines.append(f"**Material:** {self.locked_material} (Locked)")
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

    patterns = _get_material_extraction_patterns()

    for mat_code, keywords in patterns.items():
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', query_lower):
                return mat_code

    return None


def _get_material_extraction_patterns() -> dict[str, list[str]]:
    """Get material extraction patterns from config, falling back to hardcoded."""
    try:
        from config_loader import get_config
        cfg = get_config()
        if cfg.material_codes_extended:
            return {
                mat.code: mat.extraction_keywords
                for mat in cfg.material_codes_extended
            }
    except Exception:
        pass
    # Empty fallback — all extraction patterns come from tenant config
    return {}


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
