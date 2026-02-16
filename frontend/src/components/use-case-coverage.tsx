"use client";

import { useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ChevronRight,
  Mail,
  Building2,
  Factory,
  Flame,
  Snowflake,
  Wind,
  Shield,
  Layers,
  ArrowRight,
  Ruler,
  Box,
  Beaker,
  Cross,
  Wrench,
  FileQuestion,
  CircleDot,
  Package,
} from "lucide-react";
import { cn } from "@/lib/utils";

type CoverageStatus = "covered" | "partial" | "not-covered";

interface EmailExample {
  subject: string;
  from: string;
  snippet: string;
}

interface UseCase {
  id: string;
  title: string;
  description: string;
  status: CoverageStatus;
  icon: React.ComponentType<{ className?: string }>;
  products: string[];
  parameters: string[];
  emailExamples: EmailExample[];
  whatWorks: string[];
  whatsGap: string[];
  emailCount: number;
  frequency: string;
}

const STATUS_CONFIG: Record<CoverageStatus, { label: string; color: string; bg: string; border: string; icon: React.ComponentType<{ className?: string }> }> = {
  covered: {
    label: "Fully Covered",
    color: "text-emerald-700 dark:text-emerald-400",
    bg: "bg-emerald-50 dark:bg-emerald-950/30",
    border: "border-emerald-200 dark:border-emerald-800",
    icon: CheckCircle2,
  },
  partial: {
    label: "Partially Covered",
    color: "text-amber-700 dark:text-amber-400",
    bg: "bg-amber-50 dark:bg-amber-950/30",
    border: "border-amber-200 dark:border-amber-800",
    icon: AlertTriangle,
  },
  "not-covered": {
    label: "Not Covered",
    color: "text-red-700 dark:text-red-400",
    bg: "bg-red-50 dark:bg-red-950/30",
    border: "border-red-200 dark:border-red-800",
    icon: XCircle,
  },
};

const USE_CASES: UseCase[] = [
  // === COVERED ===
  {
    id: "gdb-standard",
    title: "Standard Filter Housing (GDB)",
    description: "Galvanized duct filter cabinets for bag/pocket and compact filters. The most common inquiry type — standard sizing, material selection, and transition pieces.",
    status: "covered",
    icon: Box,
    products: ["GDB", "TT", "PT"],
    parameters: ["Dimensions", "Airflow", "Material", "Filter class", "Transitions"],
    emailCount: 7,
    frequency: "Most common (26%)",
    emailExamples: [
      {
        subject: "Sv: Hagalund Filter",
        from: "Stefan Lundgren → Micael",
        snippet: "GDB 1800x1200, 750/800mm djup, PG-anslutning. Vänsterhängd lucka. 6x ePM10 50% 592x592x635-4 filter. 20% rabatt på skåp.",
      },
      {
        subject: "Sv: Skåp Grustag. VB: Offert",
        from: "Bravida Örnsköldsvik",
        snippet: "GDB-600x900-550-R-PG-FZ. Luftflöde 1200 l/s. ePM10 50% filter. Ingen övergång på skåpet.",
      },
      {
        subject: "Sv: VB: (VEOM 12,000 l/s)",
        from: "Customer → Micael",
        snippet: "2x GDB 1800x1500x750 R-PG-FZ. 12,000 l/s totalt, 2 fläktar à 6,000 l/s. Alternativ: 1800x1200 vid max 20,400 m³/h.",
      },
    ],
    whatWorks: [
      "All 28 GDB sizes in graph with weight, dimensions, filter module layout",
      "Airflow capacity per size (e.g. 1800x1500 = 25,500 m³/h)",
      "All 5 materials (FZ, AZ, RF, SF, ZM) with corrosion classes",
      "Transition pieces (TT conical + PT flat) with duct diameters",
      "Filter module layout (full, half, quarter) per size",
      "Installation constraints and assembly rules",
    ],
    whatsGap: [],
  },
  {
    id: "gdc-carbon",
    title: "Carbon Filter Housing (GDC)",
    description: "Cartridge filter cabinets for activated carbon and chemical media. Often requested in stainless steel for industrial environments.",
    status: "covered",
    icon: Beaker,
    products: ["GDC", "GDC FLEX"],
    parameters: ["Dimensions", "Material (RF/SF)", "Cartridge count", "Cylinder type"],
    emailCount: 3,
    frequency: "Common (11%)",
    emailExamples: [
      {
        subject: "Sv: FILTEROFFERT STERCO / NYFORS PST GDC SKÅP ROSTFRITT",
        from: "Sterco / Nyfors PST",
        snippet: "2 GDC i rostfritt: GDC-900x1200-900-R-PG-RF + GDC-600x600x900-RF. Kolcylindrar: 48x + 16x Scandsorb Cylinder ECO-C 9000 4mm KOH/KI 600mm.",
      },
      {
        subject: "Sv: (Alunda Energispar)",
        from: "Alunda Energispar",
        snippet: "GDC 600x300x750 RF (rostfritt). Enkel offert.",
      },
    ],
    whatWorks: [
      "12 GDC sizes + 6 GDC FLEX sizes in graph",
      "Carbon cylinder specs (Scandsorb ECO-C 2600/9000, 450/600mm)",
      "Stainless steel (RF) and acid-proof (SF) materials",
      "Cartridge count per housing size",
      "Polisfilter option for 900/950mm length",
    ],
    whatsGap: [],
  },
  {
    id: "gdmi-insulated",
    title: "Insulated Filter Housing (GDMI)",
    description: "Double-walled insulated module cabinets. Used where condensation prevention is needed.",
    status: "covered",
    icon: Snowflake,
    products: ["GDMI", "GDMI FLEX"],
    parameters: ["Dimensions", "Material (AZ/ZM)", "Insulation", "Filter type"],
    emailCount: 2,
    frequency: "Regular (7%)",
    emailExamples: [
      {
        subject: "Sv: offert filterskåp (urgent)",
        from: "Sanna → Micael",
        snippet: "GDMI-600x600-600-R-PG-AZ. Art. 9369010131. Filter 592x592x360. Pris: 14513 SEK, 20% rabatt = 11610 SEK. Leverans: 4 veckor.",
      },
    ],
    whatWorks: [
      "44 GDMI sizes (largest range) + 7 GDMI FLEX sizes",
      "Sizes up to 2400x2400 for large installations",
      "AZ and ZM materials (not available in RF/SF — correctly enforced)",
      "Airflow capacity per size at 3400 m³/h reference",
    ],
    whatsGap: [],
  },
  {
    id: "gdp-panel",
    title: "Panel Filter Housing (GDP)",
    description: "Flat filter cabinets for panel/pleat pre-filters. Used for intake air filtration and pre-filter stages.",
    status: "covered",
    icon: Layers,
    products: ["GDP", "PFF"],
    parameters: ["Dimensions", "Frame depth (25/50/100mm)", "Filter type"],
    emailCount: 3,
    frequency: "Regular (11%)",
    emailExamples: [
      {
        subject: "Pris på GDP 1400x1400",
        from: "Internal salesperson",
        snippet: "GDP 1400x1400. Fläns på aggregatsida, PG på motsatt sida. Inget artikelnummer behövs, bara pris.",
      },
      {
        subject: "VB: Offert Plitfilter (Vaddö 205)",
        from: "Customer",
        snippet: "GDP för tilloppskanal 1500x700. Pleatfilter F7 55% vid 96mm djup. Flöde: 150-1000 l/s säsongsvis.",
      },
    ],
    whatWorks: [
      "34 GDP sizes with PFF frame counts and airflow at 1.5 m/s",
      "All 5 materials supported",
      "Frame depths 25, 50, 100mm as options",
      "Compatible panel filter types (AIRSQUARE, AIRPANEL, AIRPANEL SELECT)",
    ],
    whatsGap: [],
  },
  {
    id: "acid-resistant",
    title: "Acid-Resistant Stainless Steel Housings",
    description: "Housings in syrafast (SF) material for chemically aggressive environments like electrolysis plants and smelters.",
    status: "covered",
    icon: Shield,
    products: ["GDB-SF"],
    parameters: ["Material SF (C5.1)", "Multi-stage filtration", "Wall-mount half-module"],
    emailCount: 1,
    frequency: "Occasional",
    emailExamples: [
      {
        subject: "Sv: FENIX - Filterskåp och filter",
        from: "FENIX / Boliden Rönnskär",
        snippet: "3 filterskåp i syrafast: 2x GDB-600x600-750-PG-R-SF (M5 + F7 i serie) + 1x GDB-600x300-550-PG-R-SF (F7, väggmonterat). Nytt elektrolysanlägg. Inga galvaniserade delar tillåtna.",
      },
    ],
    whatWorks: [
      "SF material (C5.1 corrosion class) fully modeled",
      "Environment-driven material enforcement blocks FZ/AZ in corrosive environments",
      "2-stage assembly (M5 pre-filter + F7 fine) supported",
      "Half-module (600x300) sizing available",
      "Installation constraints enforce minimum corrosion class per environment",
    ],
    whatsGap: [],
  },
  {
    id: "transitions",
    title: "Transition Pieces & Accessories",
    description: "Conical (TT) and flat (PT) transitions from rectangular housings to round ducts. EXL locking and filter profiles.",
    status: "covered",
    icon: ArrowRight,
    products: ["TT", "PT", "EXL", "Filter Profil"],
    parameters: ["Housing size", "Duct diameter", "Material"],
    emailCount: 5,
    frequency: "Included in most quotes",
    emailExamples: [
      {
        subject: "Sv: kolfilter samt filterlåda",
        from: "Customer",
        snippet: "GDP-300x600-100-R-PG-FZ + PT-300x600-315-FZ. Alternativ i ZM: GDP-300x600-100-R-PG-ZM + PT-300x600-315-ZM.",
      },
    ],
    whatWorks: [
      "33 transition piece sizes per product family",
      "Round duct diameter mapping (250-1250mm)",
      "Both TT (conical) and PT (flat) types",
      "Material variants (FZ, AZ, SF, ZM)",
    ],
    whatsGap: [],
  },

  // === PARTIAL ===
  {
    id: "multi-stage-food",
    title: "Multi-Stage System Design (3-stage)",
    description: "Complete filtration system design with 3 housings in series: pre-filter → carbon → polish filter. Required for food processing and recirculation systems.",
    status: "partial",
    icon: Factory,
    products: ["GDB + GDC + GDB"],
    parameters: ["Application context", "Multi-stage assembly", "Recirculation"],
    emailCount: 2,
    frequency: "Complex high-value projects",
    emailExamples: [
      {
        subject: "Sv: Ta fram förslag på filter + filterskåp",
        from: "Food processing plant",
        snippet: "3-stegs filtrering för köttmarinad-sprutmaskin: Steg 1: GDB med AIRPOCKET ECO ePM10 70% (fettpartiklar). Steg 2: GDC med kolcylindrar (lukt). Steg 3: GDB med AIRCUBE ECO ePM1 60% (polisfilter). Luften ska renas och återföras till rummet.",
      },
      {
        subject: "Sv: Förfrågan (BT Ventilation)",
        from: "BT Ventilation",
        snippet: "GDB 1800x600 med 3 steg i serie: M5 + F9 + HEPA H13. 2500 l/s. Höjdbegränsad (1 modul hög). Micael beräknade: vid 2082 l/s = 25+75+250 = 350 Pa > 300 Pa mål. Tekniskt genomförbart? Nej.",
      },
    ],
    whatWorks: [
      "All individual products (GDB, GDC) exist with full specs",
      "2-stage assembly (pre-filter + main) supported in engine",
      "DependencyRules exist for kitchen→carbon and dusty→carbon pre-filtration",
      "Carbon cylinder and pocket filter selection works",
    ],
    whatsGap: [
      "3-stage assembly not implemented (engine supports 2-stage only)",
      "\"Food processing\" not modeled as an Application in the graph",
      "Pressure drop calculations not available (case G2: M5+F9+H13 feasibility check)",
      "CARBOACTIV POCKET (combo pocket+carbon) filters not in FilterConsumable",
      "Recirculation system concept not modeled",
    ],
  },
  {
    id: "hospital-tender",
    title: "Hospital Tender (Multi-Product Bid)",
    description: "Complex competitive tenders requiring multiple product types: HEPA housings, insulated housings, filter banks, and Camfil cross-references.",
    status: "partial",
    icon: Hospital,
    products: ["GDR Nano", "GDMI", "Filter banks"],
    parameters: ["Hospital environment", "Camfil equivalents", "Filter banks", "HEPA class"],
    emailCount: 2,
    frequency: "High-value tenders",
    emailExamples: [
      {
        subject: "Sv: Anbudsförfrågan gällande Huddinge Sjukhus BY C1",
        from: "Arnaldo Roman Mallo (Airteam Creovent)",
        snippet: "LR108: GDR Nano 1/1 (art. 7101011329, 45444 SEK). LR109: GDMI-900x600-800-R-PG-AZ. Filterbankar: 6x 2400x1800mm + 4x 1800x1800mm. Camfil-ekvivalenter: Cambox 610-S + CamCube HF-S.",
      },
    ],
    whatWorks: [
      "Hospital recognized as application with hygiene stressor",
      "GDMI housing fully modeled (44 sizes)",
      "Material enforcement (hospital → C5 minimum) works",
      "Camfil competitor cross-references exist for filters (Hi-Flo, Opakfil, etc.)",
      "Camfil housing cross-refs partially exist (CamBox, CamCube)",
    ],
    whatsGap: [
      "GDR Nano product family completely missing from graph",
      "Filter banks (filterbankar) not a product — wall-mount frame systems",
      "Competitive tender workflow (multi-product bid, deadline tracking) not supported",
    ],
  },
  {
    id: "apartment-recirculation",
    title: "Apartment Recirculation with Combined Filters",
    description: "Insulated housings with combination pocket+carbon filters for apartment buildings with kitchen recirculation.",
    status: "partial",
    icon: Building2,
    products: ["GDMI", "PASKAL filters"],
    parameters: ["Kitchen/recirculation", "Combined media", "Circular connection"],
    emailCount: 1,
    frequency: "Niche but recurring",
    emailExamples: [
      {
        subject: "Sv: Kolfilterlåda + kolfilter Gretas glänta",
        from: "Customer via Stefan",
        snippet: "GDMI-600x600-850-R-PG-ZM (isolerat, magnelis). Konisk övergång 600x600 till dia 400. CARBOACTIV POCKET ECO DUOSORB ePM10 75% 592x592x500. Lägenhets-aggregat, återluftskanal, 550 l/s.",
      },
    ],
    whatWorks: [
      "GDMI product family fully modeled",
      "ZM (magnelis) material available",
      "Kitchen environment with grease/odor stressors exists",
      "Transition to circular duct (TT) available",
    ],
    whatsGap: [
      "CARBOACTIV POCKET / PASKAL DUOSORB combo filters not in FilterConsumable",
      "\"Apartment recirculation\" not a recognized application context",
    ],
  },
  {
    id: "bus-terminal",
    title: "Pre-Filter for Bus Terminal / Large AHU",
    description: "Large GDP flat filter housings with PFF frames and coarse roll media as pre-filters to protect main AHU aggregates.",
    status: "partial",
    icon: Wind,
    products: ["GDP", "PFF"],
    parameters: ["Large dimensions (1800x1800)", "Coarse roll media", "Bus terminal"],
    emailCount: 1,
    frequency: "Occasional",
    emailExamples: [
      {
        subject: "Sv: Pris på Filterram för planfilter Bussterminal",
        from: "Customer",
        snippet: "GDP-1800x1800-25-R-PG-FZ + 4x PFF-892x892-25-FZ + Airroll Eco NoGlass Coarse 80% 892x892x21. Alternativ: GDP-1500x1500-25. Nya artikelnummer behövde skapas.",
      },
    ],
    whatWorks: [
      "GDP and PFF products fully modeled",
      "Large sizes (1800x1800) available in dimension tables",
    ],
    whatsGap: [
      "Airroll Eco (coarse roll media) not in FilterConsumable — only rigid panel filters",
      "\"Bus terminal\" not a recognized application",
    ],
  },
  {
    id: "industrial-carbon-revision",
    title: "Mid-Conversation Revision & Upsizing",
    description: "Cases where the housing needs to be resized mid-conversation when actual airflow or filter count is revealed. Common in carbon filter projects.",
    status: "partial",
    icon: Ruler,
    products: ["GDB", "GDC", "GDMI FLEX"],
    parameters: ["Mid-conversation upsizing", "Revised dimensions", "Carbon cylinder count"],
    emailCount: 2,
    frequency: "Regular pattern",
    emailExamples: [
      {
        subject: "Sv: Filterskåp (revision)",
        from: "Customer (Toruz #025547)",
        snippet: "Ursprungligt: GDB-1200x600-750. Reviderat: GDB-1800x900 (för 3 hela + 3 halva kolpåsfiltermoduler) + TT-1800x900-1400x600 L500 PG/PG FZ.",
      },
      {
        subject: "Sv: Kolfilter (Storfors plåt, Skellefteå)",
        from: "Boliden PC Koppar reference",
        snippet: "Först GDMI Flex 900x600x900. Reviderat till 1200x600x850 med 28 kolcylindrar när verkligt luftflöde (1000 l/s) avslöjades.",
      },
    ],
    whatWorks: [
      "Product families and sizing tables fully available",
      "Session state (Layer 4) persists parameters across turns",
      "Transition pieces can be re-calculated after resize",
    ],
    whatsGap: [
      "Carbon pocket filters (CARBOACTIV) not in consumable database",
      "\"Boliden/mining\" not a recognized industrial application",
    ],
  },

  // === NOT COVERED ===
  {
    id: "gdr-nano-hepa",
    title: "HEPA Filter Housing (GDR Nano)",
    description: "Compact HEPA/ULPA filter housings for cleanrooms, chemical plants, and hospitals. A separate product family not in the current catalog or graph.",
    status: "not-covered",
    icon: Flame,
    products: ["GDR Nano"],
    parameters: ["HEPA class (H13/H14)", "NANOCLASS filters", "Small duct connections"],
    emailCount: 2,
    frequency: "High-value specialized",
    emailExamples: [
      {
        subject: "RE: Nouryon Tik Tock - M22.0003 air inlet filters",
        from: "Worley/Belgium → Micael",
        snippet: "GDR Nano 0.5x1 + 1x1. NANOCLASS DEEPPLEAT SELECT E11 + H14, MDF-ram. Alt: NANOCLASS CUBE N ECO E11 + H14, SS-ram, 3400 m³/h. Kund avvisar MDF — kräver rostfri ram.",
      },
      {
        subject: "Sv: Anbudsförfrågan Huddinge Sjukhus",
        from: "Micael → Stefan, Emma",
        snippet: "GDR Nano 1/1 = art. 7101011329 = 45444 SEK. Övergång dia 315 = art. 7302011324. AIRCUBE N ECO ePM1 80% 610x610x292.",
      },
    ],
    whatWorks: [],
    whatsGap: [
      "GDR Nano product family does not exist in graph",
      "No dimension table, sizing rules, or capacity data",
      "No housing-to-HEPA-filter compatibility mapping",
      "\"Chemical plant\" not an application in the graph",
      "Requires separate product catalog (not in current PDF)",
    ],
  },
  {
    id: "filter-banks",
    title: "Filter Banks (Filterbankar)",
    description: "Large wall-mount filter frame systems for AHUs. Completely different from cabinet-style housings — mounting frames assembled into walls up to 2400x1800mm.",
    status: "not-covered",
    icon: Package,
    products: ["Filter banks", "Mounting frames", "Surrounding frames"],
    parameters: ["Wall dimensions", "Frame count", "Mounting type"],
    emailCount: 1,
    frequency: "Large tenders only",
    emailExamples: [
      {
        subject: "Sv: Anbudsförfrågan Huddinge Sjukhus BY C1",
        from: "Stefan Lundgren",
        snippet: "Kompletta filterbankar med monteringsramar samt omgivande ram. 6 st 2400x1800mm + 4 st 1800x1800mm.",
      },
    ],
    whatWorks: [],
    whatsGap: [
      "No product family for filter banks exists",
      "Completely different product category from cabinet housings",
      "No dimension/sizing data available",
      "Not in the current PDF catalog — requires separate source",
    ],
  },
  {
    id: "pressure-feasibility",
    title: "Pressure Drop Feasibility Analysis",
    description: "Engineering calculations to determine if a filter combination is feasible within a pressure budget. Mikael does this manually today.",
    status: "not-covered",
    icon: CircleDot,
    products: ["Any multi-stage"],
    parameters: ["Initial/final Pa per filter", "Total Pa budget", "Airflow"],
    emailCount: 1,
    frequency: "Complex technical consults",
    emailExamples: [
      {
        subject: "Sv: Förfrågan (BT Ventilation)",
        from: "Micael (calculation)",
        snippet: "M5+F9+H13 vid 2082 l/s: init tryckfall 25+75+250 = 350 Pa. Kundens mål: max 300 Pa. Slutsats: tekniskt ogörligt med dessa parametrar.",
      },
    ],
    whatWorks: [],
    whatsGap: [
      "No pressure drop data for any filter type in the graph",
      "No Pa calculation engine",
      "Cannot determine feasibility of multi-stage combinations",
      "Filter-specific init/final Pa values would need to come from filter catalogs",
    ],
  },
  {
    id: "order-history",
    title: "Repeat Orders & Price Updates",
    description: "Customers requesting refreshed pricing on previously ordered configurations. Requires access to order history / SAP.",
    status: "not-covered",
    icon: FileQuestion,
    products: ["Any"],
    parameters: ["Previous order number", "Updated pricing"],
    emailCount: 2,
    frequency: "Regular",
    emailExamples: [
      {
        subject: "Sv: Offert Granitor systems",
        from: "Granitor Systems AB, Trollhättan",
        snippet: "Samma artiklar som föregående order S346839. Kunden vill ha aktuell prissättning. Leverans 4-6 veckor.",
      },
    ],
    whatWorks: [],
    whatsGap: [
      "No integration with SAP / order management system",
      "No access to historical pricing or order records",
      "No customer account / order number lookup",
      "Outside tool scope — requires ERP integration",
    ],
  },
];

function StatusBadge({ status }: { status: CoverageStatus }) {
  const config = STATUS_CONFIG[status];
  const Icon = config.icon;
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border", config.bg, config.color, config.border)}>
      <Icon className="w-3.5 h-3.5" />
      {config.label}
    </span>
  );
}

function UseCaseCard({ useCase }: { useCase: UseCase }) {
  const [expanded, setExpanded] = useState(false);
  const statusConfig = STATUS_CONFIG[useCase.status];

  return (
    <div className={cn(
      "rounded-xl border transition-all",
      "bg-white dark:bg-slate-900/50",
      expanded ? "border-blue-200 dark:border-blue-800 shadow-lg shadow-blue-500/5" : "border-slate-200 dark:border-slate-700/60 hover:border-slate-300 dark:hover:border-slate-600",
    )}>
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-5 py-4 flex items-start gap-4 text-left"
      >
        <div className={cn(
          "w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5",
          useCase.status === "covered" && "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400",
          useCase.status === "partial" && "bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400",
          useCase.status === "not-covered" && "bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400",
        )}>
          <useCase.icon className="w-5 h-5" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h3 className="font-semibold text-slate-900 dark:text-slate-100">{useCase.title}</h3>
            <StatusBadge status={useCase.status} />
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">{useCase.description}</p>

          <div className="flex items-center gap-4 mt-2">
            <span className="text-xs text-slate-400 dark:text-slate-500 flex items-center gap-1">
              <Mail className="w-3 h-3" />
              {useCase.emailCount} email{useCase.emailCount !== 1 ? "s" : ""}
            </span>
            <span className="text-xs text-slate-400 dark:text-slate-500">
              {useCase.frequency}
            </span>
            <div className="flex items-center gap-1">
              {useCase.products.map((p) => (
                <span key={p} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 font-mono">
                  {p}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="flex-shrink-0 mt-1">
          {expanded ? (
            <ChevronDown className="w-5 h-5 text-slate-400" />
          ) : (
            <ChevronRight className="w-5 h-5 text-slate-400" />
          )}
        </div>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-slate-100 dark:border-slate-800 pt-4">
          {/* Email examples */}
          <div>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
              Real Email Examples
            </h4>
            <div className="space-y-2">
              {useCase.emailExamples.map((email, idx) => (
                <div key={idx} className="rounded-lg bg-slate-50 dark:bg-slate-800/50 border border-slate-100 dark:border-slate-700/50 p-3">
                  <div className="flex items-start gap-2">
                    <Mail className="w-3.5 h-3.5 text-slate-400 mt-0.5 flex-shrink-0" />
                    <div className="min-w-0">
                      <div className="text-xs font-medium text-slate-700 dark:text-slate-300">{email.subject}</div>
                      <div className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">{email.from}</div>
                      <p className="text-xs text-slate-600 dark:text-slate-400 mt-1.5 leading-relaxed italic">
                        &ldquo;{email.snippet}&rdquo;
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* What works / What's missing */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {useCase.whatWorks.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider mb-2 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  What the tool handles
                </h4>
                <ul className="space-y-1">
                  {useCase.whatWorks.map((item, idx) => (
                    <li key={idx} className="text-xs text-slate-600 dark:text-slate-400 flex items-start gap-1.5">
                      <span className="text-emerald-500 mt-0.5 flex-shrink-0">+</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {useCase.whatsGap.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-red-600 dark:text-red-400 uppercase tracking-wider mb-2 flex items-center gap-1">
                  <XCircle className="w-3.5 h-3.5" />
                  Gaps to close
                </h4>
                <ul className="space-y-1">
                  {useCase.whatsGap.map((item, idx) => (
                    <li key={idx} className="text-xs text-slate-600 dark:text-slate-400 flex items-start gap-1.5">
                      <span className="text-red-500 mt-0.5 flex-shrink-0">-</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Parameters */}
          <div>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
              Key Parameters
            </h4>
            <div className="flex flex-wrap gap-1.5">
              {useCase.parameters.map((param) => (
                <span key={param} className="text-xs px-2 py-0.5 rounded-full bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400 border border-blue-100 dark:border-blue-800">
                  {param}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

type FilterType = "all" | CoverageStatus;

export function UseCaseCoverage() {
  const [filter, setFilter] = useState<FilterType>("all");

  const filtered = filter === "all" ? USE_CASES : USE_CASES.filter((uc) => uc.status === filter);

  const counts = {
    covered: USE_CASES.filter((uc) => uc.status === "covered").length,
    partial: USE_CASES.filter((uc) => uc.status === "partial").length,
    "not-covered": USE_CASES.filter((uc) => uc.status === "not-covered").length,
  };

  const totalEmails = USE_CASES.reduce((sum, uc) => sum + uc.emailCount, 0);
  const coveredEmails = USE_CASES.filter((uc) => uc.status === "covered").reduce((sum, uc) => sum + uc.emailCount, 0);
  const partialEmails = USE_CASES.filter((uc) => uc.status === "partial").reduce((sum, uc) => sum + uc.emailCount, 0);

  return (
    <div className="space-y-6">
      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="rounded-xl bg-white dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700/60 p-5">
          <div className="text-3xl font-bold text-slate-900 dark:text-slate-100">27</div>
          <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">Unique email conversations analyzed</div>
          <div className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">From Mikael Kylefalk&apos;s inbox</div>
        </div>

        <div className="rounded-xl bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-800/60 p-5">
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-emerald-700 dark:text-emerald-400">{coveredEmails}</span>
            <span className="text-sm text-emerald-600 dark:text-emerald-500">/ {totalEmails} emails</span>
          </div>
          <div className="text-sm text-emerald-700 dark:text-emerald-400 mt-1 font-medium">{counts.covered} use cases fully covered</div>
          <div className="w-full bg-emerald-200 dark:bg-emerald-900/50 rounded-full h-1.5 mt-3">
            <div className="bg-emerald-500 h-1.5 rounded-full" style={{ width: `${(coveredEmails / totalEmails) * 100}%` }} />
          </div>
        </div>

        <div className="rounded-xl bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800/60 p-5">
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-amber-700 dark:text-amber-400">{partialEmails}</span>
            <span className="text-sm text-amber-600 dark:text-amber-500">/ {totalEmails} emails</span>
          </div>
          <div className="text-sm text-amber-700 dark:text-amber-400 mt-1 font-medium">{counts.partial} use cases partially covered</div>
          <div className="w-full bg-amber-200 dark:bg-amber-900/50 rounded-full h-1.5 mt-3">
            <div className="bg-amber-500 h-1.5 rounded-full" style={{ width: `${(partialEmails / totalEmails) * 100}%` }} />
          </div>
        </div>

        <div className="rounded-xl bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800/60 p-5">
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-red-700 dark:text-red-400">{totalEmails - coveredEmails - partialEmails}</span>
            <span className="text-sm text-red-600 dark:text-red-500">/ {totalEmails} emails</span>
          </div>
          <div className="text-sm text-red-700 dark:text-red-400 mt-1 font-medium">{counts["not-covered"]} use cases not covered</div>
          <div className="w-full bg-red-200 dark:bg-red-900/50 rounded-full h-1.5 mt-3">
            <div className="bg-red-500 h-1.5 rounded-full" style={{ width: `${((totalEmails - coveredEmails - partialEmails) / totalEmails) * 100}%` }} />
          </div>
        </div>
      </div>

      {/* Coverage bar */}
      <div className="rounded-xl bg-white dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700/60 p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Email Coverage by Volume</h3>
          <span className="text-xs text-slate-400">{Math.round((coveredEmails / totalEmails) * 100)}% fully covered, {Math.round(((coveredEmails + partialEmails) / totalEmails) * 100)}% with partial</span>
        </div>
        <div className="flex rounded-full h-4 overflow-hidden bg-slate-100 dark:bg-slate-800">
          <div
            className="bg-emerald-500 transition-all duration-500"
            style={{ width: `${(coveredEmails / totalEmails) * 100}%` }}
            title={`Covered: ${coveredEmails} emails`}
          />
          <div
            className="bg-amber-400 transition-all duration-500"
            style={{ width: `${(partialEmails / totalEmails) * 100}%` }}
            title={`Partial: ${partialEmails} emails`}
          />
          <div
            className="bg-red-400 transition-all duration-500"
            style={{ width: `${((totalEmails - coveredEmails - partialEmails) / totalEmails) * 100}%` }}
            title={`Not covered: ${totalEmails - coveredEmails - partialEmails} emails`}
          />
        </div>
        <div className="flex items-center gap-6 mt-2">
          <span className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
            Fully covered ({coveredEmails})
          </span>
          <span className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
            Partial ({partialEmails})
          </span>
          <span className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-red-400" />
            Not covered ({totalEmails - coveredEmails - partialEmails})
          </span>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl w-fit">
        {[
          { id: "all" as FilterType, label: "All", count: USE_CASES.length },
          { id: "covered" as FilterType, label: "Covered", count: counts.covered },
          { id: "partial" as FilterType, label: "Partial", count: counts.partial },
          { id: "not-covered" as FilterType, label: "Not Covered", count: counts["not-covered"] },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setFilter(tab.id)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all",
              filter === tab.id
                ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm"
                : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300",
            )}
          >
            {tab.label}
            <span className={cn(
              "text-[10px] px-1.5 py-0.5 rounded-full",
              filter === tab.id
                ? "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400"
                : "bg-slate-200 dark:bg-slate-600 text-slate-500 dark:text-slate-400",
            )}>
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* Use case cards */}
      <div className="space-y-3">
        {filtered.map((uc) => (
          <UseCaseCard key={uc.id} useCase={uc} />
        ))}
      </div>

      {/* Source note */}
      <div className="rounded-lg bg-slate-50 dark:bg-slate-800/30 border border-slate-200 dark:border-slate-700/40 px-4 py-3">
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Analysis based on 27 unique email conversations from Mikael Kylefalk&apos;s inbox (testdata/mails_mikael/).
          Cross-referenced against Neo4j knowledge graph (12 ProductFamilies, 273 DimensionModules, 11 Applications, 8 Environments, 5 Materials, 31 FilterConsumables)
          and product catalog (filter_housings_sweden.pdf, 24 pages, v01-09-2025).
        </p>
      </div>
    </div>
  );
}
