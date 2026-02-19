"use client";

import { useState, useRef } from "react";
import { Chat } from "@/components/chat";
import { resetSessionId } from "@/lib/api";
import { ThreadIngestor } from "@/components/thread-ingestor";
import { DocIngestor } from "@/components/doc-ingestor";
import { ThreadExplorer } from "@/components/thread-explorer";
import { KnowledgeRefinery } from "@/components/knowledge-refinery";
import { SettingsPanel } from "@/components/settings-panel";
import { TestLab } from "@/components/test-lab";
import { TestGenerator } from "@/components/test-generator";
import { CapabilitiesShowcase } from "@/components/capabilities-showcase";
import { ExpertReview } from "@/components/expert-review";
import { GraphAudit } from "@/components/graph-audit";
import { BatchResults } from "@/components/batch-results";
import BulkOffer from "@/components/bulk-offer";
import { UseCaseCoverage } from "@/components/use-case-coverage";
import {
  MessageSquare,
  Upload,
  Settings,
  Activity,
  ChevronLeft,
  ChevronRight,
  Users,
  Plug,
  BarChart3,
  Shield,
  Workflow,
  Lock,
  FileText,
  Bug,
  Loader2,
  FolderSearch,
  BookOpen,
  Trash2,
  FlaskConical,
  Compass,
  Wand2,
  LogOut,
  ClipboardCheck,
  Sun,
  Moon,
  Package,
} from "lucide-react";
import { useTheme } from "next-themes";
import Image from "next/image";
import { cn } from "@/lib/utils";
import { AuthGuard } from "@/components/auth-guard";
import { clearToken } from "@/lib/auth";

type ChatMode = "llm-driven" | "graphrag" | "graph-reasoning" | "neuro-symbolic";

type TabType = "chat" | "ingest" | "explore" | "knowledge" | "testlab" | "testgen" | "capabilities" | "expert-review" | "analytics" | "workflows" | "users" | "integrations" | "audit" | "batch-results" | "bulk-offer" | "use-cases" | "settings";
type IngestSubTab = "threads" | "docs";

interface NavItem {
  id: TabType;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  disabled?: boolean;
  devOnly?: boolean;
  section?: "main" | "enterprise" | "admin";
}

// Sample questions for dev mode - cleared for production
const SAMPLE_QUESTIONS: Record<string, string[]> = {};

// Sample case data for dev mode
const SAMPLE_CASES = {
  knittel: {
    name: "Knittel (Yuri)",
    text: `WG: Angebotsanfrage_Kanalgehäuse+Filter_1011910

From: Shebeta, Yuri <Yuri.Shebeta@mann-hummel.com>
Sent: Mon, Oct 16, 2023, 12:26 PM
To: d.rauschenbach@knittel-maschinenbau.de

Guten Tag Frau Rauschenbach,

vielen Dank für heutiges freundliches Gespräch.
ich bin der Außendienstmitarbeiter und Ihr zuständiger Ansprechpartner der Firma Mann + Hummel Life Science & Environment GmbH.
Sie können sich gern telefonisch oder per E-Mail mit allen Themen an mich wenden.

Wie ich es schon telefonisch bestätigt habe, sind wir bereit Ihnen zu unserem Angebot 200009087 ein Projektrabatt in Höhe von 3% geben.

Einer Auftragserteilung sehen wir erfreut entgegen.

Mit freundlichen Grüßen,
Yuri Shebeta
Sales Representative
MANN+HUMMEL Life Sciences & Environment Germany GmbH

---

From: d.rauschenbach@knittel-maschinenbau.de
Sent: Freitag, 13. Oktober 2023 08:19
To: Bernhardt, Anna <anna.bernhardt@mann-hummel.com>
Subject: AW: Angebotsanfrage_Kanalgehäuse+Filter_1011910

Sehr geehrte Frau Bernhardt,
können Sie mich bitte einmal zu dem angehängten Angebot zurückrufen.

Mit freundlichen Grüßen
i.A. Daniela Rauschenbach
Waldemar Knittel Glasbearbeitungs GmbH
Maschinenbau Bielefeld

---

From: Bernhardt, Anna <anna.bernhardt@mann-hummel.com>
Sent: Freitag, 29. September 2023 11:42
To: d.gerber@knittel-maschinenbau.de
Cc: Shebeta, Yuri; Alzaghari, Milad
Subject: WG: Angebotsanfrage_Kanalgehäuse+Filter_1011910

Sehr geehrter Herr Gerber,
haben Sie vielen herzlichen Dank für Ihre Angebotsanfrage.
Im Anhang übersende ich Ihnen unsere Angebote in zweifacher Ausführung für eine zweistufige sowie dreistufige Filterung. Die Lieferzeit liegt bei ca. 5-6 Wochen nach Auftragseingang.
Einer Auftragserteilung sehen wir erfreut entgegen.

Mit freundlichen Grüßen,
Anna Bernhardt
Leiterin Customer Care

---

From: Dennis Gerber <d.gerber@knittel-maschinenbau.de>
Sent: Montag, 25. September 2023 10:23
To: Alzaghari, Milad <Milad.Alzaghari@mann-hummel.com>
Subject: AW: Angebotsanfrage_Kanalgehäuse+Filter

Hallo Herr Alzaghari,
Können sie mir ein Angebot von dem aktuellen Stand zusenden?
Mit F7, F9 und E12 (und H13 als alternative für letzteren) Filter.
Vielen Dank im Voraus.

Mit freundlichen Grüßen
Dennis Gerber, M. Sc.
Konstruktion & Entwicklung
Knittel Glasbearbeitungs GmbH

---

From: Alzaghari, Milad <Milad.Alzaghari@mann-hummel.com>
Sent: Dienstag, 19. September 2023 15:37
To: Dennis Gerber <d.gerber@knittel-maschinenbau.de>
Subject: AW: Angebotsanfrage_Kanalgehäuse+Filter

Hallo Herr Gerber,
ich von Ihnen noch keine Rückmeldung erhalten, ob Sie mit dem Vorschlag einverstanden sind.
Wir haben mittlerweile ein fertiges Design. Hierfür benötigen wir Ihre Freigabe, damit wir den Stand bei uns für die Produktion freigeben.
Wir können im nächsten Schritt die kaufmännischen Themen besprechen.

Schöne Grüße
Milad Alzaghari
R&D, Life Sciences & Environment | Air Filtration
MANN+HUMMEL Life Sciences & Environment Germany GmbH

---

From: Alzaghari, Milad
Sent: Donnerstag, 14. September 2023 14:38
To: Dennis Gerber <d.gerber@knittel-maschinenbau.de>
Subject: AW: Angebotsanfrage_Kanalgehäuse+Filter

Hallo Herr Gerber,
vielen Dank für das Bild.
Es sieht tatsächlich nicht danach aus, dass das Gitter abnehmbar ist.
Meine Vermutung bzgl. der weiteren kleinen Gitter haben Sie bestätigt.
Der Anschluss über das Rohr wäre die einfachste Lösung. So können wir unser System mit einem Flansch ausstatten, welches das gleiche Lochbild hat.
Wenn diese Lösung für Sie passt und wir Ihre Zustimmung haben, dann machen wir uns an die Arbeit.

Grüße
Milad Alzaghari

---

From: Dennis Gerber <d.gerber@knittel-maschinenbau.de>
Sent: Mittwoch, 13. September 2023 16:34
To: Alzaghari, Milad <Milad.Alzaghari@mann-hummel.com>
Subject: WG: Angebotsanfrage_Kanalgehäuse+Filter

Hallo Herr Alzaghari,
Ich habe nun doch neue Infos. Weitere Bilder erhalte Ich morgen.
Allerdings gibt es eine weitere Problemstellung: der Motor wird über die beiden kleinen Gitter rechts vom großen gekühlt.
Dabei wird die angesaugte Luft ebenfalls mit der Prozessluft vermischt und somit verunreinigt, insofern dort kein Filter ist.
Wäre es möglich die Filter hinter dem Gebläse und Schalldämpfer zu platzieren? Der Anschluss wäre dann einfach über das Rohr, wie es rechts im Bild zu sehen ist.

Danke im Voraus.
Dennis Gerber, M. Sc.

---

From: Dennis Gerber <d.gerber@knittel-maschinenbau.de>
Sent: Mittwoch, 13. September 2023 11:27
To: Alzaghari, Milad <Milad.Alzaghari@mann-hummel.com>
Subject: AW: Angebotsanfrage_Kanalgehäuse+Filter

Hallo Herr Alzaghari,
Ich habe Elektror um vollständige CAD Daten gebeten, allerdings bis heute nichts erhalten.
Fotos kann ich leider auch nicht anbieten, da wir die Box noch nicht geliefert bekommen haben.
Das habe Ich grad noch online gefunden. Scheinbar ist das Gitter nicht abnehmbar.

Mit freundlichen Grüßen
Dennis Gerber, M. Sc.

---

From: Alzaghari, Milad <Milad.Alzaghari@mann-hummel.com>
Sent: Dienstag, 5. September 2023 20:33
To: Dennis Gerber <d.gerber@knittel-maschinenbau.de>
Subject: AW: Angebotsanfrage_Kanalgehäuse+Filter

Hallo Herr Gerber,
zunächst bedanke ich mich für die Zusendung der 3D Daten.
Leider konnten wir nicht viel erkennen, da Dummy Solid bzw. nur ein Volumenkörper ohne Details. Das Innere des Systems war leider nicht sichtbar, um die Konstruktion des Einlassgitters genauer auf Anbindungsmöglichkeiten zu prüfen.
Besteht die Möglichkeit das gesamte 3D Model zur Verfügung zu stellen?
Falls nein, können Sie mir bitte mitteilen, ob das Blechteil des Gitter abmontierbar ist?
Bilder wären ebenfalls hilfreich.

Danke im Voraus
Milad Alzaghari
R&D, MANN+HUMMEL

---

From: Dennis Gerber <d.gerber@knittel-maschinenbau.de>
Sent: Montag, 4. September 2023 15:07
To: Alzaghari, Milad <Milad.Alzaghari@mann-hummel.com>
Subject: AW: Angebotsanfrage_Kanalgehäuse+Filter

Hallo Herr Alzaghari,
Anbei wie letzte Woche besprochen, die Schallschutzhaube als STEP, an die das Filtergehäuse angeschlossen werden soll.
In Bezug auf den dritten Filter (Hepa) habe ich noch keine neuen Informationen, da mein Chef bis nächste Woche nicht im Hause ist. Aber aufgrund der Modularität sollte das ja kein Problem sein.

Mit freundlichen Grüßen
Dennis Gerber, M. Sc.
Konstruktion & Entwicklung
Knittel Glasbearbeitungs GmbH`
  },
  huddinge: {
    name: "Huddinge (Mikael)",
    text: `Huddinge Hospital (Huddinge Sjukhus) BY C1

Email 1: The Tender Request
From: Arnaldo Roman Mallo (Airteam Creovent AB)
Subject: Request for tender regarding Huddinge Hospital BY C1

You are hereby invited to submit your best price for the delivery listed below according to the attached documents.
Attached description and own quantities regarding Huddinge Hospital Building C1.
Own and alternative products - to be exchanged under your own responsibility.
Your prices must be broken down by item and NOTE included unit prices.
Shipping and packaging included in the price must be reported.
Your offer must be valid for 90 days.
We wish to have your prices ASAP but no later than: 2025-11-07
Your offer shall be marked with the facility name.

Best regards,
Arnaldo Roman Mallo
Calculation Manager
Airteam Creovent AB

---

Email 2: Internal Specification Discussion
From: Lundgren, Stefan <Stefan.Lundgren@mann-hummel.com>
Sent: November 3, 2025 at 14:32
To: Kylefalk, Micael; Landström, Emma
Subject: Re: Request for tender regarding Huddinge Hospital BY C1

Hi Micke.
Spoke to Emma about this earlier.
These are complete filter banks with mounting frames as well as a mounting frame surrounding them.
6 pieces 2400x1800 mm
4 pieces 1800x1800 mm
Then on page 46 we look if we have any equivalent to Camfil's cabinets that are specified.
Cambox 610-S for compact filter 610x610x292
Circular connection 315 mm
CamCube HF-S for compact filter 592x592x460
Connection 900x600 mm

Best regards,
Stefan Lundgren
Contract Manager / Sales Manager

---

Email 3: Internal Follow-up
From: Landström, Emma <emma.landstrom@mann-hummel.com>
Sent: November 7, 2025 at 08:25
To: Kylefalk, Micael; Lundgren, Stefan
Subject: Re: Request for tender regarding Huddinge Hospital BY C1

Hi Micke,
Can you push them so that we can submit this today.

---

Email 4: Pricing & Calculation
From: Kylefalk, Micael
Sent: November 7, 2025 at 10:48
To: Landström, Emma; Lundgren, Stefan
Subject: Re: Request for tender regarding Huddinge Hospital BY C1

Hi,
Returning with filter wall that HABE is calculating.

LR108
Filter cabinet GDR Nano 1/1 = 7101011329 = Price 45444 SEK = 20% discount = 36356 SEK
Transition dia 315 7302011324 = Price 5280 SEK = 20% discount = 6864 SEK
Filter AIRCUBE N ECO ePM1 80% 610x610x292 G-00-F2-XX-6HXX = 800481002927 = init pressure drop 140 Pa, end pressure drop 450Pa at 3400m3/h

LR109
Filter cabinet GDMI-900x600-800-R-PG-AZ = 9369010759
Filter 1/1 AIRCUBE ECO ePM1 80% 592x592x300 P-25-XX-XX-1NXX = 800410000141 = init pressure drop 100 Pa, end pressure drop 450Pa at 3400m3/h
Filter 1/2 AIRCUBE ECO ePM1 80% 592x287x300 P-25-XX-XX-1NXX = 800410000041 = init pressure drop 100 Pa, end pressure drop 450Pa at 3400m3/h

Best Regards
Micael Kylefalk
Product Manager Industrial`
  },
  nordic: {
    name: "Nordic Furniture (ATEX)",
    text: `Subject: Replacement Filters - Line 3 Sander - Nordic Furniture Group

Email 7: The Agreement
From: Arne Jensen a.jensen@nordic-furniture.com
Sent: Tuesday, January 23, 2024 09:15 AM
To: Lukas Weber lukas.weber@mann-hummel.com
Subject: RE: Replacement Filters - Line 3 Sander - Nordic Furniture Group

Hi Lukas,
Understood. I spoke with the plant manager, and we cannot risk a compliance issue with the insurance company.
Please proceed with the quote for the Airpocket Ex-Protect (Conductive) filters. We will organize the budget for the price difference.
Send the order confirmation ASAP.
Best,
Arne

---

Email 6: The Engineering Enforcement
From: Lukas Weber lukas.weber@mann-hummel.com
Sent: Monday, January 22, 2024 04:45 PM
To: Arne Jensen a.jensen@nordic-furniture.com
Subject: RE: Replacement Filters - Line 3 Sander - Nordic Furniture Group

Arne,
Grounding the metal housing is standard procedure, but it is not sufficient if the filter bags themselves are insulators.

The Physics:
Standard synthetic pocket filters act like a capacitor. As the dry wood dust rubs against the synthetic media, it builds up a static charge (Triboelectric effect). If that charge jumps to the metal frame (Spark), and you have a dust cloud (Sanding), you have an ignition source.

Regulatory Constraint:
For ATEX Zone 22, the filter media MUST be conductive (leakage resistance < 10^8 Ohm).

Therefore, I cannot sell you the standard Eco filters for this application. It would be a violation of the machinery directive.
You need the Airpocket Ex-Protect version with integrated carbon threads.

Lukas

---

Email 5: The Pushback (Cost vs. Risk)
From: Arne Jensen a.jensen@nordic-furniture.com
Sent: Monday, January 22, 2024 02:10 PM
To: Lukas Weber lukas.weber@mann-hummel.com
Subject: RE: Replacement Filters - Line 3 Sander - Nordic Furniture Group

Lukas,
I just checked with our HSE officer. The inside of the filter chamber is indeed classified as ATEX Zone 22 (Potential explosive atmosphere during normal operation).
However, the housing itself is grounded. Do we really need the expensive Conductive filters?
The standard Airpocket Eco you quoted initially is €45. The Antistatic version is €85. That's nearly double.
Can't we just use the standard ones since the box is grounded?

Arne

---

Email 4: The Safety Warning
From: Lukas Weber lukas.weber@mann-hummel.com
Sent: Monday, January 22, 2024 11:30 AM
To: Arne Jensen a.jensen@nordic-furniture.com
Subject: RE: Replacement Filters - Line 3 Sander - Nordic Furniture Group

Hi Arne,
Thanks for the detail. Oak and Pine dust are fine organic particulates with a high Kst value (Explosion index).

Before I confirm the order for standard filters, I need to raise a safety flag.
Standard synthetic bag filters generate Electrostatic Charges during operation. In a wood sanding environment, this creates a spark risk.

Critical Question:
Is your filter unit classified as an ATEX Zone (20, 21, or 22)?
If yes, standard filters are prohibited.

Regards,
Lukas

---

Email 3: Context Clarification
From: Arne Jensen a.jensen@nordic-furniture.com
Sent: Monday, January 22, 2024 10:15 AM
To: Lukas Weber lukas.weber@mann-hummel.com
Subject: RE: Replacement Filters - Line 3 Sander - Nordic Furniture Group

Hi Lukas,
This is for our Fine Sanding Line (Line 3).
We are processing solid Oak and Pine. The dust is very fine and dry.
The current filters are clogging up too fast, so we hope the M+H ones last longer.

Arne

---

Email 2: Discovery
From: Lukas Weber lukas.weber@mann-hummel.com
Sent: Monday, January 22, 2024 09:00 AM
To: Arne Jensen a.jensen@nordic-furniture.com
Subject: RE: Replacement Filters - Line 3 Sander - Nordic Furniture Group

Hello Arne,
Thank you for the request.
I can certainly quote the Airpocket Eco ePM1 60% (F7) as a direct dimensional replacement.

However, to ensure I give you the correct media type:
What specific application is this for?
Are you filtering ambient hall air, or is this direct extraction from a machine (Sawing/Sanding/Varnishing)?

Best regards,
Lukas Weber
Sales Engineer | Industrial Air

---

Email 1: The Inquiry
From: Arne Jensen a.jensen@nordic-furniture.com
Sent: Monday, January 22, 2024 08:30 AM
To: Lukas Weber lukas.weber@mann-hummel.com
Subject: Replacement Filters - Line 3 Sander - Nordic Furniture Group

Hi Lukas,
We need to replace the bag filters in our extraction unit.
Looking for 60 pcs.
Size: 592x592x635mm, 8 pockets.
Class: F7 (ePM1 60%).

We are looking for a standard, cost-effective solution to keep our maintenance budget in check. Please send a quote for your standard synthetic bags.

Best regards,
Arne Jensen
Nordic Furniture Group`
  }
};

const HIDDEN_NAV_IDS = new Set(["bulk-offer", "ingest", "explore", "knowledge", "testgen", "use-cases", "expert-review", "audit", "batch-results"]);

const NAV_ITEMS: NavItem[] = [
  { id: "chat", label: "AI Consultant", icon: MessageSquare, section: "main" },
  { id: "bulk-offer", label: "Bulk Offer", icon: Package, section: "main", devOnly: true },
  { id: "ingest", label: "Ingest Data", icon: Upload, section: "main" },
  { id: "explore", label: "Thread Explorer", icon: FolderSearch, section: "main" },
  { id: "knowledge", label: "Knowledge Refinery", icon: BookOpen, section: "main" },
  { id: "testlab", label: "Test Lab", icon: FlaskConical, section: "main", devOnly: true },
  { id: "testgen", label: "Test Generator", icon: Wand2, section: "main", devOnly: true },
  { id: "capabilities", label: "Capabilities", icon: Compass, section: "main", devOnly: true },
  { id: "use-cases", label: "Use Cases", icon: BookOpen, section: "main", devOnly: true },
  { id: "expert-review", label: "Expert Review", icon: ClipboardCheck, section: "main", devOnly: true },
  { id: "analytics", label: "Analytics", icon: BarChart3, disabled: true, section: "enterprise" },
  { id: "workflows", label: "Workflows", icon: Workflow, disabled: true, section: "enterprise" },
  { id: "users", label: "User Management", icon: Users, disabled: true, section: "admin" },
  { id: "integrations", label: "Integrations", icon: Plug, disabled: true, section: "admin" },
  { id: "audit", label: "Graph Audit", icon: Shield, section: "main", devOnly: true },
  { id: "batch-results", label: "Batch Results", icon: BarChart3, section: "main", devOnly: true },
  { id: "settings", label: "Settings", icon: Settings, section: "admin" },
];

function LockedModule({ title, description, icon: Icon }: { title: string; description: string; icon: React.ComponentType<{ className?: string }> }) {
  return (
    <div className="relative h-full">
      {/* Fake grayed-out UI background */}
      <div className="absolute inset-0 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden opacity-40 pointer-events-none">
        {/* Fake header */}
        <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-slate-200 dark:bg-slate-700" />
            <div>
              <div className="h-4 w-32 bg-slate-200 dark:bg-slate-700 rounded" />
              <div className="h-3 w-24 bg-slate-100 dark:bg-slate-800 rounded mt-1" />
            </div>
          </div>
          <div className="flex gap-2">
            <div className="h-9 w-24 bg-slate-100 dark:bg-slate-800 rounded-lg" />
            <div className="h-9 w-9 bg-slate-100 dark:bg-slate-800 rounded-lg" />
          </div>
        </div>

        {/* Fake content */}
        <div className="p-6 space-y-4">
          <div className="grid grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-100 dark:border-slate-700">
                <div className="h-8 w-16 bg-slate-200 dark:bg-slate-700 rounded mb-2" />
                <div className="h-3 w-20 bg-slate-100 dark:bg-slate-800 rounded" />
              </div>
            ))}
          </div>

          <div className="rounded-xl border border-slate-100 dark:border-slate-700 overflow-hidden">
            <div className="bg-slate-50 dark:bg-slate-800 px-4 py-3 border-b border-slate-100 dark:border-slate-700">
              <div className="flex gap-4">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="h-3 w-20 bg-slate-200 dark:bg-slate-700 rounded" />
                ))}
              </div>
            </div>
            {[1, 2, 3, 4, 5].map((row) => (
              <div key={row} className="px-4 py-3 border-b border-slate-50 dark:border-slate-800 flex gap-4">
                {[1, 2, 3, 4, 5].map((col) => (
                  <div key={col} className="h-3 w-20 bg-slate-100 dark:bg-slate-800 rounded" />
                ))}
              </div>
            ))}
          </div>

          <div className="rounded-xl border border-slate-100 dark:border-slate-700 p-4">
            <div className="h-3 w-32 bg-slate-200 dark:bg-slate-700 rounded mb-4" />
            <div className="flex items-end gap-2 h-32">
              {[40, 65, 45, 80, 55, 70, 60, 75, 50, 85, 65, 70].map((h, i) => (
                <div key={i} className="flex-1 bg-slate-100 dark:bg-slate-800 rounded-t" style={{ height: `${h}%` }} />
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Overlay with lock message */}
      <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-br from-white/80 via-white/90 to-white/80 dark:from-slate-950/80 dark:via-slate-950/90 dark:to-slate-950/80 backdrop-blur-[2px] rounded-2xl">
        <div className="text-center max-w-md mx-auto p-8">
          <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-slate-100 to-slate-200 dark:from-slate-700 dark:to-slate-800 flex items-center justify-center relative shadow-lg">
            <Icon className="w-10 h-10 text-slate-400" />
            <div className="absolute -bottom-2 -right-2 w-9 h-9 rounded-full bg-gradient-to-br from-slate-700 to-slate-900 flex items-center justify-center shadow-lg border-2 border-white dark:border-slate-800">
              <Lock className="w-4 h-4 text-white" />
            </div>
          </div>
          <h2 className="text-2xl font-bold text-slate-700 dark:text-slate-200 mb-2">{title}</h2>
          <p className="text-slate-500 dark:text-slate-400 mb-6 leading-relaxed">{description}</p>
          <div className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-700 shadow-sm">
            <div className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
            <span className="text-sm font-semibold text-amber-700 dark:text-amber-400">Module not rolled out</span>
          </div>
          <p className="mt-6 text-sm text-slate-400">
            Contact your account manager to enable this module
          </p>
          <button className="mt-4 px-6 py-2.5 rounded-xl bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 text-sm font-medium hover:bg-slate-800 dark:hover:bg-slate-200 transition-colors shadow-lg">
            Request Access
          </button>
        </div>
      </div>
    </div>
  );
}

function MainApp() {
  const [activeTab, setActiveTab] = useState<TabType>("chat");
  const [ingestSubTab, setIngestSubTab] = useState<IngestSubTab>("threads");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [devMode, setDevMode] = useState(false);
  const { theme, setTheme } = useTheme();
  // Read ?q= synchronously during init — MUST happen before Chat mounts
  // and loads history with the (potentially copied) parent session ID.
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q");
    if (q) {
      resetSessionId();
      window.history.replaceState({}, "", window.location.pathname);
      return q;
    }
    return null;
  });
  const [autoSubmit, setAutoSubmit] = useState(() => !!pendingQuestion);
  const [pendingSampleText, setPendingSampleText] = useState<string | null>(null);

  // Chat settings (lifted from Chat component)
  const [explainableMode] = useState(false);  // Use regular chat with widgets
  const expertMode = true;
  const chatMode: ChatMode = "graph-reasoning";
  const chatRef = useRef<{ clearChat: () => void; testWidgets: () => void } | null>(null);


  return (
    <div className="min-h-screen bg-gradient-to-br from-stone-50 via-green-50/20 to-stone-50 dark:from-slate-950 dark:via-green-950/20 dark:to-slate-950 flex">
      {/* Sidebar */}
      <aside
        className={cn(
          "h-screen sticky top-0 bg-white/70 dark:bg-slate-900/70 backdrop-blur-xl border-r border-slate-200/60 dark:border-slate-700/60 flex flex-col transition-all duration-300",
          sidebarCollapsed ? "w-[72px]" : "w-64"
        )}
      >
        {/* Logo */}
        <div className="h-16 flex items-center px-4 border-b border-slate-200/60 dark:border-slate-700/60">
          <div className="flex items-center gap-3 min-w-0">
            {sidebarCollapsed ? (
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-green-700 to-green-600 flex items-center justify-center shadow-lg shadow-green-700/25">
                <span className="text-white font-bold text-xs">M+H</span>
              </div>
            ) : (
              <div className="animate-fade-in">
                <Image src="/mh_logo.png" alt="MANN+HUMMEL" width={96} height={24} className="dark:brightness-0 dark:invert" priority />
              </div>
            )}
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {/* Main Section */}
          {!sidebarCollapsed && (
            <div className="px-3 py-2">
              <span className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                Main
              </span>
            </div>
          )}
          {NAV_ITEMS.filter(item => item.section === "main" && (!item.devOnly || devMode) && !HIDDEN_NAV_IDS.has(item.id)).map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all",
                activeTab === item.id
                  ? "bg-green-700 text-white shadow-lg shadow-green-700/25"
                  : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
              )}
            >
              <item.icon className="w-5 h-5 flex-shrink-0" />
              {!sidebarCollapsed && <span>{item.label}</span>}
            </button>
          ))}

          {/* Admin Section - Settings */}
          <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-700">
            {!sidebarCollapsed && (
              <div className="px-3 py-2">
                <span className="text-[10px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                  Admin
                </span>
              </div>
            )}
            <button
              onClick={() => setActiveTab("settings")}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all",
                activeTab === "settings"
                  ? "bg-gradient-to-r from-slate-700 to-slate-800 text-white shadow-lg shadow-slate-500/25"
                  : "text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
              )}
            >
              <Settings className="w-5 h-5 flex-shrink-0" />
              {!sidebarCollapsed && <span>Settings</span>}
            </button>
          </div>

        </nav>

        {/* Dev Mode Toggle */}
        <div className="border-t border-slate-200/60 dark:border-slate-700/60 p-3">
          {/* Theme Toggle */}
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-all"
          >
            <Sun className="w-4 h-4 flex-shrink-0 dark:hidden" />
            <Moon className="w-4 h-4 flex-shrink-0 hidden dark:block" />
            {!sidebarCollapsed && <span className="dark:hidden">Dark Mode</span>}
            {!sidebarCollapsed && <span className="hidden dark:block">Light Mode</span>}
          </button>

          <button
            onClick={() => setDevMode(!devMode)}
            className={cn(
              "w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-all mt-1",
              devMode
                ? "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400"
                : "text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
            )}
          >
            <div className="flex items-center gap-2">
              <Bug className="w-4 h-4 flex-shrink-0" />
              {!sidebarCollapsed && <span>Dev Mode</span>}
            </div>
            {!sidebarCollapsed && (
              <div className={cn(
                "w-8 h-4 rounded-full transition-colors relative",
                devMode ? "bg-amber-500" : "bg-slate-300 dark:bg-slate-600"
              )}>
                <div className={cn(
                  "absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform",
                  devMode ? "translate-x-4" : "translate-x-0.5"
                )} />
              </div>
            )}
          </button>

          {/* Logout Button */}
          <button
            onClick={() => {
              clearToken();
              window.location.href = "/login";
            }}
            className="w-full flex items-center gap-2 px-3 py-2 mt-1 rounded-lg text-xs font-medium text-slate-400 dark:text-slate-500 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-all"
          >
            <LogOut className="w-4 h-4 flex-shrink-0" />
            {!sidebarCollapsed && <span>Logout</span>}
          </button>
        </div>

        {/* Collapse Toggle */}
        <button
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          className="mx-3 mb-3 p-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
        >
          {sidebarCollapsed ? (
            <ChevronRight className="w-4 h-4 mx-auto" />
          ) : (
            <ChevronLeft className="w-4 h-4 mx-auto" />
          )}
        </button>
      </aside>

      {/* Main Content */}
      <main className="flex-1 min-h-screen flex flex-col">
        {/* Header */}
        <header className="h-16 border-b border-slate-200/60 dark:border-slate-700/60 bg-white dark:bg-slate-900/50 backdrop-blur-xl sticky top-0 z-10 flex items-center justify-between px-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              {activeTab === "chat" && "AI Sales Consultant"}
              {activeTab === "ingest" && "Data Ingestion"}
              {activeTab === "explore" && "Thread Explorer"}
              {activeTab === "knowledge" && "Knowledge Refinery"}
              {activeTab === "testlab" && "Test Lab"}
              {activeTab === "testgen" && "Test Generator"}
              {activeTab === "capabilities" && "Expert Capabilities"}
              {activeTab === "expert-review" && "Expert Review"}
              {activeTab === "analytics" && "Analytics & Reports"}
              {activeTab === "workflows" && "Automation Workflows"}
              {activeTab === "users" && "User Management"}
              {activeTab === "integrations" && "Integrations"}
              {activeTab === "audit" && "Graph Audit"}
              {activeTab === "batch-results" && "Batch Results"}
              {activeTab === "bulk-offer" && "Bulk Offer Creator"}
              {activeTab === "use-cases" && "Use Case Coverage"}
              {activeTab === "settings" && "Settings"}
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {activeTab === "chat" && ""}
              {activeTab === "ingest" && "Add email threads and documents to the knowledge base"}
              {activeTab === "explore" && "Browse and manage ingested email threads"}
              {activeTab === "knowledge" && "Review and refine AI-discovered knowledge"}
              {activeTab === "testlab" && "Review regression test results and assertion details"}
              {activeTab === "testgen" && "Multi-LLM debate to generate new test cases from product catalogs"}
              {activeTab === "capabilities" && "Expert modules, sub-components, and example scenarios"}
              {activeTab === "expert-review" && "Browse conversations, review responses, and score judge evaluations"}
              {activeTab === "analytics" && "Track performance metrics and generate reports"}
              {activeTab === "workflows" && "Automate repetitive tasks and processes"}
              {activeTab === "users" && "Manage team members and permissions"}
              {activeTab === "integrations" && "Connect with CRM, ERP and other systems"}
              {activeTab === "audit" && "Multi-LLM debate to verify knowledge graph integrity against product catalog"}
              {activeTab === "batch-results" && "3-LLM judge evaluation across all test questions with per-dimension scores"}
              {activeTab === "bulk-offer" && "Upload client orders, AI analyzes and generates bulk offers with graph reasoning"}
              {activeTab === "use-cases" && "Real email analysis: what Mikael handles today vs. what the tool covers"}
              {activeTab === "settings" && "Configure system preferences and policies"}
            </p>
          </div>

          {/* Chat Controls - Only show on chat tab */}
          {activeTab === "chat" && (
            <div className="flex items-center gap-2">
              {/* New Session */}
              <button
                onClick={() => chatRef.current?.clearChat()}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-400 dark:text-slate-500 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                title="Clear session and start fresh"
              >
                <Trash2 className="h-4 w-4" />
                <span>New Session</span>
              </button>
            </div>
          )}
        </header>

        {/* Content Area */}
        <div className="flex-1 p-6">
          <div className={cn(
            "h-full",
            activeTab === "chat" ? "w-full" : "max-w-5xl mx-auto"
          )}>
            {activeTab === "chat" && (
              <Chat
                ref={chatRef}
                devMode={devMode}
                sampleQuestions={SAMPLE_QUESTIONS}
                externalQuestion={pendingQuestion || undefined}
                autoSubmit={autoSubmit}
                onQuestionConsumed={() => { setPendingQuestion(null); setAutoSubmit(false); }}
                explainableMode={explainableMode}
                expertMode={expertMode}
                onExpertModeChange={() => {}}
                chatMode={chatMode}
              />
            )}
            {activeTab === "ingest" && (
              <div className="space-y-4">
                {/* Sub-tabs for Threads vs Docs */}
                <div className="flex gap-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl w-fit">
                  <button
                    onClick={() => setIngestSubTab("threads")}
                    className={cn(
                      "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
                      ingestSubTab === "threads"
                        ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm"
                        : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                    )}
                  >
                    <Upload className="w-4 h-4" />
                    Email Threads
                  </button>
                  <button
                    onClick={() => setIngestSubTab("docs")}
                    className={cn(
                      "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
                      ingestSubTab === "docs"
                        ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm"
                        : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                    )}
                  >
                    <FileText className="w-4 h-4" />
                    Documents
                  </button>
                </div>

                {/* Content based on sub-tab */}
                {ingestSubTab === "threads" && (
                  <ThreadIngestor
                    devMode={devMode}
                    sampleCases={SAMPLE_CASES}
                    pendingSampleText={pendingSampleText}
                    onSampleTextConsumed={() => setPendingSampleText(null)}
                  />
                )}
                {ingestSubTab === "docs" && <DocIngestor />}
              </div>
            )}
            {activeTab === "explore" && <ThreadExplorer />}
            {activeTab === "knowledge" && <KnowledgeRefinery />}
            {activeTab === "testlab" && <TestLab />}
            {activeTab === "testgen" && <TestGenerator />}
            {activeTab === "capabilities" && <CapabilitiesShowcase />}
            {activeTab === "expert-review" && <ExpertReview />}
            {activeTab === "analytics" && (
              <LockedModule
                title="Analytics & Reports"
                description="Comprehensive dashboards with real-time KPIs, custom report builder, and exportable insights across all your sales engineering activities."
                icon={BarChart3}
              />
            )}
            {activeTab === "workflows" && (
              <LockedModule
                title="Automation Workflows"
                description="Build custom automation rules, trigger actions based on knowledge graph events, and streamline repetitive engineering tasks."
                icon={Workflow}
              />
            )}
            {activeTab === "users" && (
              <LockedModule
                title="User Management"
                description="Enterprise SSO integration, role-based access control, team hierarchies, and detailed permission management for your organization."
                icon={Users}
              />
            )}
            {activeTab === "integrations" && (
              <LockedModule
                title="Integrations Hub"
                description="Connect with Salesforce, SAP, Microsoft Dynamics, Outlook, and 50+ enterprise systems. Bi-directional sync with your existing tools."
                icon={Plug}
              />
            )}
            {activeTab === "audit" && <GraphAudit />}
            {activeTab === "batch-results" && <BatchResults />}
            {activeTab === "bulk-offer" && <BulkOffer />}
            {activeTab === "use-cases" && <UseCaseCoverage />}
            {activeTab === "settings" && <SettingsPanel />}
          </div>
        </div>
      </main>
    </div>
  );
}

export default function Home() {
  return (
    <AuthGuard>
      <MainApp />
    </AuthGuard>
  );
}
