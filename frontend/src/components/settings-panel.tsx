"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Building2,
  Shield,
  FlaskConical,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Database,
  Beaker,
  Factory,
  Loader2,
  FileText,
  Code,
  Copy,
  Check,
} from "lucide-react";

interface DomainInfo {
  id: string;
  name: string;
  company: string;
  description: string;
  version: string;
  config_file?: string;
}

interface Material {
  code: string;
  name: string;
  class: string;
}

interface Environment {
  name: string;
  required_materials: string[];
  concern: string;
}

interface ProductCapability {
  family: string;
  name: string;
  filters: string[];
  warnings_count: number;
}

interface ClarificationParam {
  name: string;
  units: string[];
  prompt: string;
}

interface Prompts {
  system: string;
  synthesis: string;
  no_context: string;
}

interface DomainConfig {
  domain: DomainInfo;
  guardian_rules: {
    material_count: number;
    environment_count: number;
    product_rules_count: number;
    accessory_rules_count: number;
  };
  materials: Material[];
  demanding_environments: Environment[];
  product_capabilities: ProductCapability[];
  sample_questions: Record<string, { label: string; icon: string; questions: string[] }>;
  clarification_params: ClarificationParam[];
  prompts: Prompts;
  prompt_templates: Record<string, string>;
}

interface DomainsResponse {
  current_domain: string;
  available_domains: DomainInfo[];
}

// Copy button component
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className="p-1.5 rounded-md hover:bg-slate-200 transition-colors"
      title="Copy to clipboard"
    >
      {copied ? (
        <Check className="w-3.5 h-3.5 text-green-500" />
      ) : (
        <Copy className="w-3.5 h-3.5 text-slate-400" />
      )}
    </button>
  );
}

// Prompt viewer component with expandable content
function PromptViewer({ title, content, description }: { title: string; content: string; description: string }) {
  const [expanded, setExpanded] = useState(false);
  const lines = content?.split("\n") || [];
  const preview = lines.slice(0, 5).join("\n");
  const hasMore = lines.length > 5;

  return (
    <div className="rounded-lg border border-indigo-100 bg-indigo-50/30 overflow-hidden">
      <div className="p-3 bg-indigo-50 border-b border-indigo-100 flex items-center justify-between">
        <div>
          <h4 className="font-medium text-slate-800">{title}</h4>
          <p className="text-xs text-slate-500">{description}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-xs">
            {lines.length} lines
          </Badge>
          <CopyButton text={content || ""} />
        </div>
      </div>
      <div className="p-3">
        <pre className={`text-xs text-slate-700 whitespace-pre-wrap font-mono bg-white p-3 rounded border border-slate-100 ${expanded ? "max-h-96" : "max-h-32"} overflow-y-auto`}>
          {expanded ? content : preview}
          {!expanded && hasMore && "\n..."}
        </pre>
        {hasMore && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-2 text-xs text-indigo-600 hover:text-indigo-700 font-medium"
          >
            {expanded ? "Show less" : `Show all ${lines.length} lines`}
          </button>
        )}
      </div>
    </div>
  );
}

export function SettingsPanel() {
  const [domains, setDomains] = useState<DomainsResponse | null>(null);
  const [config, setConfig] = useState<DomainConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(["domain", "guardian"]));

  const fetchDomains = async () => {
    try {
      const res = await fetch("http://localhost:8000/config/domains");
      const data = await res.json();
      setDomains(data);
    } catch (error) {
      console.error("Failed to fetch domains:", error);
    }
  };

  const fetchConfig = async () => {
    try {
      const res = await fetch("http://localhost:8000/config/domain");
      const data = await res.json();
      setConfig(data);
    } catch (error) {
      console.error("Failed to fetch config:", error);
    }
  };

  const switchDomain = async (domainId: string) => {
    setSwitching(true);
    try {
      const res = await fetch(`http://localhost:8000/config/domain/${domainId}`, {
        method: "POST",
      });
      if (res.ok) {
        await fetchDomains();
        await fetchConfig();
      }
    } catch (error) {
      console.error("Failed to switch domain:", error);
    } finally {
      setSwitching(false);
    }
  };

  const reloadConfig = async () => {
    setLoading(true);
    try {
      const currentDomain = domains?.current_domain;
      if (currentDomain) {
        await fetch(`http://localhost:8000/config/domain/${currentDomain}/reload`, {
          method: "POST",
        });
      }
      await fetchConfig();
    } catch (error) {
      console.error("Failed to reload config:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await fetchDomains();
      await fetchConfig();
      setLoading(false);
    };
    load();
  }, []);

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
      </div>
    );
  }

  const getDomainIcon = (domainId: string) => {
    if (domainId === "wacker" || domainId.includes("chem")) {
      return <Beaker className="w-5 h-5" />;
    }
    return <Factory className="w-5 h-5" />;
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-200 bg-white">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-slate-800">Domain Configuration</h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Manage domain-specific settings and Guardian rules
            </p>
          </div>
          <button
            onClick={reloadConfig}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 text-sm font-medium transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Reload Config
          </button>
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-6 space-y-6">
          {/* Domain Selector */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <Building2 className="w-4 h-4 text-blue-500" />
                Active Domain
              </CardTitle>
              <CardDescription>Switch between configured client domains</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-3">
                {domains?.available_domains.map((domain) => {
                  const isActive = domain.id === domains.current_domain;
                  return (
                    <button
                      key={domain.id}
                      onClick={() => !isActive && switchDomain(domain.id)}
                      disabled={switching}
                      className={`p-4 rounded-xl border-2 text-left transition-all ${
                        isActive
                          ? "border-blue-500 bg-blue-50"
                          : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className={`p-2 rounded-lg ${isActive ? "bg-blue-100" : "bg-slate-100"}`}>
                          {getDomainIcon(domain.id)}
                        </div>
                        {isActive && (
                          <Badge className="bg-blue-500 text-white">Active</Badge>
                        )}
                      </div>
                      <div className="mt-3">
                        <h3 className="font-semibold text-slate-800">{domain.company}</h3>
                        <p className="text-sm text-slate-500 mt-0.5">{domain.name}</p>
                        <p className="text-xs text-slate-400 mt-1">v{domain.version}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Domain Info */}
          {config && (
            <>
              {/* Collapsible: Domain Details */}
              <Card>
                <button
                  onClick={() => toggleSection("domain")}
                  className="w-full"
                >
                  <CardHeader className="pb-3 flex flex-row items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Database className="w-4 h-4 text-green-500" />
                      <CardTitle className="text-base">Domain Details</CardTitle>
                    </div>
                    {expandedSections.has("domain") ? (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-slate-400" />
                    )}
                  </CardHeader>
                </button>
                {expandedSections.has("domain") && (
                  <CardContent className="pt-0">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-3 rounded-lg bg-slate-50">
                        <p className="text-xs text-slate-500 uppercase tracking-wide">Company</p>
                        <p className="text-sm font-medium text-slate-800 mt-1">{config.domain.company}</p>
                      </div>
                      <div className="p-3 rounded-lg bg-slate-50">
                        <p className="text-xs text-slate-500 uppercase tracking-wide">Domain ID</p>
                        <p className="text-sm font-mono text-slate-800 mt-1">{config.domain.id}</p>
                      </div>
                      <div className="col-span-2 p-3 rounded-lg bg-slate-50">
                        <p className="text-xs text-slate-500 uppercase tracking-wide">Description</p>
                        <p className="text-sm text-slate-800 mt-1">{config.domain.description}</p>
                      </div>
                    </div>
                  </CardContent>
                )}
              </Card>

              {/* Collapsible: Guardian Rules Summary */}
              <Card>
                <button
                  onClick={() => toggleSection("guardian")}
                  className="w-full"
                >
                  <CardHeader className="pb-3 flex flex-row items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Shield className="w-4 h-4 text-amber-500" />
                      <CardTitle className="text-base">Guardian Rules</CardTitle>
                    </div>
                    {expandedSections.has("guardian") ? (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-slate-400" />
                    )}
                  </CardHeader>
                </button>
                {expandedSections.has("guardian") && (
                  <CardContent className="pt-0">
                    <div className="grid grid-cols-4 gap-3 mb-4">
                      <div className="p-3 rounded-lg bg-blue-50 border border-blue-100">
                        <p className="text-2xl font-bold text-blue-600">{config.guardian_rules.material_count}</p>
                        <p className="text-xs text-blue-600">Materials</p>
                      </div>
                      <div className="p-3 rounded-lg bg-amber-50 border border-amber-100">
                        <p className="text-2xl font-bold text-amber-600">{config.guardian_rules.environment_count}</p>
                        <p className="text-xs text-amber-600">Environments</p>
                      </div>
                      <div className="p-3 rounded-lg bg-green-50 border border-green-100">
                        <p className="text-2xl font-bold text-green-600">{config.guardian_rules.product_rules_count}</p>
                        <p className="text-xs text-green-600">Products</p>
                      </div>
                      <div className="p-3 rounded-lg bg-purple-50 border border-purple-100">
                        <p className="text-2xl font-bold text-purple-600">{config.guardian_rules.accessory_rules_count}</p>
                        <p className="text-xs text-purple-600">Accessories</p>
                      </div>
                    </div>
                  </CardContent>
                )}
              </Card>

              {/* Collapsible: Materials */}
              <Card>
                <button
                  onClick={() => toggleSection("materials")}
                  className="w-full"
                >
                  <CardHeader className="pb-3 flex flex-row items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FlaskConical className="w-4 h-4 text-blue-500" />
                      <CardTitle className="text-base">Material Classes</CardTitle>
                      <Badge variant="outline" className="ml-2">{config.materials.length}</Badge>
                    </div>
                    {expandedSections.has("materials") ? (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-slate-400" />
                    )}
                  </CardHeader>
                </button>
                {expandedSections.has("materials") && (
                  <CardContent className="pt-0">
                    <div className="space-y-2">
                      {config.materials.map((mat) => (
                        <div key={mat.code} className="flex items-center justify-between p-3 rounded-lg bg-slate-50">
                          <div className="flex items-center gap-3">
                            <Badge className="bg-blue-100 text-blue-700 font-mono">{mat.code}</Badge>
                            <span className="text-sm text-slate-700">{mat.name}</span>
                          </div>
                          <Badge variant="outline">{mat.class}</Badge>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                )}
              </Card>

              {/* Collapsible: Demanding Environments */}
              <Card>
                <button
                  onClick={() => toggleSection("environments")}
                  className="w-full"
                >
                  <CardHeader className="pb-3 flex flex-row items-center justify-between">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-500" />
                      <CardTitle className="text-base">Demanding Environments</CardTitle>
                      <Badge variant="outline" className="ml-2">{config.demanding_environments.length}</Badge>
                    </div>
                    {expandedSections.has("environments") ? (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-slate-400" />
                    )}
                  </CardHeader>
                </button>
                {expandedSections.has("environments") && (
                  <CardContent className="pt-0">
                    <div className="space-y-3">
                      {config.demanding_environments.map((env) => (
                        <div key={env.name} className="p-3 rounded-lg border border-amber-100 bg-amber-50/50">
                          <div className="flex items-center justify-between mb-2">
                            <span className="font-medium text-slate-800 capitalize">{env.name.replace(/_/g, " ")}</span>
                            <div className="flex gap-1">
                              {env.required_materials.map((mat) => (
                                <Badge key={mat} className="bg-amber-100 text-amber-700">{mat}</Badge>
                              ))}
                            </div>
                          </div>
                          <p className="text-sm text-slate-600">{env.concern}</p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                )}
              </Card>

              {/* Collapsible: Product Capabilities */}
              <Card>
                <button
                  onClick={() => toggleSection("products")}
                  className="w-full"
                >
                  <CardHeader className="pb-3 flex flex-row items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-green-500" />
                      <CardTitle className="text-base">Product Capabilities</CardTitle>
                      <Badge variant="outline" className="ml-2">{config.product_capabilities.length}</Badge>
                    </div>
                    {expandedSections.has("products") ? (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-slate-400" />
                    )}
                  </CardHeader>
                </button>
                {expandedSections.has("products") && (
                  <CardContent className="pt-0">
                    <div className="space-y-3">
                      {config.product_capabilities.map((prod) => (
                        <div key={prod.family} className="p-3 rounded-lg bg-slate-50">
                          <div className="flex items-center justify-between mb-2">
                            <div>
                              <span className="font-medium text-slate-800">{prod.family}</span>
                              <span className="text-slate-400 ml-2">-</span>
                              <span className="text-sm text-slate-600 ml-2">{prod.name}</span>
                            </div>
                            {prod.warnings_count > 0 && (
                              <Badge className="bg-amber-100 text-amber-700">
                                {prod.warnings_count} warnings
                              </Badge>
                            )}
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {prod.filters.map((filter) => (
                              <Badge key={filter} variant="outline" className="text-xs">
                                {filter}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                )}
              </Card>

              {/* Collapsible: Sample Questions */}
              <Card>
                <button
                  onClick={() => toggleSection("questions")}
                  className="w-full"
                >
                  <CardHeader className="pb-3 flex flex-row items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Database className="w-4 h-4 text-purple-500" />
                      <CardTitle className="text-base">Sample Questions</CardTitle>
                      <Badge variant="outline" className="ml-2">
                        {Object.keys(config.sample_questions).length} categories
                      </Badge>
                    </div>
                    {expandedSections.has("questions") ? (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-slate-400" />
                    )}
                  </CardHeader>
                </button>
                {expandedSections.has("questions") && (
                  <CardContent className="pt-0">
                    <div className="space-y-4">
                      {Object.entries(config.sample_questions).map(([key, category]) => (
                        <div key={key}>
                          <div className="flex items-center gap-2 mb-2">
                            <span className="text-lg">{category.icon}</span>
                            <span className="font-medium text-slate-700">{category.label}</span>
                          </div>
                          <div className="space-y-1 pl-7">
                            {category.questions.slice(0, 3).map((q, i) => (
                              <p key={i} className="text-sm text-slate-600 truncate">{q}</p>
                            ))}
                            {category.questions.length > 3 && (
                              <p className="text-xs text-slate-400">+{category.questions.length - 3} more</p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                )}
              </Card>

              {/* Collapsible: System Prompts */}
              <Card>
                <button
                  onClick={() => toggleSection("prompts")}
                  className="w-full"
                >
                  <CardHeader className="pb-3 flex flex-row items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-indigo-500" />
                      <CardTitle className="text-base">System Prompts</CardTitle>
                      <Badge variant="outline" className="ml-2">3 prompts</Badge>
                    </div>
                    {expandedSections.has("prompts") ? (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-slate-400" />
                    )}
                  </CardHeader>
                </button>
                {expandedSections.has("prompts") && config.prompts && (
                  <CardContent className="pt-0 space-y-4">
                    <PromptViewer
                      title="System Prompt"
                      content={config.prompts.system}
                      description="Main system instructions for the AI"
                    />
                    <PromptViewer
                      title="Synthesis Prompt"
                      content={config.prompts.synthesis}
                      description="Template for combining retrieved context with queries"
                    />
                    <PromptViewer
                      title="No Context Prompt"
                      content={config.prompts.no_context}
                      description="Response when no relevant data is found"
                    />
                  </CardContent>
                )}
              </Card>

              {/* Collapsible: Prompt Templates */}
              {config.prompt_templates && Object.keys(config.prompt_templates).length > 0 && (
                <Card>
                  <button
                    onClick={() => toggleSection("templates")}
                    className="w-full"
                  >
                    <CardHeader className="pb-3 flex flex-row items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Code className="w-4 h-4 text-cyan-500" />
                        <CardTitle className="text-base">Warning Templates</CardTitle>
                        <Badge variant="outline" className="ml-2">
                          {Object.keys(config.prompt_templates).length} templates
                        </Badge>
                      </div>
                      {expandedSections.has("templates") ? (
                        <ChevronDown className="w-4 h-4 text-slate-400" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-slate-400" />
                      )}
                    </CardHeader>
                  </button>
                  {expandedSections.has("templates") && (
                    <CardContent className="pt-0 space-y-3">
                      {Object.entries(config.prompt_templates).map(([key, template]) => (
                        <div key={key} className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium text-slate-700 font-mono">
                              {key.replace(/_/g, " ")}
                            </span>
                            <CopyButton text={template} />
                          </div>
                          <pre className="text-xs text-slate-600 whitespace-pre-wrap font-mono bg-white p-2 rounded border border-slate-100 max-h-24 overflow-y-auto">
                            {template}
                          </pre>
                        </div>
                      ))}
                    </CardContent>
                  )}
                </Card>
              )}
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
