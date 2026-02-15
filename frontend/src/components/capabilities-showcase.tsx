"use client";

import { useState } from "react";
import {
  Search,
  TreePine,
  Shield,
  Ruler,
  Layers,
  AlertTriangle,
  ShieldCheck,
  Wrench,
  QrCode,
  ArrowRightLeft,
  MessageSquare,
  ChevronDown,
  ChevronRight,
  Zap,
  Atom,
  CircleDot,
  HelpCircle,
  ArrowRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface ExampleQuestion { question: string; why: string; }
interface SubComponent { name: string; detail?: string; }
interface Module {
  id: string; title: string; subtitle: string; description: string;
  icon: React.ComponentType<{ className?: string }>; color: string;
  subComponents: SubComponent[]; examples: ExampleQuestion[];
}

const MODULES: Module[] = [
  {
    id: "product-selection", title: "Product Selection", subtitle: "Product Recommendation",
    description: "Recommends the optimal product family based on application, environmental context and required physical traits.",
    icon: Search, color: "blue",
    subComponents: [
      { name: "GDP Planfilterskåp", detail: "Panel filter housing, priority 10" },
      { name: "GDB Kanalfilterskåp", detail: "Bag/compact filter housing" },
      { name: "GDC Patronfilterskåp", detail: "Carbon cartridge housing (bayonet)" },
      { name: "GDC FLEX", detail: "Carbon housing with extractable rail" },
      { name: "GDMI Modulfilterskåp", detail: "Double-walled insulated housing" },
      { name: "PFF Planfilterram", detail: "Panel filter frame" },
    ],
    examples: [
      { question: "I need a filter housing for hospital ventilation", why: "General product inquiry — system evaluates all families against detected stressors (hygiene, chlorine) and ranks by trait coverage." },
      { question: "What is the difference between GDB and GDMI?", why: "Product comparison — engine compares physical traits (insulation, corrosion class) and shows coverage score for each." },
      { question: "I want a carbon filter for odor removal", why: "Functional goal 'Odor Removal' maps to trait Porous Adsorption → GDC/GDC FLEX families recommended." },
      { question: "GDB 305x610x292 stainless steel", why: "Direct selection with explicit specs — system validates instead of recommending, checks constraints." },
      { question: "What do you recommend for HEPA filtration?", why: "Functional goal 'HEPA' maps to trait HEPA Filtration → GDMI is the only family with this trait." },
    ],
  },
  {
    id: "environment-assessment", title: "Environment Assessment", subtitle: "Hazard Identification",
    description: "Automatic identification of environmental hazards and their impact on product selection via graph nodes.",
    icon: TreePine, color: "emerald",
    subComponents: [
      { name: "Hospital / Healthcare", detail: "→ Hygiene Requirements" },
      { name: "Commercial Kitchen", detail: "→ Grease/Oil, Chemical Vapors" },
      { name: "ATEX Zone", detail: "→ Explosive Atmosphere" },
      { name: "Marine / Offshore", detail: "→ Salt Spray, High Humidity" },
      { name: "Pharmaceutical / Cleanroom", detail: "→ Particulate, Chemical Vapors, Hygiene" },
      { name: "Outdoor / Rooftop", detail: "→ Condensation, High Humidity" },
      { name: "Wastewater Treatment", detail: "→ H₂S Corrosion, Chemical Vapors" },
      { name: "Swimming Pool", detail: "→ Chlorine Exposure, Humidity" },
      { name: "Flour Mill / Grain Processing", detail: "→ Particulate, Explosive Atmosphere" },
      { name: "Paint Shop", detail: "→ Particulate, Chemical Vapors" },
      { name: "Powder Coating Line", detail: "→ Particulate, Explosive, Chemical Vapors" },
    ],
    examples: [
      { question: "This is for hospital operating room ventilation", why: "Keyword 'hospital' triggers Environment: Hospital/Healthcare → stressor Hygiene Requirements → demands C5 corrosion resistance." },
      { question: "Installation next to an indoor swimming pool", why: "'Swimming pool' maps to Application → exposes to Chlorine + High Humidity. Triggers material escalation logic." },
      { question: "Industrial kitchen, extraction above deep fryers", why: "'Kitchen' + 'fryers' → Environment: Commercial Kitchen → stressors: Grease/Oil Exposure + Chemical Vapors." },
      { question: "Offshore drilling platform in the North Sea", why: "'Offshore' / 'North Sea' → Environment: Marine → stressors: Salt Spray (demands C5-M) + High Humidity." },
      { question: "Rooftop AHU installation in Scandinavia", why: "'Rooftop' → Environment: Outdoor → stressors: Condensation (demands thermal insulation) + Humidity." },
      { question: "Wastewater treatment plant, sludge hall", why: "'Wastewater' → Environment: Wastewater Treatment → H₂S corrosion (destroys zinc) + Chemical Vapors." },
      { question: "ATEX-classified zone in a flour mill", why: "'ATEX' + 'flour mill' → two triggers: Environment ATEX (Explosive Atmosphere) + Application Flour Mill (Particulate)." },
      { question: "ISO 7 cleanroom for pharmaceutical production", why: "'Cleanroom' + 'pharmaceutical' → Environment: Pharmaceutical → Particulate + Hygiene + Chemical Vapors." },
    ],
  },
  {
    id: "material-specification", title: "Material Specification", subtitle: "Corrosion Class Enforcement",
    description: "Selection and validation of housing material based on detected environment, chlorine thresholds, and corrosion class.",
    icon: Shield, color: "violet",
    subComponents: [
      { name: "FZ — Galvanized (Förzinkat)", detail: "C3, max 0 ppm Cl" },
      { name: "AZ — Aluzink", detail: "C4, max 5 ppm Cl" },
      { name: "ZM — Zinc-Magnesium", detail: "C5, max 10 ppm Cl" },
      { name: "RF — Stainless (Rostfri)", detail: "C5, max 50 ppm Cl" },
      { name: "SF — Acid-proof (Syrafast)", detail: "C5.1, max 500 ppm Cl" },
    ],
    examples: [
      { question: "Can I use galvanized steel in a hospital?", why: "Hospital demands C5+ (stainless). FZ is C3 — blocked by SET_MEMBERSHIP constraint. System explains the gap and suggests RF or SF." },
      { question: "What material for a pool with 80 ppm chlorine?", why: "80 ppm exceeds RF max (50 ppm) → CROSS_NODE_THRESHOLD fires → only SF (max 500 ppm) qualifies." },
      { question: "Stainless steel, please", why: "System maps 'stainless' → code RF, locks material for the session. All subsequent product codes get -RF suffix." },
      { question: "Does ZM work for a marine platform?", why: "Marine demands C5-M. ZM is C5 without marine suffix → Salt Spray neutralizes C3/C5 → system escalates to SF." },
      { question: "Cheapest material for an office building?", why: "No aggressive stressors detected (indoor/office) → FZ (galvanized) is allowed and most cost-effective." },
      { question: "We have H₂S problems in the sewage plant", why: "H₂S aggressively attacks zinc → CRITICAL neutralization of C3 → minimum RF required, SF recommended." },
    ],
  },
  {
    id: "sizing-arrangement", title: "Sizing & Arrangement", subtitle: "Module Layout & Capacity",
    description: "Module selection, quantity calculation based on airflow requirements, and spatial arrangement geometry.",
    icon: Ruler, color: "amber",
    subComponents: [
      { name: "Airflow capacity calculation", detail: "Modules needed = required ÷ per-module rating" },
      { name: "Dimension lock", detail: "Exact-match module when user specifies explicit dimensions" },
      { name: "Spatial constraint handling", detail: "Max width/height → vertical/horizontal stacking" },
      { name: "Arrangement geometry", detail: "horizontal × vertical → effective dimensions" },
      { name: "Oversizing detection", detail: "Warn when module capacity >> required airflow" },
    ],
    examples: [
      { question: "I need 8000 m³/h airflow", why: "Capacity calculation: per-module rating (e.g. 1700 m³/h for GDB-300) → 5 modules needed. System computes optimal arrangement." },
      { question: "GDB 305×610", why: "Explicit dimensions → dimension lock on 300×600 module. No alternative module selection — exact match enforced." },
      { question: "Maximum 700mm width available in the shaft", why: "Spatial constraint → modules arranged vertically instead of horizontally. System calculates how many fit within 700mm." },
      { question: "What are the actual dimensions of a 4-module set?", why: "Arrangement geometry: e.g. 2 wide × 2 high = 1200mm × 1200mm effective size." },
      { question: "Will one module handle 2000 m³/h?", why: "Capacity check: GDB-600 module = 3400 m³/h → one module sufficient, but system may warn about oversizing." },
    ],
  },
  {
    id: "multi-stage", title: "Multi-Stage System Design", subtitle: "Assembly Builder",
    description: "When a product's primary trait is neutralized by environment, system designs a multi-stage assembly with a protector upstream.",
    icon: Layers, color: "rose",
    subComponents: [
      { name: "Grease → Pre-filter + Carbon", detail: "GDB protects GDC from lipid contamination" },
      { name: "Particulate → Pre-filter + Carbon", detail: "GDB captures dust before it blocks carbon pores" },
      { name: "Humidity → Drying stage + Carbon", detail: "GDB pre-dries air to maintain adsorption efficiency" },
      { name: "Assembly sync", detail: "Shared dimensions and airflow across all stages" },
    ],
    examples: [
      { question: "I want a carbon filter for an industrial kitchen", why: "Grease NEUTRALIZES Porous Adsorption (CRITICAL). Auto-builds assembly: Stage 1 GDB (pre-filter) + Stage 2 GDC (carbon)." },
      { question: "GDC for a paint shop — there will be overspray", why: "Particulate from overspray NEUTRALIZES carbon pores. DependencyRule triggers: upstream Mechanical Filtration → downstream Adsorption." },
      { question: "Odor removal in a humid environment", why: "Humidity degrades carbon efficiency (WARNING). Suggests assembly with GDB dehumidifying stage before GDC." },
      { question: "Can I use just GDC in a powder coating line?", why: "Powder coating = Particulate + Explosive + Chemical Vapors. GDC alone would have neutralized traits → assembly mandatory." },
    ],
  },
  {
    id: "installation-feasibility", title: "Installation Feasibility", subtitle: "Constraint Validation",
    description: "Three constraint types validate physical fit: computed clearance, environment whitelists, and chemical threshold checks.",
    icon: AlertTriangle, color: "orange",
    subComponents: [
      { name: "COMPUTED_FORMULA", detail: "Service clearance = dimension × factor vs available space" },
      { name: "SET_MEMBERSHIP", detail: "Environment requires material IN allowed list" },
      { name: "CROSS_NODE_THRESHOLD", detail: "Chemical concentration vs material tolerance" },
      { name: "Hard constraints", detail: "Min housing length per product family (auto-correct)" },
    ],
    examples: [
      { question: "I have 900mm shaft, will GDB-600 fit?", why: "COMPUTED_FORMULA: 600mm × service_access_factor → required clearance. Checks if 900mm sufficient including service space." },
      { question: "Can FZ galvanized be used in a hospital?", why: "SET_MEMBERSHIP: Hospital allows only [RF, SF]. FZ not in list → CRITICAL violation with alternatives." },
      { question: "Chlorine is 120 ppm — is RF enough?", why: "CROSS_NODE_THRESHOLD: RF.max_chlorine = 50, input = 120 → threshold exceeded → must upgrade to SF." },
      { question: "GDC with 400mm housing", why: "Hard constraint: GDC minimum housing_length ≥ 750mm. Auto-corrected to 750mm with explanation." },
      { question: "GDB with 500mm housing length", why: "Hard constraint: GDB minimum ≥ 550mm. Auto-corrected — insufficient depth for bag filters." },
    ],
  },
  {
    id: "compliance-safety", title: "Compliance & Safety", subtitle: "Logic Gates & Data Collection",
    description: "Logic Gates monitor detected stressors and collect additional parameters before safety-critical decisions.",
    icon: ShieldCheck, color: "red",
    subComponents: [
      { name: "Chlorine Exposure Gate", detail: "Requires: chlorine_level (ppm) → RF vs SF" },
      { name: "ATEX Zone Classification", detail: "Requires: atex_zone → grounding requirements" },
      { name: "Dew Point Condensation Gate", detail: "Requires: min_temperature, relative_humidity" },
      { name: "Grease Loading Gate", detail: "Requires: grease_presence confirmation" },
    ],
    examples: [
      { question: "Installation near a swimming pool", why: "Chlorine detected but concentration unknown → Gate fires: 'What is the chlorine concentration (ppm)?' to determine RF vs SF." },
      { question: "This is an ATEX zone", why: "ATEX Gate triggers: 'What zone classification (20/21/22)?' — different zones have different grounding requirements." },
      { question: "Rooftop unit in northern climate", why: "Dew Point Gate fires: 'Minimum outdoor temperature? Humidity?' — needed to calculate condensation risk." },
      { question: "Kitchen with grills and open flames", why: "Grease Gate asks for confirmation → if confirmed, triggers assembly requirement (pre-filter before carbon)." },
      { question: "150", why: "Bare number after chlorine question → pending_clarification routes it as chlorine_level = 150 ppm → SF enforced." },
    ],
  },
  {
    id: "accessories", title: "Accessories & Transitions", subtitle: "Compatibility & Cross-sell",
    description: "Compatibility validation for locks, mounting systems, duct transitions, and cross-sell suggestions.",
    icon: Wrench, color: "slate",
    subComponents: [
      { name: "EXL — Excentric lock", detail: "Compatible: GDB, GDMI, GDP — Blocked: GDC" },
      { name: "L — Door configuration", detail: "Compatible: all families" },
      { name: "F — Flange connection", detail: "Compatible: all families" },
      { name: "Polis — Mounting system", detail: "Compatible: GDB, GDMI only" },
      { name: "Transition pieces (33)", detail: "Mapped by housing size → duct diameter" },
      { name: "Filter consumables (12)", detail: "Matched by product variant" },
    ],
    examples: [
      { question: "Add an EXL lock", why: "Compatibility check: EXL has HAS_COMPATIBLE_ACCESSORY with GDB/GDMI/GDP. If product is GDC (bayonet) → BLOCKED." },
      { question: "I need a round duct connection, 500mm", why: "Looks up TransitionPiece nodes matching housing size → duct_diameter = 500mm → returns compatible piece." },
      { question: "Can I mount this on a Polis rail?", why: "Polis compatible with GDB and GDMI only. If GDC → NOT_COMPATIBLE_WITH, suggests alternative mounting." },
      { question: "What replacement filters fit my unit?", why: "Queries FilterConsumable via ACCEPTS_FILTER on the selected ProductVariant → returns matching filters." },
    ],
  },
  {
    id: "product-code", title: "Product Code & Weight", subtitle: "Order Code Generation",
    description: "Generates complete orderable product codes from graph templates. Resolves weight from variant data or parametric models.",
    icon: QrCode, color: "cyan",
    subComponents: [
      { name: "Code format template", detail: "From ProductFamily.code_format in graph" },
      { name: "Variant weight lookup", detail: "Exact match from ProductVariant.weight_kg" },
      { name: "Parametric weight model", detail: "weight_per_mm_length × housing_length" },
      { name: "Multi-module aggregation", detail: "Total = modules × unit_weight" },
    ],
    examples: [
      { question: "Give me the full order code", why: "Assembles: family + filter_dims + material + housing_length + connection → e.g. GDB 305x610x292-RF-550-PG" },
      { question: "How much does it weigh? For structural calculations", why: "Weight from ProductVariant (exact) or parametric model (weight_per_mm × housing_length)." },
      { question: "5 modules of GDB — total weight?", why: "Aggregation: 5 × unit_weight_kg → returns total weight for structural engineering." },
    ],
  },
  {
    id: "alternatives", title: "Alternative Recommendations", subtitle: "Sales Recovery",
    description: "When primary selection is blocked, finds verified alternatives — material swaps or different product families.",
    icon: ArrowRightLeft, color: "indigo",
    subComponents: [
      { name: "Prong 1: Material change", detail: "Same product, different material (GDB-FZ → GDB-RF)" },
      { name: "Prong 2: Family change", detail: "Different product family (GDB → GDMI)" },
      { name: "Space alternatives", detail: "Smaller products that fit spatial constraints" },
      { name: "Capacity alternatives", detail: "Larger modules to reduce unit count" },
    ],
    examples: [
      { question: "GDB galvanized in a hospital — possible?", why: "FZ blocked (SET_MEMBERSHIP). Alternatives: Prong 1 GDB-RF (material swap), Prong 2 GDMI-RF (insulated, better for hospital)." },
      { question: "Is there something cheaper than SF?", why: "Checks lower corrosion classes that still meet requirements. If chlorine allows, RF may qualify." },
      { question: "I don't have space for 5 modules", why: "Space alternative: larger modules (600×600 instead of 300×600) → fewer units in arrangement." },
      { question: "GDC in a flour mill — no pre-filter", why: "Carbon without pre-filter impossible (neutralization). Explains physics and suggests GDP as alternative." },
    ],
  },
  {
    id: "multi-turn", title: "Multi-Turn Consultation", subtitle: "Session Persistence",
    description: "Full session memory persisted in the Knowledge Graph. Never loses established parameters across turns.",
    icon: MessageSquare, color: "teal",
    subComponents: [
      { name: "Parameter persistence", detail: "Dimensions, material, airflow survive across turns" },
      { name: "Material lock", detail: "Once chosen, material persists for all items" },
      { name: "Assembly group tracking", detail: "Multi-stage systems maintained across session" },
      { name: "Multi-tag projects", detail: "Independent specs for item_1, item_2, etc." },
      { name: "Pending clarification routing", detail: "Bare answers route to the right parameter" },
      { name: "Session restoration", detail: "Full state restored after days of inactivity" },
    ],
    examples: [
      { question: "Turn 1: 'GDB 300×600' → Turn 2: 'this is for a hospital'", why: "Dimensions from turn 1 preserved in Layer 4. Hospital added → material pivoted to RF, dimensions unchanged." },
      { question: "Turn 1: 'Stainless steel' → Turn 2: 'code for GDC'", why: "Material lock (RF) carries over. GDC code generated with -RF suffix automatically." },
      { question: "(3-day break) → 'Let's continue with that project'", why: "Full session restored from Neo4j Layer 4: all tags, dimensions, material locks, assembly groups." },
      { question: "Same as before but double the airflow", why: "Derived action: SAME_AS copies dimensions, DOUBLE multiplies airflow × 2. All tracked in state." },
      { question: "Add second item — GDC with same dimensions", why: "Multi-tag: item_2 created with GDC, dimensions copied from item_1. Each tracked independently." },
    ],
  },
];

const COLOR_MAP: Record<string, { bg: string; bgLight: string; border: string; icon: string; badge: string; dot: string }> = {
  blue:    { bg: "bg-blue-600",    bgLight: "bg-blue-50 dark:bg-blue-900/30",    border: "border-blue-200 dark:border-blue-800",    icon: "text-blue-500",    badge: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",    dot: "bg-blue-500" },
  emerald: { bg: "bg-emerald-600", bgLight: "bg-emerald-50 dark:bg-emerald-900/30", border: "border-emerald-200 dark:border-emerald-800", icon: "text-emerald-500", badge: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400", dot: "bg-emerald-500" },
  violet:  { bg: "bg-violet-600",  bgLight: "bg-violet-50 dark:bg-violet-900/30",  border: "border-violet-200 dark:border-violet-800",  icon: "text-violet-500",  badge: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400",  dot: "bg-violet-500" },
  amber:   { bg: "bg-amber-600",   bgLight: "bg-amber-50 dark:bg-amber-900/30",   border: "border-amber-200 dark:border-amber-800",   icon: "text-amber-500",   badge: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",   dot: "bg-amber-500" },
  rose:    { bg: "bg-rose-600",    bgLight: "bg-rose-50 dark:bg-rose-900/30",    border: "border-rose-200 dark:border-rose-800",    icon: "text-rose-500",    badge: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400",    dot: "bg-rose-500" },
  orange:  { bg: "bg-orange-600",  bgLight: "bg-orange-50 dark:bg-orange-900/30",  border: "border-orange-200 dark:border-orange-800",  icon: "text-orange-500",  badge: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",  dot: "bg-orange-500" },
  red:     { bg: "bg-red-600",     bgLight: "bg-red-50 dark:bg-red-900/30",     border: "border-red-200 dark:border-red-800",     icon: "text-red-500",     badge: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",     dot: "bg-red-500" },
  slate:   { bg: "bg-slate-600",   bgLight: "bg-slate-50 dark:bg-slate-800",   border: "border-slate-200 dark:border-slate-700",   icon: "text-slate-500",   badge: "bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300",   dot: "bg-slate-500" },
  cyan:    { bg: "bg-cyan-600",    bgLight: "bg-cyan-50 dark:bg-cyan-900/30",    border: "border-cyan-200 dark:border-cyan-800",    icon: "text-cyan-500",    badge: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400",    dot: "bg-cyan-500" },
  indigo:  { bg: "bg-indigo-600",  bgLight: "bg-indigo-50 dark:bg-indigo-900/30",  border: "border-indigo-200 dark:border-indigo-800",  icon: "text-indigo-500",  badge: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400",  dot: "bg-indigo-500" },
  teal:    { bg: "bg-teal-600",    bgLight: "bg-teal-50 dark:bg-teal-900/30",    border: "border-teal-200 dark:border-teal-800",    icon: "text-teal-500",    badge: "bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400",    dot: "bg-teal-500" },
};

function StatCard({ value, label, icon: Icon }: { value: string; label: string; icon: React.ComponentType<{ className?: string }> }) {
  return (
    <div className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-sm rounded-2xl border border-slate-200/60 dark:border-slate-700/60 p-5 flex items-center gap-4">
      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-50 to-violet-50 dark:from-blue-900/30 dark:to-violet-900/30 flex items-center justify-center flex-shrink-0">
        <Icon className="w-6 h-6 text-blue-600" />
      </div>
      <div>
        <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">{value}</div>
        <div className="text-xs text-slate-500 dark:text-slate-400">{label}</div>
      </div>
    </div>
  );
}

function ModuleCard({ module, isExpanded, onToggle }: { module: Module; isExpanded: boolean; onToggle: () => void }) {
  const c = COLOR_MAP[module.color] || COLOR_MAP.blue;
  const Icon = module.icon;
  return (
    <div className={cn(
      "bg-white/90 dark:bg-slate-800/90 backdrop-blur-sm rounded-2xl border transition-all duration-300",
      isExpanded ? cn("shadow-lg", c.border) : "border-slate-200/60 dark:border-slate-700/60 hover:border-slate-300 dark:hover:border-slate-600 hover:shadow-md"
    )}>
      <button onClick={onToggle} className="w-full text-left px-6 py-5 flex items-center gap-4">
        <div className={cn("w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 shadow-lg", c.bg)}>
          <Icon className="w-5 h-5 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">{module.title}</h3>
            <span className="text-xs text-slate-400 italic hidden sm:inline">{module.subtitle}</span>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-1">{module.description}</p>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", c.badge)}>{module.subComponents.length}</span>
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300">{module.examples.length} ex.</span>
          <div className={cn("w-7 h-7 rounded-lg flex items-center justify-center transition-colors", isExpanded ? c.bgLight : "bg-slate-50 dark:bg-slate-700")}>
            {isExpanded ? <ChevronDown className={cn("w-4 h-4", c.icon)} /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
          </div>
        </div>
      </button>
      {isExpanded && (
        <div className="px-6 pb-6 animate-fade-in">
          <div className="h-px bg-slate-100 dark:bg-slate-700 mb-5" />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div>
              <div className="flex items-center gap-2 mb-3">
                <CircleDot className={cn("w-4 h-4", c.icon)} />
                <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Sub-components</h4>
              </div>
              <div className="space-y-2">
                {module.subComponents.map((sub, i) => (
                  <div key={i} className={cn("flex items-start gap-2.5 px-3 py-2.5 rounded-xl border", c.bgLight, c.border)}>
                    <div className={cn("w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0", c.dot)} />
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-slate-800 dark:text-slate-200">{sub.name}</div>
                      {sub.detail && <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{sub.detail}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2 mb-3">
                <HelpCircle className={cn("w-4 h-4", c.icon)} />
                <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Example Customer Questions</h4>
              </div>
              <div className="space-y-3">
                {module.examples.map((ex, i) => (
                  <div key={i} className="flex items-start gap-2.5 px-3 py-2.5 rounded-xl bg-slate-50 dark:bg-slate-700/50 border border-slate-100 dark:border-slate-700 hover:border-slate-200 dark:hover:border-slate-600 transition-colors">
                    <div className="flex-shrink-0 mt-0.5">
                      <div className={cn("w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold text-white", c.bg)}>{i + 1}</div>
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-slate-800 dark:text-slate-200 italic">&ldquo;{ex.question}&rdquo;</div>
                      <div className="flex items-start gap-1.5 mt-1.5">
                        <ArrowRight className={cn("w-3 h-3 mt-0.5 flex-shrink-0", c.icon)} />
                        <div className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">{ex.why}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function CapabilitiesShowcase() {
  const [expandedModules, setExpandedModules] = useState<Set<string>>(new Set());
  const toggleModule = (id: string) => {
    setExpandedModules(prev => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  };
  const totalExamples = MODULES.reduce((s, m) => s + m.examples.length, 0);
  const totalSubs = MODULES.reduce((s, m) => s + m.subComponents.length, 0);

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <div className="bg-gradient-to-br from-blue-600 via-violet-600 to-indigo-700 rounded-2xl p-8 text-white relative overflow-hidden">
        <div className="absolute inset-0 opacity-10" style={{ backgroundImage: "radial-gradient(circle at 1px 1px, white 1px, transparent 0)", backgroundSize: "32px 32px" }} />
        <div className="relative">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-white/20 backdrop-blur-sm flex items-center justify-center">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold">Expert Modules</h1>
              <p className="text-blue-100 text-sm">Knowledge Graph-powered reasoning capabilities</p>
            </div>
          </div>
          <p className="text-blue-100 text-sm mt-3 max-w-2xl leading-relaxed">
            Every module is powered by graph-stored domain knowledge — zero hardcoded business logic.
            The system reasons through causal physics, trait matching, and constraint propagation to deliver expert-level technical consultation.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard value={String(MODULES.length)} label="Expert Modules" icon={Layers} />
        <StatCard value={String(totalSubs)} label="Sub-components" icon={CircleDot} />
        <StatCard value={String(totalExamples)} label="Example Scenarios" icon={HelpCircle} />
        <StatCard value="4" label="Knowledge Graph Layers" icon={Atom} />
      </div>

      <div className="flex items-center justify-between">
        <div className="text-sm text-slate-500 dark:text-slate-400">{expandedModules.size} of {MODULES.length} expanded</div>
        <div className="flex gap-2">
          <button onClick={() => setExpandedModules(new Set(MODULES.map(m => m.id)))} className="px-3 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors">Expand All</button>
          <button onClick={() => setExpandedModules(new Set())} className="px-3 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors">Collapse All</button>
        </div>
      </div>

      <div className="space-y-3">
        {MODULES.map((m) => (
          <ModuleCard key={m.id} module={m} isExpanded={expandedModules.has(m.id)} onToggle={() => toggleModule(m.id)} />
        ))}
      </div>

      <div className="bg-white/60 dark:bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-200/60 dark:border-slate-700/60 p-6 text-center">
        <p className="text-sm text-slate-500 dark:text-slate-400">All modules are domain-agnostic — the engine reads rules, traits, and constraints from the Knowledge Graph.</p>
        <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">To extend coverage, add new nodes and relationships to the graph. No code changes required.</p>
      </div>
    </div>
  );
}
