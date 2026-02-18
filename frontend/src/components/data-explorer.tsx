"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  RefreshCw,
  Loader2,
  Search,
  Folder,
  Package,
  Users,
  Lightbulb,
  Eye,
  Zap,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiUrl, authFetch } from "@/lib/api";

// Tab configuration with colors matching the graph visualization
const TABS = [
  { id: "projects", label: "Projects", icon: Folder, color: "#5B8C3E" },
  { id: "products", label: "Products", icon: Package, color: "#22c55e" },
  { id: "competitors", label: "Competitors", icon: Users, color: "#ef4444" },
  { id: "concepts", label: "Concepts", icon: Lightbulb, color: "#a855f7" },
  { id: "observations", label: "Observations", icon: Eye, color: "#f59e0b" },
  { id: "actions", label: "Actions", icon: Zap, color: "#059669" },
] as const;

type TabId = (typeof TABS)[number]["id"];

// Type definitions for data
interface Project {
  name: string;
  customer: string | null;
  date: string | null;
  summary: string | null;
  observations_count: number;
  concepts: string[];
}

interface Product {
  sku: string | null;
  name: string;
  price: number | null;
  dimensions: string | null;
  type: string | null;
  competitor_equivalents: string[];
}

interface Competitor {
  name: string;
  manufacturer: string | null;
  equivalents: Array<{ sku: string | null; name: string | null; price: number | null }>;
}

interface Concept {
  name: string;
  description: string | null;
  observations_count: number;
  actions_count: number;
}

interface Observation {
  description: string;
  context: string | null;
  project: string | null;
  concepts: string[];
  actions: string[];
}

interface Action {
  description: string;
  outcome: string | null;
  observations_count: number;
  projects: string[];
}

type DataItem = Project | Product | Competitor | Concept | Observation | Action;

interface ExplorerData {
  projects: Project[];
  products: Product[];
  competitors: Competitor[];
  concepts: Concept[];
  observations: Observation[];
  actions: Action[];
}

export function DataExplorer() {
  const [activeTab, setActiveTab] = useState<TabId>("projects");
  const [selectedItem, setSelectedItem] = useState<DataItem | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ExplorerData>({
    projects: [],
    products: [],
    competitors: [],
    concepts: [],
    observations: [],
    actions: [],
  });

  const fetchData = useCallback(async (tab: TabId) => {
    setLoading(true);
    setError(null);
    try {
      const endpoint = tab === "products" ? "/products" : `/explorer/${tab}`;
      const response = await fetch(apiUrl(`${endpoint}`), authFetch());
      if (!response.ok) throw new Error(`Failed to fetch ${tab}`);
      const result = await response.json();

      setData((prev) => ({
        ...prev,
        [tab]: result[tab] || result.products || [],
      }));
    } catch (err) {
      setError(`Failed to load ${tab}`);
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(activeTab);
  }, [activeTab, fetchData]);

  const handleTabChange = (tab: TabId) => {
    setActiveTab(tab);
    setSelectedItem(null);
    setSearchQuery("");
  };

  const handleRefresh = () => {
    fetchData(activeTab);
  };

  const getItemName = (item: DataItem): string => {
    if ("name" in item && item.name) return item.name;
    if ("description" in item && item.description) return item.description;
    return "Unknown";
  };

  const getItemSubtitle = (item: DataItem): string => {
    if ("customer" in item && item.customer) return item.customer;
    if ("manufacturer" in item && item.manufacturer) return item.manufacturer;
    if ("project" in item && item.project) return item.project;
    if ("sku" in item && item.sku) return item.sku;
    return "";
  };

  const filteredItems = (data[activeTab] || []).filter((item: DataItem) => {
    const name = getItemName(item).toLowerCase();
    const subtitle = getItemSubtitle(item).toLowerCase();
    const query = searchQuery.toLowerCase();
    return name.includes(query) || subtitle.includes(query);
  });

  const navigateToItem = (tab: TabId, name: string) => {
    setActiveTab(tab);
    setSearchQuery("");
    // Find and select the item after data loads
    setTimeout(() => {
      const items = data[tab] || [];
      const item = items.find((i: DataItem) => getItemName(i) === name);
      if (item) setSelectedItem(item);
    }, 100);
  };

  const currentTab = TABS.find((t) => t.id === activeTab)!;

  return (
    <Card className="w-full h-[600px] flex flex-col">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <CardTitle className="text-xl">Data Explorer</CardTitle>
        <Button variant="outline" size="sm" onClick={handleRefresh} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        </Button>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col overflow-hidden p-0">
        {/* Tabs */}
        <div className="flex border-b px-4 overflow-x-auto">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id)}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap",
                  isActive
                    ? "border-current text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                )}
                style={{ color: isActive ? tab.color : undefined }}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Search */}
        <div className="p-4 border-b">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder={`Search ${activeTab}...`}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          {error ? (
            <div className="flex-1 flex items-center justify-center text-destructive">
              {error}
            </div>
          ) : loading ? (
            <div className="flex-1 flex items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-muted-foreground">
              No {activeTab} found
            </div>
          ) : (
            <>
              {/* Item List */}
              <ScrollArea className="w-1/2 border-r">
                <div className="p-2">
                  {filteredItems.map((item: DataItem, index: number) => {
                    const name = getItemName(item);
                    const subtitle = getItemSubtitle(item);
                    const isSelected = selectedItem && getItemName(selectedItem) === name;
                    return (
                      <button
                        key={`${index}-${name}`}
                        onClick={() => setSelectedItem(item)}
                        className={cn(
                          "w-full text-left p-3 rounded-md mb-1 transition-colors flex items-center justify-between group",
                          isSelected
                            ? "bg-accent"
                            : "hover:bg-accent/50"
                        )}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <div
                            className="w-2 h-2 rounded-full flex-shrink-0"
                            style={{ backgroundColor: currentTab.color }}
                          />
                          <div className="min-w-0">
                            <div className="font-medium truncate">{name}</div>
                            {subtitle && (
                              <div className="text-xs text-muted-foreground truncate">
                                {subtitle}
                              </div>
                            )}
                          </div>
                        </div>
                        <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 flex-shrink-0" />
                      </button>
                    );
                  })}
                </div>
              </ScrollArea>

              {/* Detail Panel */}
              <ScrollArea className="w-1/2">
                {selectedItem ? (
                  <DetailPanel
                    item={selectedItem}
                    tab={activeTab}
                    tabColor={currentTab.color}
                    onNavigate={navigateToItem}
                  />
                ) : (
                  <div className="h-full flex items-center justify-center text-muted-foreground p-4">
                    Select an item to view details
                  </div>
                )}
              </ScrollArea>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

interface DetailPanelProps {
  item: DataItem;
  tab: TabId;
  tabColor: string;
  onNavigate: (tab: TabId, name: string) => void;
}

function DetailPanel({ item, tab, tabColor, onNavigate }: DetailPanelProps) {
  const renderBadge = (text: string, color: string, onClick?: () => void) => (
    <span
      onClick={onClick}
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium mr-1 mb-1",
        onClick && "cursor-pointer hover:opacity-80"
      )}
      style={{ backgroundColor: `${color}20`, color }}
    >
      {text}
    </span>
  );

  const renderSection = (title: string, content: React.ReactNode) => (
    <div className="mb-4">
      <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
        {title}
      </h4>
      {content}
    </div>
  );

  const content = () => {
    switch (tab) {
      case "projects": {
        const project = item as Project;
        return (
          <>
            <h3 className="text-lg font-bold mb-1" style={{ color: tabColor }}>
              {project.name}
            </h3>
            {project.customer && (
              <p className="text-sm text-muted-foreground mb-4">
                Customer: {project.customer}
              </p>
            )}
            {project.summary && renderSection("Summary", <p className="text-sm">{project.summary}</p>)}
            {project.date && renderSection("Date", <p className="text-sm">{project.date}</p>)}
            {renderSection(
              `Observations (${project.observations_count})`,
              <p className="text-sm text-muted-foreground">
                {project.observations_count} observation(s) recorded
              </p>
            )}
            {project.concepts.length > 0 &&
              renderSection(
                "Related Concepts",
                <div className="flex flex-wrap">
                  {project.concepts.filter(Boolean).map((c) =>
                    renderBadge(c, "#a855f7", () => onNavigate("concepts", c))
                  )}
                </div>
              )}
          </>
        );
      }

      case "products": {
        const product = item as Product;
        return (
          <>
            <h3 className="text-lg font-bold mb-1" style={{ color: tabColor }}>
              {product.name}
            </h3>
            {product.sku && (
              <p className="text-sm text-muted-foreground mb-4">SKU: {product.sku}</p>
            )}
            {product.price && renderSection("Price", <p className="text-sm">${product.price}</p>)}
            {product.type && renderSection("Type", <p className="text-sm">{product.type}</p>)}
            {product.dimensions &&
              renderSection("Dimensions", <p className="text-sm">{product.dimensions}</p>)}
            {product.competitor_equivalents?.length > 0 &&
              renderSection(
                "Competitor Equivalents",
                <div className="flex flex-wrap">
                  {product.competitor_equivalents.filter(Boolean).map((c) =>
                    renderBadge(c, "#ef4444", () => onNavigate("competitors", c))
                  )}
                </div>
              )}
          </>
        );
      }

      case "competitors": {
        const competitor = item as Competitor;
        return (
          <>
            <h3 className="text-lg font-bold mb-1" style={{ color: tabColor }}>
              {competitor.name}
            </h3>
            {competitor.manufacturer && (
              <p className="text-sm text-muted-foreground mb-4">
                Manufacturer: {competitor.manufacturer}
              </p>
            )}
            {competitor.equivalents?.length > 0 &&
              renderSection(
                "Our Equivalent Products",
                <div className="space-y-2">
                  {competitor.equivalents
                    .filter((e) => e.name)
                    .map((e, i) => (
                      <div
                        key={i}
                        className="p-2 rounded bg-accent/50 text-sm cursor-pointer hover:bg-accent"
                        onClick={() => e.name && onNavigate("products", e.name)}
                      >
                        <div className="font-medium">{e.name}</div>
                        {e.sku && (
                          <div className="text-xs text-muted-foreground">SKU: {e.sku}</div>
                        )}
                        {e.price && (
                          <div className="text-xs text-muted-foreground">Price: ${e.price}</div>
                        )}
                      </div>
                    ))}
                </div>
              )}
          </>
        );
      }

      case "concepts": {
        const concept = item as Concept;
        return (
          <>
            <h3 className="text-lg font-bold mb-1" style={{ color: tabColor }}>
              {concept.name}
            </h3>
            {concept.description &&
              renderSection("Description", <p className="text-sm">{concept.description}</p>)}
            {renderSection(
              "Statistics",
              <div className="grid grid-cols-2 gap-4">
                <div className="p-2 rounded bg-accent/50">
                  <div className="text-2xl font-bold">{concept.observations_count}</div>
                  <div className="text-xs text-muted-foreground">Observations</div>
                </div>
                <div className="p-2 rounded bg-accent/50">
                  <div className="text-2xl font-bold">{concept.actions_count}</div>
                  <div className="text-xs text-muted-foreground">Actions</div>
                </div>
              </div>
            )}
          </>
        );
      }

      case "observations": {
        const observation = item as Observation;
        return (
          <>
            <h3 className="text-lg font-bold mb-1" style={{ color: tabColor }}>
              Observation
            </h3>
            {observation.project && (
              <p
                className="text-sm text-muted-foreground mb-4 cursor-pointer hover:underline"
                onClick={() => onNavigate("projects", observation.project!)}
              >
                Project: {observation.project}
              </p>
            )}
            {renderSection("Description", <p className="text-sm">{observation.description}</p>)}
            {observation.context &&
              renderSection("Context", <p className="text-sm">{observation.context}</p>)}
            {observation.concepts?.length > 0 &&
              renderSection(
                "Related Concepts",
                <div className="flex flex-wrap">
                  {observation.concepts.filter(Boolean).map((c) =>
                    renderBadge(c, "#a855f7", () => onNavigate("concepts", c))
                  )}
                </div>
              )}
            {observation.actions?.length > 0 &&
              renderSection(
                "Actions Taken",
                <div className="space-y-1">
                  {observation.actions.filter(Boolean).map((a, i) => (
                    <div key={i} className="text-sm p-2 rounded bg-accent/50">
                      {a}
                    </div>
                  ))}
                </div>
              )}
          </>
        );
      }

      case "actions": {
        const action = item as Action;
        return (
          <>
            <h3 className="text-lg font-bold mb-1" style={{ color: tabColor }}>
              Action
            </h3>
            {renderSection("Description", <p className="text-sm">{action.description}</p>)}
            {action.outcome &&
              renderSection(
                "Outcome",
                <p className="text-sm p-2 rounded bg-green-500/10 text-green-600">
                  {action.outcome}
                </p>
              )}
            {renderSection(
              "Statistics",
              <div className="p-2 rounded bg-accent/50">
                <div className="text-2xl font-bold">{action.observations_count}</div>
                <div className="text-xs text-muted-foreground">Related Observations</div>
              </div>
            )}
            {action.projects?.length > 0 &&
              renderSection(
                "Projects",
                <div className="flex flex-wrap">
                  {action.projects.filter(Boolean).map((p) =>
                    renderBadge(p, "#5B8C3E", () => onNavigate("projects", p))
                  )}
                </div>
              )}
          </>
        );
      }

      default:
        return null;
    }
  };

  return <div className="p-4">{content()}</div>;
}
