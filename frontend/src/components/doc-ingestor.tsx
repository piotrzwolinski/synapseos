"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Loader2,
  CheckCircle2,
  AlertCircle,
  FileText,
  Upload,
  ArrowRight,
  ArrowLeft,
  RefreshCw,
  Eye,
  Database,
  Link2,
  Box,
  ChevronDown,
  ChevronRight,
  Sparkles,
  FileJson,
  ImageIcon,
  File,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiUrl, authFetch } from "@/lib/api";

type WizardStep = "upload" | "schema" | "processing" | "result";

interface VariantProperty {
  name: string;
  type: string;
  description: string;
}

interface CategoryDimension {
  label: string;
  description: string;
  example_values: string[];
}

interface Schema {
  document_type: string;
  summary: string;
  version: string;
  product_family: string;
  variant_properties: VariantProperty[];
  category_dimensions: CategoryDimension[];
  compatibility_rules: string[];
  concepts: string[];
  error?: string;
}

interface ProductVariant {
  id: string;
  family: string;
  variant_props: Record<string, number | string>;
  categories: Array<{
    label: string;
    value: string;
  }>;
}

interface ExtractionResult {
  message: string;
  counts: {
    document_sources: number;
    product_variants: number;
    categories: number;
    accessories: number;
    concepts: number;
    relationships: number;
  };
  extracted: {
    products: ProductVariant[];
    accessories: Array<{
      id: string;
      name: string;
      compatible_with: string[];
      price?: number;
    }>;
    compatibility_rules: Array<{
      rule: string;
      applies_to: string[];
      constraint_type: string;
      constraint_property: string;
      constraint_value: number;
    }>;
    concepts: string[];
  };
  schema: Schema;
  error?: string;
}

export function DocIngestor() {
  const [step, setStep] = useState<WizardStep>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [documentHint, setDocumentHint] = useState("");
  const [schema, setSchema] = useState<Schema | null>(null);
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [isDragActive, setIsDragActive] = useState(false);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragActive(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragActive(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragActive(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      setFile(droppedFile);
    }
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
    }
  };

  const analyzeSchema = async () => {
    if (!file) return;

    setIsAnalyzing(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      if (documentHint.trim()) {
        formData.append("document_hint", documentHint.trim());
      }

      const response = await fetch(apiUrl("/ingest/doc/analyze"), authFetch({
        method: "POST",
        body: formData,
      }));

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to analyze document");
      }

      const data = await response.json();
      setSchema(data.schema);
      setStep("schema");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const executeExtraction = async () => {
    if (!file || !schema) return;

    setStep("processing");
    setIsExtracting(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("schema", JSON.stringify(schema));
      formData.append("source_name", file.name);

      const response = await fetch(apiUrl("/ingest/doc/execute"), authFetch({
        method: "POST",
        body: formData,
      }));

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to extract data");
      }

      const data = await response.json();
      setResult(data);
      setStep("result");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed");
      setStep("schema");
    } finally {
      setIsExtracting(false);
    }
  };

  const reset = () => {
    setStep("upload");
    setFile(null);
    setDocumentHint("");
    setSchema(null);
    setResult(null);
    setError(null);
    setExpandedNodes(new Set());
  };

  const toggleNodeExpansion = (label: string) => {
    const newExpanded = new Set(expandedNodes);
    if (newExpanded.has(label)) {
      newExpanded.delete(label);
    } else {
      newExpanded.add(label);
    }
    setExpandedNodes(newExpanded);
  };

  const getFileIcon = () => {
    if (!file) return <Upload className="w-8 h-8 text-slate-400" />;
    if (file.type.startsWith("image/")) return <ImageIcon className="w-8 h-8 text-blue-500" />;
    if (file.type === "application/pdf") return <FileText className="w-8 h-8 text-red-500" />;
    return <File className="w-8 h-8 text-slate-500" />;
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl shadow-slate-200/50 dark:shadow-slate-900/50 border border-slate-200/60 dark:border-slate-700/60 overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-700 flex items-center justify-between bg-gradient-to-r from-slate-50 to-white dark:from-slate-800 dark:to-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/20">
            <FileText className="w-5 h-5 text-white" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-900 dark:text-slate-100">Document Ingestion</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              AI-driven schema discovery & extraction
            </p>
          </div>
        </div>

        {/* Step Indicator */}
        <div className="flex items-center gap-2">
          {["upload", "schema", "processing", "result"].map((s, i) => (
            <div key={s} className="flex items-center">
              <div
                className={cn(
                  "w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium transition-all",
                  step === s
                    ? "bg-emerald-500 text-white shadow-lg shadow-emerald-500/25"
                    : ["upload", "schema", "processing", "result"].indexOf(step) > i
                    ? "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400"
                    : "bg-slate-100 dark:bg-slate-700 text-slate-400 dark:text-slate-500"
                )}
              >
                {i + 1}
              </div>
              {i < 3 && (
                <div
                  className={cn(
                    "w-6 h-0.5 mx-1",
                    ["upload", "schema", "processing", "result"].indexOf(step) > i
                      ? "bg-emerald-200 dark:bg-emerald-800"
                      : "bg-slate-100 dark:bg-slate-700"
                  )}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="p-6">
        {/* Error Banner */}
        {error && (
          <div className="mb-4 flex items-start gap-3 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 animate-fade-in">
            <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-red-800 dark:text-red-300">Error</p>
              <p className="text-sm text-red-600 dark:text-red-400 mt-1">{error}</p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setError(null)}
              className="text-red-600 hover:text-red-800 hover:bg-red-100 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-900/30"
            >
              Dismiss
            </Button>
          </div>
        )}

        {/* Step 1: Upload */}
        {step === "upload" && (
          <div className="space-y-4 animate-fade-in">
            {/* File Dropzone */}
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={cn(
                "relative border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer",
                isDragActive
                  ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20"
                  : file
                  ? "border-emerald-300 dark:border-emerald-700 bg-emerald-50/50 dark:bg-emerald-900/10"
                  : "border-slate-200 dark:border-slate-600 hover:border-slate-300 dark:hover:border-slate-500 hover:bg-slate-50 dark:hover:bg-slate-700/50"
              )}
              onClick={() => document.getElementById("file-input")?.click()}
            >
              <input
                id="file-input"
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.txt,.csv,.md"
                onChange={handleFileSelect}
                className="hidden"
              />

              <div className="flex flex-col items-center">
                <div className="w-16 h-16 rounded-2xl bg-slate-100 dark:bg-slate-700 flex items-center justify-center mb-4">
                  {getFileIcon()}
                </div>

                {file ? (
                  <>
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{file.name}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                      {formatFileSize(file.size)} • Click to change
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
                      Drop a document here or click to browse
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                      Supports PDF, PNG, JPEG, TXT, CSV, MD
                    </p>
                  </>
                )}
              </div>
            </div>

            {/* Document Hint */}
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                Document Hint (Optional)
              </label>
              <textarea
                value={documentHint}
                onChange={(e) => setDocumentHint(e.target.value)}
                placeholder="Describe what this document contains to help the AI understand it better...

Example: This is a product catalog from a HVAC filter manufacturer, containing product specifications, pricing, and technical data."
                className="w-full h-24 p-3 text-sm bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-xl resize-none focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 focus:bg-white dark:focus:bg-slate-600 placeholder:text-slate-400 dark:placeholder:text-slate-500 dark:text-slate-200"
              />
            </div>

            {/* Analyze Button */}
            <Button
              onClick={analyzeSchema}
              disabled={!file || isAnalyzing}
              className="w-full h-12 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 shadow-lg shadow-emerald-500/25 rounded-xl text-sm font-medium"
            >
              {isAnalyzing ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Analyzing Document...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4 mr-2" />
                  Analyze & Propose Schema
                </>
              )}
            </Button>
          </div>
        )}

        {/* Step 2: Schema Review */}
        {step === "schema" && schema && (
          <div className="space-y-4 animate-fade-in">
            {/* Document Info */}
            <div className="p-4 rounded-xl bg-gradient-to-r from-emerald-50 to-teal-50 dark:from-emerald-900/20 dark:to-teal-900/20 border border-emerald-200 dark:border-emerald-800">
              <div className="flex items-center gap-2 mb-2">
                <Eye className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                <span className="text-sm font-semibold text-emerald-800 dark:text-emerald-300">
                  {schema.document_type}
                </span>
                {schema.product_family && (
                  <span className="px-2 py-0.5 rounded bg-emerald-200 dark:bg-emerald-800 text-emerald-800 dark:text-emerald-300 text-xs font-medium">
                    {schema.product_family}
                  </span>
                )}
              </div>
              <p className="text-sm text-emerald-700 dark:text-emerald-400">{schema.summary}</p>
            </div>

            {/* Variant Properties (Numeric) */}
            {schema.variant_properties && schema.variant_properties.length > 0 && (
              <div className="border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
                <div className="px-4 py-3 bg-slate-50 dark:bg-slate-700 border-b border-slate-200 dark:border-slate-600 flex items-center gap-2">
                  <Box className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                  <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                    Variant Properties ({schema.variant_properties.length})
                  </span>
                  <span className="text-xs text-slate-400 ml-auto">Numeric fields for Cypher math</span>
                </div>
                <div className="p-3 grid grid-cols-2 gap-2">
                  {schema.variant_properties.map((prop) => (
                    <div key={prop.name} className="flex items-center gap-2 p-2 rounded-lg bg-slate-50 dark:bg-slate-700/50">
                      <span className="px-2 py-0.5 rounded bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400 text-xs font-mono">
                        {prop.name}
                      </span>
                      <span className="text-xs text-slate-500 dark:text-slate-400">{prop.description}</span>
                      <span className="ml-auto px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400 text-[10px]">
                        {prop.type}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Category Dimensions */}
            {schema.category_dimensions && schema.category_dimensions.length > 0 && (
              <div className="border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
                <div className="px-4 py-3 bg-slate-50 dark:bg-slate-700 border-b border-slate-200 dark:border-slate-600 flex items-center gap-2">
                  <Link2 className="w-4 h-4 text-violet-600 dark:text-violet-400" />
                  <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                    Category Dimensions ({schema.category_dimensions.length})
                  </span>
                  <span className="text-xs text-slate-400 ml-auto">Faceted filtering</span>
                </div>
                <div className="divide-y divide-slate-100 dark:divide-slate-700">
                  {schema.category_dimensions.map((cat) => (
                    <div key={cat.label} className="p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="px-2 py-1 rounded-lg bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-400 text-xs font-mono font-medium">
                          {cat.label}
                        </span>
                        <span className="text-sm text-slate-600 dark:text-slate-400">{cat.description}</span>
                      </div>
                      {cat.example_values && cat.example_values.length > 0 && (
                        <div className="flex flex-wrap gap-1 pl-2">
                          {cat.example_values.map((val, i) => (
                            <span key={i} className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-400 text-xs">
                              {val}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Compatibility Rules */}
            {schema.compatibility_rules && schema.compatibility_rules.length > 0 && (
              <div className="border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
                <div className="px-4 py-3 bg-slate-50 dark:bg-slate-700 border-b border-slate-200 dark:border-slate-600 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400" />
                  <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                    Compatibility Rules ({schema.compatibility_rules.length})
                  </span>
                </div>
                <div className="p-3 space-y-2">
                  {schema.compatibility_rules.map((rule, i) => (
                    <div key={i} className="text-sm text-slate-600 dark:text-slate-400 p-2 rounded bg-amber-50 dark:bg-amber-900/20 border border-amber-100 dark:border-amber-800">
                      {rule}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Concepts */}
            {schema.concepts && schema.concepts.length > 0 && (
              <div className="border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
                <div className="px-4 py-3 bg-slate-50 dark:bg-slate-700 border-b border-slate-200 dark:border-slate-600 flex items-center gap-2">
                  <Database className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                  <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                    Semantic Concepts ({schema.concepts.length})
                  </span>
                </div>
                <div className="p-3 flex flex-wrap gap-2">
                  {schema.concepts.map((concept, i) => (
                    <span
                      key={i}
                      className="px-2.5 py-1 rounded-lg bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 text-xs font-medium border border-emerald-200 dark:border-emerald-800"
                    >
                      {concept}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-3">
              <Button
                variant="outline"
                onClick={() => setStep("upload")}
                className="flex-1 h-11 rounded-xl"
              >
                <ArrowLeft className="w-4 h-4 mr-2" />
                Back
              </Button>
              <Button
                variant="outline"
                onClick={analyzeSchema}
                disabled={isAnalyzing}
                className="h-11 rounded-xl"
              >
                <RefreshCw className={cn("w-4 h-4 mr-2", isAnalyzing && "animate-spin")} />
                Re-analyze
              </Button>
              <Button
                onClick={executeExtraction}
                className="flex-1 h-11 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 rounded-xl"
              >
                Confirm & Extract
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Processing */}
        {step === "processing" && (
          <div className="text-center py-16 animate-fade-in">
            <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-emerald-100 to-teal-100 dark:from-emerald-900/30 dark:to-teal-900/30 flex items-center justify-center">
              <Loader2 className="w-10 h-10 animate-spin text-emerald-600 dark:text-emerald-400" />
            </div>
            <h3 className="font-semibold text-slate-900 dark:text-slate-100 mb-2">
              Extracting Knowledge
            </h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 max-w-sm mx-auto">
              AI is reading the document and extracting entities, relationships, and concepts...
            </p>
            <div className="mt-6 flex justify-center gap-2">
              <div className="w-2 h-2 rounded-full bg-emerald-400 animate-bounce" style={{ animationDelay: "0ms" }} />
              <div className="w-2 h-2 rounded-full bg-emerald-400 animate-bounce" style={{ animationDelay: "150ms" }} />
              <div className="w-2 h-2 rounded-full bg-emerald-400 animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
          </div>
        )}

        {/* Step 4: Result */}
        {step === "result" && result && (
          <div className="space-y-4 animate-fade-in">
            {/* Success Banner */}
            <div className="flex items-center justify-between p-4 rounded-xl bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                <div>
                  <span className="text-sm font-medium text-emerald-800 dark:text-emerald-300 block">
                    Document Ingested Successfully
                  </span>
                  <span className="text-xs text-emerald-600 dark:text-emerald-400">
                    {file?.name}
                  </span>
                </div>
              </div>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <div className="p-4 rounded-xl bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 text-center">
                <div className="text-2xl font-bold text-blue-700 dark:text-blue-400">
                  {result.counts.product_variants}
                </div>
                <div className="text-xs text-blue-600 dark:text-blue-400">Variants</div>
              </div>
              <div className="p-4 rounded-xl bg-violet-50 dark:bg-violet-900/20 border border-violet-200 dark:border-violet-800 text-center">
                <div className="text-2xl font-bold text-violet-700 dark:text-violet-400">
                  {result.counts.categories}
                </div>
                <div className="text-xs text-violet-600 dark:text-violet-400">Categories</div>
              </div>
              <div className="p-4 rounded-xl bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 text-center">
                <div className="text-2xl font-bold text-emerald-700 dark:text-emerald-400">
                  {result.counts.concepts}
                </div>
                <div className="text-xs text-emerald-600 dark:text-emerald-400">Concepts</div>
              </div>
              <div className="p-4 rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 text-center">
                <div className="text-2xl font-bold text-amber-700 dark:text-amber-400">
                  {result.counts.accessories}
                </div>
                <div className="text-xs text-amber-600 dark:text-amber-400">Accessories</div>
              </div>
              <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-center">
                <div className="text-2xl font-bold text-slate-700 dark:text-slate-300">
                  {result.counts.relationships}
                </div>
                <div className="text-xs text-slate-600 dark:text-slate-400">Relationships</div>
              </div>
            </div>

            {/* Extracted Product Variants */}
            {result.extracted.products && result.extracted.products.length > 0 && (
              <div className="border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
                <div className="px-4 py-3 bg-slate-50 dark:bg-slate-700 border-b border-slate-200 dark:border-slate-600 flex items-center gap-2">
                  <Box className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                  <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                    Product Variants ({result.extracted.products.length})
                  </span>
                </div>
                <ScrollArea className="h-64">
                  <div className="p-3 space-y-2">
                    {result.extracted.products.map((product, i) => (
                      <div
                        key={i}
                        className="p-3 rounded-lg bg-slate-50 dark:bg-slate-700/50 border border-slate-100 dark:border-slate-600"
                      >
                        <div className="flex items-center gap-2 mb-2">
                          <span className="px-2 py-0.5 rounded bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400 text-xs font-mono font-medium">
                            {product.id}
                          </span>
                          <span className="text-xs text-slate-500 dark:text-slate-400">{product.family}</span>
                        </div>
                        {/* Numeric Properties */}
                        {product.variant_props && Object.keys(product.variant_props).length > 0 && (
                          <div className="flex flex-wrap gap-1 mb-2">
                            {Object.entries(product.variant_props).slice(0, 6).map(([k, v]) => (
                              <span key={k} className="px-1.5 py-0.5 rounded bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 text-[10px] font-mono">
                                {k}: {v}
                              </span>
                            ))}
                          </div>
                        )}
                        {/* Categories */}
                        {product.categories && product.categories.length > 0 && (
                          <div className="flex flex-wrap gap-1">
                            {product.categories.map((cat, j) => (
                              <span key={j} className="px-1.5 py-0.5 rounded bg-violet-50 dark:bg-violet-900/30 text-violet-700 dark:text-violet-400 text-[10px]">
                                {cat.label}: {cat.value}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </div>
            )}

            {/* Concepts */}
            {result.extracted.concepts && result.extracted.concepts.length > 0 && (
              <div className="border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
                <div className="px-4 py-3 bg-slate-50 dark:bg-slate-700 border-b border-slate-200 dark:border-slate-600 flex items-center gap-2">
                  <Database className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                  <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                    Semantic Concepts
                  </span>
                </div>
                <div className="p-3 flex flex-wrap gap-2">
                  {result.extracted.concepts.map((concept, i) => (
                    <span
                      key={i}
                      className="px-2.5 py-1 rounded-lg bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 text-xs font-medium border border-emerald-200 dark:border-emerald-800"
                    >
                      {concept}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Reset Button */}
            <Button
              variant="outline"
              onClick={reset}
              className="w-full h-11 rounded-xl border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700/50"
            >
              <ArrowRight className="w-4 h-4 mr-2" />
              Ingest Another Document
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
