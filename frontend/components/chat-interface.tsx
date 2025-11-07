"use client";

import type React from "react";
import { useState, useRef, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Send,
  Bot,
  User,
  FileText,
  Copy,
  ThumbsUp,
  ThumbsDown,
  Database,
  Code,
  AlertCircle,
  CheckCircle,
  Loader2,
  Download,
  Eye,
  EyeOff,
  ChevronDown,
  ChevronUp,
  BookOpen, // New: for references
  Building2, // New: for business rules
  Info, // New: for context info
  Activity, // New: for retrieval stats
  Clock,
  Pause,
  Plus,
  MessageSquare,
  ShoppingCart, // For PO workflow icon
  Package,
  ChevronRight,
  Image
} from "lucide-react";
import {toast, useToast } from "@/components/ui/use-toast";

// **ENHANCED: Updated interfaces for new API response**
interface SQLChatResponse {
  conversation_id: string;
  intent: string;
  sql_query?: string;
  explanation: string;
  tables_used?: string[];
  business_rules_applied?: string[]; // New field
  reference_context?: string[]; // New field
  query_result?: {
    success: boolean;
    data?: Array<Record<string, any>>;
    row_count?: number;
    error?: string;
  };
  final_answer: string;
  suggestion: string[]
  confidence: number;
  sample_data?: Array<Record<string, any>>;
  total_rows?: number;
  retrieval_stats?: {
    // New field
    total_results: number;
    metadata_results: number;
    business_logic_results: number;
    reference_results: number;
  };
  context_sources?: string[]; // New field
  po_workflow?: {
    workflow_id: string;
    order_date: string;
    extracted_date: string;
    status: string;
  };
  // po_suggestion?: {
  //   suggest_po: boolean;
  //   reason: string;
  //   suggestion_text: string;
  // };
  po_workflow_started?: boolean;
  chart?: ChartData
  chart_suggestions?: ChartSuggestion[]
  data_insights?: string
  // suggested_questions?: string[]
  requires_chart_selection?: boolean
}
interface FollowUpSuggestion {
  type: 'granularity_change' | 'comparison' | 'metric_addition' | 'time_period' | 'drill_down' | 'visualization_change'
  question: string
  reasoning: string
  action: {
    query_modification: string
    chart_type: string
    requires_new_data: boolean
  }
}
interface ChartData {
  success: boolean
  chart_id: string
  chart_json: string
  chart_html: string
  chart_png_base64?: string
  chart_type: string
  title: string
  data_points: number
  columns_used: {
    x: string
    y: string[]
  }
  timestamp: string
  followup_suggestions?: FollowUpSuggestion[]
}

interface ChartSuggestion {
  chart_type: string
  confidence: number
  reasoning: string
  config: {
    x: string
    y: string[]
    group_by?: string
  }
  title: string
  metadata: {
    name: string
    description: string
    icon: string
    best_for: string
  }
  thumbnail?: string
}
interface Message {
  id: string
  sender: "user" | "ai"
  content: string
  timestamp: Date
  conversation_id?: string
  intent?: string
  sql_query?: string
  explanation?: string
  tables_used?: string[]
  business_rules_applied?: string[]
  reference_context?: string[]
  query_result?: SQLChatResponse["query_result"]
  confidence?: number
  suggestion?: string[]
  sample_data?: any[]
  total_rows?: number
  retrieval_stats?: any
  context_sources?: string[]
  relatedDocuments?: string[]
  po_workflow?: any
  po_suggestion?: any
  po_workflow_started?: boolean
  
 // Visualization fields
  chart?: ChartData
  chart_suggestions?: ChartSuggestion[]
  data_insights?: string
  // suggested_questions?: string[]
  requires_chart_selection?: boolean
  direct_chart_generation?: boolean; 
  followup_suggestions?: FollowUpSuggestion[]
}

interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  documentCounts?: {
    metadata: number;
    businesslogic: number;
    references: number;
  };
}

interface Conversation {
  id: string;
  title: string;
  project_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

interface ChatInterfaceProps {
  selectedProject: Project | null
  isEmbeddingProcessing?: boolean
  conversations: Conversation[]
  currentConversationId: string | null
  onConversationChange: (conversationId: string | null) => void
  onNewConversation: () => void
}

// ==================== CHART SELECTION CARD ====================

interface ChartSelectionCardProps {
  suggestions: ChartSuggestion[]
  dataInsights?: string
  onSelect: (chartType: string) => void
}
const API_BASE_URL =
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "https://retail-ai-chatbot.onrender.com";

const ChartSelectionCard: React.FC<ChartSelectionCardProps> = ({
  suggestions,
  dataInsights,
  onSelect
}) => {
  const [selected, setSelected] = useState<string | null>(null)

  if (!suggestions || suggestions.length === 0) return null

  return (
    <div className="my-4 p-4 border-2 border-green-200 rounded-lg bg-gradient-to-br from-green-50 to-white">
      <div className="flex items-center gap-2 mb-3">
        <Activity className="h-5 w-5 text-primary" />
        <h3 className="font-semibold text-lg">Choose Your Visualization</h3>
      </div>

      {dataInsights && (
        <Alert className="mb-4 bg-blue-50 border-blue-200">
          <Info className="h-4 w-4 text-blue-600" />
          <AlertDescription className="text-sm text-blue-800">
            {dataInsights}
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {suggestions.map((suggestion, idx) => (
          <div
            key={suggestion.chart_type}
            className={`relative border-2 rounded-lg p-4 cursor-pointer transition-all hover:shadow-lg ${
              selected === suggestion.chart_type
                ? 'border-primary bg-green-100 shadow-lg scale-105'
                : 'border-gray-300 hover:border-primary hover:shadow-md'
            }`}
            onClick={() => {
              setSelected(suggestion.chart_type)
              onSelect(suggestion.chart_type)
            }}
          >
            {idx === 0 && (
              <Badge className="absolute top-2 right-2 bg-primary text-white text-xs">
                Recommended
              </Badge>
            )}
            
            <Badge variant="outline" className="absolute top-2 left-2 text-xs">
              {suggestion.confidence}% match
            </Badge>

            <div className="mt-8 mb-3 bg-white rounded-lg overflow-hidden border">
              {suggestion.thumbnail ? (
                <img 
                  src={suggestion.thumbnail}
                  alt={suggestion.chart_type}
                  className="w-full h-40 object-contain p-2"
                />
              ) : (
                <div className="w-full h-40 flex items-center justify-center bg-gray-50">
                  <span className="text-5xl">{suggestion.metadata?.icon || '📊'}</span>
                </div>
              )}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="font-semibold text-sm">
                  {suggestion.metadata?.name || suggestion.chart_type.toUpperCase()}
                </h4>
                {selected === suggestion.chart_type && (
                  <CheckCircle className="h-5 w-5 text-primary" />
                )}
              </div>

              <p className="text-xs text-gray-600 line-clamp-2">
                {suggestion.metadata?.description || suggestion.reasoning}
              </p>

              <div className="pt-2 border-t text-xs text-gray-500">
                <strong>Best for:</strong> {suggestion.metadata?.best_for || 'General analysis'}
              </div>
            </div>

            <Button
              variant={selected === suggestion.chart_type ? "default" : "outline"}
              size="sm"
              className="w-full mt-3"
              onClick={(e) => {
                e.stopPropagation()
                setSelected(suggestion.chart_type)
                onSelect(suggestion.chart_type)
              }}
            >
              {selected === suggestion.chart_type ? (
                <>
                  <CheckCircle className="h-3 w-3 mr-1" />
                  Selected
                </>
              ) : (
                'Select This Chart'
              )}
            </Button>
          </div>
        ))}
      </div>
    </div>
  )
}

// ==================== SMART FOLLOW-UP BUTTONS ====================

interface SmartFollowUpButtonsProps {
  suggestions: FollowUpSuggestion[]
  onSuggestionClick: (suggestion: FollowUpSuggestion) => void
}

const SmartFollowUpButtons: React.FC<SmartFollowUpButtonsProps> = ({ 
  suggestions, 
  onSuggestionClick 
}) => {
  const getIconForType = (type: string) => {
    switch (type) {
      case 'granularity_change':
        return <Clock className="h-1 w-1" />
      case 'comparison':
        return <Activity className="h-1 w-1" />
      case 'metric_addition':
        return <Plus className="h-1 w-1" />
      case 'time_period':
        return <Clock className="h-1 w-1" />
      case 'drill_down':
        return <ChevronDown className="h-1 w-1" />
      case 'visualization_change':
        return <Activity className="h-1 w-1" />
      default:
        return <Info className="h-1 w-1" />
    }
  }

  const getBadgeColor = (type: string) => {
    switch (type) {
      case 'granularity_change':
        return 'bg-blue-100 text-blue-700 border-blue-300'
      case 'comparison':
        return 'bg-green-100 text-green-700 border-green-300'
      case 'drill_down':
        return 'bg-purple-100 text-purple-700 border-purple-300'
      case 'time_period':
        return 'bg-orange-100 text-orange-700 border-orange-300'
      default:
        return 'bg-gray-100 text-gray-700 border-gray-300'
    }
  }

  if (!suggestions || suggestions.length === 0) return null

  return (
    <div className="mt-4 p-4 bg-gradient-to-r from-green-50 to-blue-50 rounded-lg border border-green-200">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">💡</span>
        <p className="text-sm font-semibold text-gray-700">You might also want to:</p>
      </div>

      <div className="space-y-2">
        {suggestions.map((suggestion, idx) => (
          <div
            key={idx}
            className="group flex items-start gap-3 p-3 bg-white rounded-lg border border-gray-200 hover:border-primary hover:shadow-md transition-all cursor-pointer"
            onClick={() => onSuggestionClick(suggestion)}
          >
            <div className="flex-shrink-0 mt-1">
              <Badge variant="outline" className={`text-xs ${getBadgeColor(suggestion.type)}`}>
                {getIconForType(suggestion.type)}
                <span className="ml-1 capitalize">
                  {suggestion.type.replace('_', ' ')}
                </span>
              </Badge>
            </div>

            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 group-hover:text-primary transition-colors">
                {suggestion.question}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                {suggestion.reasoning}
              </p>
            </div>

            <div className="flex-shrink-0">
              <ChevronRight className="h-4 w-4 text-gray-400 group-hover:text-primary transition-colors" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ==================== CHART DISPLAY ====================

interface ChartDisplayProps {
  chart: ChartData
  conversationId?: string
  followupSuggestions?: FollowUpSuggestion[]
  onSuggestionClick?: (suggestion: FollowUpSuggestion) => void
}

const ChartDisplay: React.FC<ChartDisplayProps> = ({ 
  chart, 
  conversationId, 
  followupSuggestions,
  onSuggestionClick 
}) => {
  const { toast } = useToast()

  if (!chart) {
    console.warn("❌ ChartDisplay: No chart prop received");
    return <div>⚠️ No chart data</div>;
  }

  if (!chart.success) {
    console.warn("❌ ChartDisplay: Chart not successful");
    return <div>⚠️ Chart marked unsuccessful</div>;
  }

  if (!chart.chart_html && !chart.chart_png_base64) {
    console.error("❌ ChartDisplay: No HTML or image available", chart);
    return <div>⚠️ No chart visualization available</div>;
  }
  const downloadPDF = async () => {
    try {
      if (!chart?.chart_id) {
        throw new Error("Chart ID is missing")
      }
      const requestPayload = {
        chart_ids: [chart.chart_id],        // ✅ Array of strings
        report_title: chart.title || "Chart Report",
        include_insights: true,
        conversation_id: conversationId
      }
      
      const cleanPayload = JSON.parse(JSON.stringify(requestPayload))
      console.log("📤 Clean Request Payload:")
      console.log(JSON.stringify(cleanPayload, null, 2))

      const token = localStorage.getItem("access_token");
      if (!token) {
        throw new Error("No authentication token found. Please log in again.");
      }
      const response = await fetch(`${API_BASE_URL}/visualizations/generate-pdf`, {
        method: 'POST',
        headers: { 
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json'
          
        },
        body: JSON.stringify(cleanPayload)
      })

      if (!response.ok) {
      const error = await response.json()
      console.error("❌ PDF download error:", error)
      throw new Error(error.detail || 'Download failed')
    }

      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${chart.title.replace(/[^a-z0-9]/gi, '_')}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)

      toast({
        title: "Downloaded Successfully!",
        description: "Chart has been saved as PDF",
      })
    } catch (error) {
      console.error('PDF download error:', error)
      toast({
        title: "Download Failed",
        description: "Unable to download chart as PDF",
        variant: "destructive"
      })
    }
  }

  const downloadHTML = () => {
    try {
      const blob = new Blob([chart.chart_html], { type: 'text/html' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${chart.title.replace(/[^a-z0-9]/gi, '_')}.html`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)

      toast({
        title: "Downloaded Successfully!",
        description: "Interactive chart saved as HTML",
      })
    } catch (error) {
      console.error('HTML download error:', error)
      toast({
        title: "Download Failed",
        description: "Unable to download HTML",
        variant: "destructive"
      })
    }
  }
  const downloadPNG = () => {
    try {
      if (!chart?.chart_png_base64) {
        console.error("No chart PNG data available");
        toast({
          title: "Download Failed",
          description: "No PNG data available for this chart",
          variant: "destructive"
        });
        return;
      }

      // Convert base64 to blob
      const byteCharacters = atob(chart.chart_png_base64);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { type: "image/png" });

      // Create download link
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      
      // Generate filename: chart-title-YYYY-MM-DD.png
      const dateStr = new Date().toISOString().slice(0, 10);
      const filename = `${chart.title.toLowerCase().replace(/\s+/g, "-")}-${dateStr}.png`;
      
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      toast({
        title: "Downloaded Successfully!",
        description: "Chart has been saved as PNG",
      });
    } catch (error) {
      console.error("PNG download error:", error);
      toast({
        title: "Download Failed",
        description: "Unable to download chart as PNG",
        variant: "destructive"
      });
    }
  };


  if (!chart || !chart.success) return null
  return (
    <div className="w-full">
    {/* Header */}
    <div className="bg-muted/50 border border-b-0 border-border/30 rounded-t-md px-4 py-2 flex items-center justify-between gap-2">
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <Activity className="h-3.5 w-3.5 text-primary flex-shrink-0" />
        <span className="font-medium text-xs text-foreground truncate">{chart.title}</span>
        <Badge variant="outline" className="text-[10px] h-4 flex-shrink-0">
          {chart.data_points} pts
        </Badge>
        <Badge variant="secondary" className="text-[10px] h-4 capitalize flex-shrink-0">
          {chart.chart_type}
        </Badge>
      </div>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" className="h-6 px-2 text-xs flex-shrink-0 ml-2">
            <Download className="h-3 w-3 mr-1" />
            Download
            <ChevronDown className="h-3 w-3 ml-1" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={downloadPDF}>
            <FileText className="h-3 w-3 mr-2" />
            PDF
          </DropdownMenuItem>
          <DropdownMenuItem onClick={downloadHTML}>
            <Code className="h-3 w-3 mr-2" />
            HTML
          </DropdownMenuItem>
          <DropdownMenuItem onClick={downloadPNG}>
            <Image className="h-3 w-3 mr-2" />
            PNG
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>

    {/* Chart Container */}
    <div className="w-full border border-t-0 border-border/30 rounded-b-md bg-white dark:bg-background overflow-hidden flex items-center justify-center" style={{ height: '350px' }}>
      {chart.chart_html ? (
        <iframe
          srcDoc={chart.chart_html}
          title={chart.title}
          className="w-full h-full border-0"
          style={{ display: 'block', background: 'white' }}
        />
      ) : chart.chart_png_base64 ? (
        <img
          src={`data:image/png;base64,${chart.chart_png_base64}`}
          alt="Chart"
          className="w-full h-full object-contain"
        />
      ) : (
        <div className="flex items-center justify-center h-full text-sm text-muted-foreground italic">
          No chart visualization available.
        </div>
      )}
    </div>

    {/* Followup Suggestions */}
    {followupSuggestions && followupSuggestions.length > 0 && onSuggestionClick && (
      <div className="px-3 py-2 border-t border-border/30 bg-muted/30">
        <SmartFollowUpButtons
          suggestions={followupSuggestions}
          onSuggestionClick={onSuggestionClick}
        />
      </div>
    )}
  </div>
)

}
// **ENHANCED: Business Rules & References Display Component**
// const BusinessContextDisplay = ({
//   business_rules_applied,
//   reference_context
// }: {
//   business_rules_applied?: string[]
//   reference_context?: string[]
// }) => {
//   if ((!business_rules_applied || business_rules_applied.length === 0) &&
//       (!reference_context || reference_context.length === 0)) return null

//   return (
//     <div className="space-y-1">
//       {/* Business Rules */}
//       {business_rules_applied && business_rules_applied.length > 0 && (
//         <div className="flex items-center gap-1 flex-wrap">
//           <Building2 className="h-3 w-3 text-accent" />
//           <span className="text-xs text-muted-foreground">Rules Applied:</span>
//           {business_rules_applied.slice(0, 3).map((rule, index) => (
//             <Badge key={index} variant="secondary" className="text-xs py-0 px-1 h-4">
//               {rule.length > 20 ? `${rule.substring(0, 20)}...` : rule}
//             </Badge>
//           ))}
//           {business_rules_applied.length > 3 && (
//             <Badge variant="outline" className="text-xs py-0 px-1 h-4">
//               +{business_rules_applied.length - 3} more
//             </Badge>
//           )}
//         </div>
//       )}

//       {/* Reference Context */}
//       {reference_context && reference_context.length > 0 && (
//         <div className="flex items-center gap-1 flex-wrap">
//           <BookOpen className="h-3 w-3 text-chart-3" />
//           <span className="text-xs text-muted-foreground">References:</span>
//           {reference_context.slice(0, 2).map((ref, index) => (
//             <Badge key={index} variant="outline" className="text-xs py-0 px-1 h-4">
//               Ref {index + 1}
//             </Badge>
//           ))}
//           {reference_context.length > 2 && (
//             <Badge variant="outline" className="text-xs py-0 px-1 h-4">
//               +{reference_context.length - 2} more
//             </Badge>
//           )}
//         </div>
//       )}
//     </div>
//   )
// }

// **ENHANCED: SQL Result Display Component with new context info**
const SQLResultDisplay = ({
  sqlQuery,
  queryResult,
  data,
  sample_data,
  total_rows,
  tables_used,
  business_rules_applied,
  reference_context,
  // context_sources,
  retrieval_stats,
}: {
  sqlQuery?: string;
  queryResult?: SQLChatResponse["query_result"];
  data?: Array<Record<string, any>>;
  sample_data?: Array<Record<string, any>>;
  total_rows?: number;
  tables_used?: string[];
  business_rules_applied?: string[];
  reference_context?: string[];
  // context_sources?: string[]
  retrieval_stats?: SQLChatResponse["retrieval_stats"];
}) => {
  const [showSQL, setShowSQL] = useState(false);
  const [showData, setShowData] = useState(false);
  const [showContext, setShowContext] = useState(false);

  const copySQL = () => {
    if (sqlQuery) {
      navigator.clipboard.writeText(sqlQuery);
      toast({
        title: "SQL Copied!",
        description: "SQL query copied to clipboard",
        duration: 2000,
      });
    }
  };

  const downloadCSV = () => {
    const exportData = data && data.length > 0 ? data : sample_data;

    if (exportData && exportData.length > 0) {
      const headers = Object.keys(exportData[0]);
      const csvContent = [
        headers.join(","),
        ...exportData.map((row) =>
          headers
            .map((header) => {
              const value = row[header];
              return typeof value === "string"
                ? `"${value.replace(/"/g, '""')}"`
                : value;
            })
            .join(",")
        ),
      ].join("\n");

      const blob = new Blob([csvContent], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "query_results.csv";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast({
        title: "Downloaded!",
        description: "Query results downloaded as CSV",
        duration: 2000,
      });
    }
  };

  // if (!sqlQuery && !sample_data && !context_sources) return null
  if (!sqlQuery && !sample_data) return null;

  return (
    <div className="mt-3 space-y-2">
      {/* Query Status - Compact */}
      {queryResult && (
        <div className="flex items-center gap-2 text-xs">
          {queryResult.success ? (
            <CheckCircle className="h-3 w-3 text-green-500" />
          ) : (
            <AlertCircle className="h-3 w-3 text-red-500" />
          )}
          <span
            className={`font-medium ${queryResult.success ? "text-green-700" : "text-red-700"
              }`}
          >
            {queryResult.success ? "Success" : "Failed"}
          </span>
          {queryResult.success && total_rows !== undefined && (
            <Badge variant="secondary" className="text-xs py-0 px-1 h-4">
              {total_rows} rows
            </Badge>
          )}
        </div>
      )}

      {/* Context Sources Display */}
      {/* <ContextSourcesDisplay 
        context_sources={context_sources}
        retrieval_stats={retrieval_stats}
      /> */}

      {/* Tables Used - Compact */}
      {tables_used && tables_used.length > 0 && (
        <div className="flex items-center gap-1 flex-wrap">
          <Database className="h-3 w-3 text-primary" />
          <span className="text-xs text-muted-foreground">Tables:</span>
          {tables_used.map((table, index) => (
            <Badge
              key={index}
              variant="outline"
              className="text-xs py-0 px-1 h-4 font-mono"
            >
              {table}
            </Badge>
          ))}
        </div>
      )}

      {/* Business Context Display */}
      {/* <BusinessContextDisplay 
        business_rules_applied={business_rules_applied}
        reference_context={reference_context}
      /> */}

      {/* Enhanced Context Details - Collapsible */}
      {/* {(business_rules_applied?.length || reference_context?.length || retrieval_stats) && (
        <div className="border rounded">
          <div 
            className="flex items-center justify-between p-2 cursor-pointer hover:bg-muted/50 transition-colors"
            onClick={() => setShowContext(!showContext)}
          >
            <div className="flex items-center gap-1">
              <Info className="h-3 w-3 text-primary" />
              <span className="text-xs font-medium">Context Details</span>
            </div>
            {showContext ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </div>
          {showContext && (
            <div className="px-2 pb-2 space-y-2"> */}
      {/* Retrieval Statistics */}
      {/* {retrieval_stats && (
                <div className="text-xs space-y-1">
                  <div className="font-medium text-muted-foreground">Retrieval Statistics:</div>
                  <div className="grid grid-cols-2 gap-1 text-xs">
                    <div>Total Results: {retrieval_stats.total_results}</div>
                    <div>Schema: {retrieval_stats.metadata_results}</div>
                    <div>Rules: {retrieval_stats.business_logic_results}</div>
                    <div>Docs: {retrieval_stats.reference_results}</div>
                  </div>
                </div>
              )} */}

      {/* Business Rules Details */}
      {/* {business_rules_applied && business_rules_applied.length > 0 && (
                <div className="text-xs space-y-1">
                  <div className="font-medium text-muted-foreground">Business Rules Applied:</div>
                  <div className="space-y-1 max-h-20 overflow-y-auto">
                    {business_rules_applied.map((rule, index) => (
                      <div key={index} className="text-xs bg-muted/50 p-1 rounded">
                        {rule}
                      </div>
                    ))}
                  </div>
                </div>
              )}
               */}
      {/* Reference Context Details */}
      {/* {reference_context && reference_context.length > 0 && (
                <div className="text-xs space-y-1">
                  <div className="font-medium text-muted-foreground">Reference Context:</div>
                  <div className="space-y-1 max-h-20 overflow-y-auto">
                    {reference_context.map((ref, index) => (
                      <div key={index} className="text-xs bg-muted/50 p-1 rounded">
                        Reference {index + 1}: {ref.substring(0, 100)}...
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )} */}

      {/* SQL Query Collapsible - Compact */}
      {sqlQuery && (
        <div className="border rounded">
          <div
            className="flex items-center justify-between p-2 cursor-pointer hover:bg-muted/50 transition-colors"
            onClick={() => setShowSQL(!showSQL)}
          >
            <div className="flex items-center gap-1">
              <Code className="h-3 w-3 text-primary" />
              <span className="text-xs font-medium">SQL Query</span>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  copySQL();
                }}
                className="h-5 w-5 p-0"
              >
                <Copy className="h-2 w-2" />
              </Button>
              {showSQL ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </div>
          </div>
          {showSQL && (
            <div className="px-2 pb-2">
              {/* <pre className="text-xs bg-muted/50 p-2 rounded border overflow-x-auto font-mono max-h-32 overflow-y-auto">
                <code>{sqlQuery}</code> */}
              <pre className="text-xs bg-muted/50 p-3 rounded border overflow-x-auto font-mono max-h-40 overflow-y-auto whitespace-pre-wrap break-words">
                <code className="text-foreground whitespace-pre-wrap">
                  {sqlQuery}
                </code>
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Query Error - Compact */}
      {queryResult?.error && (
        <Alert variant="destructive" className="py-2">
          <AlertCircle className="h-3 w-3" />
          <AlertDescription className="text-xs">
            {queryResult.error}
          </AlertDescription>
        </Alert>
      )}

      {/* Data Table Display - Compact */}
      {sample_data && sample_data.length > 0 && (
        <div className="border rounded">
          <div
            className="flex items-center justify-between p-2 cursor-pointer hover:bg-muted/50 transition-colors"
            onClick={() => setShowData(!showData)}
          >
            <div className="flex items-center gap-1">
              <Database className="h-3 w-3 text-accent" />
              <span className="text-xs font-medium">
                Results
                <span className="text-muted-foreground font-normal ml-1">
                  ({sample_data.length}/{total_rows || sample_data.length})
                </span>
              </span>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  downloadCSV();
                }}
                className="h-5 w-5 p-0"
              >
                <Download className="h-2 w-2" />
              </Button>
              {showData ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </div>
          </div>
          {showData && (
            <div className="px-2 pb-2">
              <div className="border rounded overflow-hidden bg-background">
                <div className="max-h-48 max-w-full overflow-auto">
                  <Table>
                    <TableHeader className="sticky top-0 bg-muted">
                      <TableRow>
                        {Object.keys(sample_data[0]).map((header) => (
                          <TableHead
                            key={header}
                            className="whitespace-nowrap text-xs font-medium py-1 px-2 h-6"
                          >
                            {header}
                          </TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {sample_data.map((row, index) => (
                        <TableRow key={index} className="hover:bg-muted/30">
                          {Object.values(row).map((value, cellIndex) => (
                            <TableCell
                              key={cellIndex}
                              className="text-xs font-mono py-1 px-2"
                            >
                              {value !== null && value !== undefined
                                ? String(value).length > 50
                                  ? `${String(value).substring(0, 50)}...`
                                  : String(value)
                                : "NULL"}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                {total_rows && total_rows > sample_data.length && (
                  <div className="p-1 bg-muted/50 text-center border-t">
                    <span className="text-xs text-muted-foreground">
                      Showing first {sample_data.length} of {total_rows} rows
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// Auto-scroll Hook
const useChatScroll = (dep: any) => {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight;
    }
  }, [dep]);

  return ref;
};

// Utility functions
const shouldShowIntent = (intent?: string): boolean => {
  if (!intent) return false;

  const words = intent.replace(/_/g, " ").trim().split(/\s+/);
  const meaningfulWords = words.filter((word) => word.length > 2);

  return meaningfulWords.length > 2;
};

const shouldShowConfidence = (confidence?: number): boolean => {
  return confidence !== undefined && confidence >= 0.5;
};

// **ENHANCED: Message Bubble Component with new context display**
const MessageBubble = ({
  message,
  conversation_id,
  onCopy,
  onFeedback,
  onSuggestionClick,
  onChartSelect,
  onFollowupClick
}: {
  message: Message;
  conversation_id: string | null
  onCopy: (content: string) => void;
  onFeedback: (messageId: string, type: "up" | "down") => void;
  onSuggestionClick: (suggestion: string) => void;
  onChartSelect: (selection: string) => void;
  onFollowupClick: (suggestion: FollowUpSuggestion) => void;
}) => {
  const formatTimestamp = (timestamp: Date) => {
    return timestamp.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getMessageWidth = (content: string, sender: string, hasChart?:boolean) => {
    if (hasChart) {
      return "max-w-[85%]";
    }
    const contentLength = content.length;

    if (sender === "user") {
      if (contentLength <= 15) return "w-fit max-w-[150px]";
      if (contentLength <= 50) return "w-fit max-w-[250px]";
      if (contentLength <= 100) return "w-fit max-w-[400px]";
      return "max-w-[85%]";
    } else {
      if (contentLength <= 50) return "w-fit max-w-[300px]";
      return "max-w-[85%]";
    }
  };

  const messageWidthClass = getMessageWidth(message.content, message.sender, !!message.chart);
  // **NEW: PO Workflow Status Component**
  const POWorkflowDisplay = ({
    po_workflow,
    // po_suggestion,
  }: {
    po_workflow?: SQLChatResponse["po_workflow"];
    // po_suggestion?: SQLChatResponse["po_suggestion"];
  }) => {
    // if (!po_workflow && !po_suggestion) return null;
    if (!po_workflow) return null;

    return (
      <div className="mt-3 space-y-2">
        {/* PO Workflow Status */}
        {po_workflow && (
          <div className="border rounded bg-blue-50 dark:bg-blue-900/20">
            <div className="p-3">
              <div className="flex items-center gap-2 mb-2">
                <div className="flex items-center gap-1">
                  {po_workflow.status === "initiated" ? (
                    <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                  ) : (
                    <CheckCircle className="h-4 w-4 text-green-600" />
                  )}
                  <span className="text-sm font-medium text-blue-900 dark:text-blue-100">
                    Purchase Order Workflow
                  </span>
                </div>
                <Badge variant="secondary" className="text-xs">
                  {po_workflow.status}
                </Badge>
              </div>

              <div className="text-xs space-y-1 text-blue-800 dark:text-blue-200">
                <div>
                  🔄 Status: Processing material shortfalls and vendor
                  selection...
                </div>
              </div>
            </div>
          </div>
        )}

        {/* PO Suggestion */}
        {/*po_suggestion?.suggest_po && (
          <div className="border rounded bg-amber-50 dark:bg-amber-900/20 border-amber-200">
            <div className="p-3">
              <div className="flex items-center gap-2 mb-2">
                <AlertCircle className="h-4 w-4 text-amber-600" />
                <span className="text-sm font-medium text-amber-900 dark:text-amber-100">
                  PO Suggestion
                </span>
              </div>
              <div className="text-xs text-amber-800 dark:text-amber-200">
                {po_suggestion.suggestion_text}
              </div>
            </div>
          </div>
        )*/}
      </div>
    );
  };
  return (
    <div
      className={`flex gap-2 ${message.sender === "user" ? "justify-end" : "justify-start"
        }`}
    >
      {message.sender === "ai" && (
        <Avatar className="h-6 w-6 flex-shrink-0 mt-1">
          <AvatarFallback className="bg-secondary text-primary-foreground text-xs">
            <Bot className="h-3 w-3" />
          </AvatarFallback>
        </Avatar>
      )}

      <div
        className={`flex flex-col gap-1 ${messageWidthClass} min-w-0 ${message.sender === "user" ? "items-end" : "items-start"
          }`}
      >
        <Card
          className={`${message.sender === "user"
              ? "bg-secondary text-primary-foreground border-primary"
              : "bg-card border-border"
            } shadow-sm overflow-hidden`}
          style={{ maxWidth: "100%" }}
        >
          <CardContent className="px-3 py-2 overflow-hidden">
            <div className="space-y-1 overflow-hidden">
              <p className="text-sm leading-5 whitespace-pre-wrap break-words">
                {message.content}
              </p>
              {/* {message.sender === "ai" && message.suggestion && message.suggestion.length > 0 && (
                <div className="mt-4 space-y-2">
                  <p className="text-sm text-muted-foreground font-medium">
                    Would you like me to help with any of these next?
                  </p>
                  <div className="space-y-1.5">
                    {message.suggestion.map((suggestion, index) => (
                      <div
                        key={index}
                        className="flex items-start gap-2 text-sm text-foreground/80 pl-2 border-l-2 border-primary/20"
                      >
                        <span className="text-primary mt-0.5">•</span>
                        <span>{suggestion}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )} */}


              {/* Enhanced Intent and Confidence Display */}
              {/* {message.sender === "ai" && (shouldShowIntent(message.intent) || shouldShowConfidence(message.confidence)) && (
                <div className="flex items-center gap-1 pt-1 border-t border-border/20">
                  {shouldShowIntent(message.intent) && (
                    <Badge variant="outline" className="text-xs py-0 px-1 h-4">
                      {message.intent?.replace(/_/g, ' ')}
                    </Badge>
                  )}
                  {shouldShowConfidence(message.confidence) && (
                    <Badge variant="secondary" className="text-xs py-0 px-1 h-4">
                      {Math.round((message.confidence || 0) * 100)}%
                    </Badge>
                  )}
                </div>
              )} */}
              {message.sender === "ai" && shouldShowIntent(message.intent) && (
                <div className="flex items-center gap-1 pt-1 border-t border-border/20 min-w-0">
                  {shouldShowIntent(message.intent) && (
                    <Badge
                      variant="outline"
                      className="text-xs py-1 px-2 max-w-full whitespace-normal break-words flex-shrink min-w-0 h-auto leading-tight"
                    >
                      {message.intent?.replace(/_/g, " ")}
                    </Badge>
                  )}
                </div>
              )}

              {/* Enhanced SQL Result Display */}
              {message.sender === "ai" && (
                <div className="overflow-hidden max-w-full">
                  <SQLResultDisplay
                    sqlQuery={message.sql_query}
                    queryResult={message.query_result}
                    data={message.query_result?.data}
                    sample_data={message.sample_data}
                    total_rows={message.total_rows}
                    tables_used={message.tables_used}
                    business_rules_applied={message.business_rules_applied}
                    reference_context={message.reference_context}
                  // context_sources={message.context_sources}
                  // retrieval_stats={message.retrieval_stats}
                  />
                  <POWorkflowDisplay
                    po_workflow={message.po_workflow}
                    // po_suggestion={message.po_suggestion}
                  />
                </div>
              )}
              {message.sender === "ai" && message.chart && (
                    <ChartDisplay
                      chart={message.chart}
                      conversationId={conversation_id || ""}
                      followupSuggestions={message.followup_suggestions}
                      onSuggestionClick={onFollowupClick}
                    />
                )}
              {message.sender === "ai" && message.requires_chart_selection && !message.direct_chart_generation && message.chart_suggestions && message.chart_suggestions.length > 0 &&(
                <ChartSelectionCard
                  suggestions={message.chart_suggestions}
                  dataInsights={message.data_insights}
                  onSelect={onChartSelect}
                />
              )}
              {message.sender === "ai" && message.suggestion && message.suggestion.length > 0 && (
                  <div className="mt-3 p-3 bg-muted/30 rounded-lg border">
                    <p className="text-sm text-muted-foreground font-medium mb-2">
                      Would you like me to help with any of these next?
                    </p>
                    <div className="space-y-2">
                      {message.suggestion.map((sug, idx) => (
                        <button
                          key={idx}
                          onClick={() => onSuggestionClick(sug)}
                          className="w-full text-left text-xs p-3 rounded-md border border-border hover:border-primary hover:bg-accent/60 transition-colors bg-background"
                        >
                          <div className="flex items-start gap-2">
                            <ChevronRight className="h-3 w-3 text-muted-foreground flex-shrink-0 mt-0.5" />
                            <span className="flex-1 leading-relaxed">{sug}</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
              )}

            </div>
          </CardContent>
        </Card>

        {/* Message Actions - Compact */}
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <span>{formatTimestamp(message.timestamp)}</span>

          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-4 w-4 p-0 hover:bg-muted"
              onClick={() => onCopy(message.content)}
            >
              <Copy className="h-2 w-2" />
            </Button>
            {/* {message.sender === "ai" && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-4 w-4 p-0 hover:bg-muted"
                  onClick={() => onFeedback(message.id, "up")}
                >
                  <ThumbsUp className="h-2 w-2" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-4 w-4 p-0 hover:bg-muted"
                  onClick={() => onFeedback(message.id, "down")}
                >
                  <ThumbsDown className="h-2 w-2" />
                </Button>
              </>
            )} */}
          </div>
        </div>
      </div>

      {message.sender === "user" && (
        <Avatar className="h-6 w-6 flex-shrink-0 mt-1">
          <AvatarFallback className="bg-muted text-muted-foreground text-xs">
            <User className="h-3 w-3" />
          </AvatarFallback>
        </Avatar>
      )}
    </div>
  );
};

// **NEW: Embedding Processing Banner Component**
// const EmbeddingProcessingBanner = () => {
//   return (
//     <div className="bg-amber-50 border-b border-amber-200 p-3 flex-shrink-0">
//       <div className="max-w-4xl mx-auto">
//         <div className="flex items-center gap-3">
//           <div className="flex items-center gap-2">
//             <Loader2 className="h-4 w-4 animate-spin text-amber-600" />
//             <Clock className="h-4 w-4 text-amber-600" />
//           </div>
//           <div className="flex-1">
//             <div className="flex items-center gap-2 mb-1">
//               <span className="text-sm font-medium text-amber-800">
//                 Processing Documents
//               </span>
//               <Badge variant="secondary" className="bg-amber-100 text-amber-700 text-xs">
//                 Creating Embeddings
//               </Badge>
//             </div>
//             <p className="text-xs text-amber-700">
//               Documents are being processed to enhance search capabilities.
//               Chat functionality is limited until processing completes.
//             </p>
//           </div>
//           <div className="text-xs text-amber-600 bg-amber-100 px-2 py-1 rounded">
//             Please wait...
//           </div>
//         </div>
//       </div>
//     </div>
//   )
// }

// **ENHANCED: Main ChatInterface Component with updated API call**
export function ChatInterface({
  selectedProject,
  isEmbeddingProcessing = false,
  conversations,
  currentConversationId,
  onConversationChange,
  onNewConversation,
}: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [message, setMessage] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom when new messages arrive
  const messagesEndRef = useChatScroll(messages);

  // Initialize welcome message
  useEffect(() => {
    if (currentConversationId) {
      loadConversationMessages(currentConversationId);
    } else {
      // Clear messages for new chat or show welcome message
      if (selectedProject?.id) {
        setMessages([
          {
            id: "welcome",
            content: `Hello! I'm your Supply Chain Assistant for "${selectedProject.name}". 
                      I can help you:
                      📊 Query your database using natural language
                      📋 Generate purchase orders by saying "generate PO for today"
                      💡 Analyze data and suggest PO creation when shortfalls are found
                      What would you like to do?`,
            sender: "ai",
            timestamp: new Date(),
            intent: isEmbeddingProcessing ? "processing_status" : "welcome",
          },
        ]);
      } else {
        setMessages([]);
      }
    }
  }, [currentConversationId, selectedProject?.id, isEmbeddingProcessing]);

  // ADD: Function to load conversation messages
  const loadConversationMessages = async (conversationId: string) => {
    try {
      const token = localStorage.getItem("access_token");
      const response = await fetch(
        `${API_BASE_URL}/chat/conversation/${conversationId}/messages`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        const data = await response.json();
        if (!data.messages || data.messages.length === 0) {
          // Show welcome message for empty conversations
          if (selectedProject?.id) {
            setMessages([
              {
                id: "welcome",
                content: `Hello! I'm your Supply Chain Assistant for "${selectedProject.name}". I can help you query your database using schema information, business rules, and documentation. What would you like to know?`,
                sender: "ai",
                timestamp: new Date(),
                intent: isEmbeddingProcessing ? "processing_status" : "welcome",
              },
            ]);
          } else {
            setMessages([]);
          }
          return; // Exit early for empty conversations
        }

        const formattedMessages = data.messages.map((msg: any) => {
          let queryResult = msg.query_result;
          let metadata = msg.metadata || {};
          
          if (typeof queryResult === "string") {
            try {
              queryResult = JSON.parse(queryResult);
            } catch (e) {
              console.warn("Failed to parse query_result:", e);
              queryResult = null;
            }
          }
          if (metadata && typeof metadata === "string") {
            try {
              metadata = JSON.parse(metadata);
            } catch (e) {
              console.warn("Failed to parse metadata:", e);
              metadata = null;
            }
          }
          if (!metadata || typeof metadata !== "object") {
              metadata = {}
            }
         
          // const chartData = metadata?.chart
          // const chartSuggestions = metadata?.chart_suggestions
          const visualizationData = metadata?._pending_viz_data || {}
          // const suggestedQuestions = metadata?.suggested_next_questions || metadata?.suggested_questions || []
          const followupSuggestions = metadata?.followup_suggestions || []
          const pendingVizData = metadata._pending_viz_data || {};
          const chartData = metadata.chart;
          
          // **KEY FIX: Get suggestions from _pending_viz_data.suggestions**
          // let chartSuggestions = metadata.chart_suggestions || [];
          // if (!chartSuggestions.length && pendingVizData.suggestions) {
          //   chartSuggestions = pendingVizData.suggestions;
          // }
          const suggestionsContainer = pendingVizData.suggestions || {};
          const chartSuggestions = suggestionsContainer.suggestions || [];
          const dataInsights = 
            pendingVizData.suggestions?.metadata?.data_insights ||
            metadata.data_insights || 
            "";
          const isDirectChartGeneration = metadata?.is_direct_generation || false
          const suggestedQuestions = 
            metadata.suggested_next_questions || 
            metadata.suggested_questions || 
            pendingVizData.suggested_questions ||
            [];

          return {
            id: msg.id,
            content: msg.content,
            sender: msg.role === "user" ? "user" : "ai",
            timestamp: new Date(msg.created_at),
            sqlQuery: msg.sql_query,
            queryResult: queryResult,
            intent: msg.intent,
            tables_used: msg.tables_used,
            suggestion: suggestedQuestions,
            business_rules_applied: msg.business_rules_applied,
            reference_context: msg.reference_context,
            sample_data:
              queryResult?.sample_data || queryResult?.data || msg.sample_data,
            total_rows:
              queryResult?.rows_count ||
              queryResult?.row_count ||
              msg.rows_count,
            retrieval_stats: msg.retrieval_stats,
            context_sources: msg.context_sources,
            chart: chartData ? chartData : undefined,
            chart_suggestions: chartSuggestions || [],
            data_insights: dataInsights || visualizationData?.metadata?.data_insights || metadata?.data_insights || "",
            requires_chart_selection: !!chartSuggestions?.length || !!pendingVizData.suggestions?.length,
            direct_chart_generation: isDirectChartGeneration,
            followup_suggestions:followupSuggestions
          };
        });
        setMessages(formattedMessages);
      }
    } catch (error) {
      console.error("Error loading conversation messages:", error);
    }
  };

  // useEffect(() => {
  //   if (isEmbeddingProcessing && messages.length > 0 && selectedProject) {
  //     // Add a processing notification message
  //     const processingMessage: Message = {
  //       id: `processing-${Date.now()}`,
  //       content: "📋 I notice new documents are being processed. My responses will improve as the embeddings are created. Feel free to continue asking questions!",
  //       sender: "ai",
  //       timestamp: new Date(),
  //       intent: "processing_notification"
  //     }

  //     setMessages(prev => {
  //       // Don't add duplicate processing messages
  //       const hasProcessingMessage = prev.some(msg => msg.intent === "processing_notification")
  //       if (!hasProcessingMessage) {
  //         return [...prev, processingMessage]
  //       }
  //       return prev
  //     })
  //   }
  // }, [isEmbeddingProcessing, selectedProject])

  const handleCopy = useCallback((content: string) => {
    navigator.clipboard.writeText(content);
    toast({
      title: "Copied!",
      description: "Message copied to clipboard",
      duration: 2000,
    });
  }, []);

  const handleFeedback = useCallback(
    (messageId: string, type: "up" | "down") => {
      toast({
        title: "Feedback received",
        description: `Thank you for your ${type === "up" ? "positive" : "negative"
          } feedback!`,
        duration: 2000,
      });
    },
    []
  );

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim() || !selectedProject || isTyping) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      content: message.trim(),
      sender: "user",
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setMessage("");
    setIsTyping(true);
    setError(null);
    // **NEW: Add processing warning for better user experience**
    if (isEmbeddingProcessing) {
      console.warn(
        "Sending query while embeddings are processing - responses may be limited"
      );
    }
    try {
      const token = localStorage.getItem("access_token");

      if (!token) {
        throw new Error("No authentication token found. Please log in again.");
      }

      const response = await fetch(`${API_BASE_URL}/chat/query`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: userMessage.content,
          project_id: selectedProject.id,
          conversation_id: currentConversationId,
        }),
      });

      if (!response.ok) {
        if (response.status === 401) {
          throw new Error("Authentication expired. Please log in again.");
        }
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Server error: ${response.status}`);
      }

      const data: SQLChatResponse = await response.json();

      // **ENHANCED: AI Response with processing context**
      let finalAnswer = data.final_answer;
      if (isEmbeddingProcessing && !data.final_answer.includes("processing")) {
        finalAnswer +=
          "\n\n💡 *Note: Document processing is still in progress. My response may improve once all embeddings are ready.*";
      }

      // **ENHANCED: AI Response with new fields**
      const aiResponse: Message = {
        id: (Date.now() + 1).toString(),
        content: data.final_answer,
        sender: "ai",
        timestamp: new Date(),
        relatedDocuments: data.tables_used || [],
        sql_query: data.sql_query,
        query_result: data.query_result,
        intent: data.intent,
        confidence: data.confidence,
        tables_used: data.tables_used,
        suggestion: data.suggestion,
        business_rules_applied: data.business_rules_applied, // New
        reference_context: data.reference_context, // New
        sample_data: data.sample_data,
        total_rows: data.total_rows,
        retrieval_stats: data.retrieval_stats, // New
        context_sources: data.context_sources, // New
        po_workflow: data.po_workflow,
        // po_suggestion: data.po_suggestion,
        po_workflow_started: data.po_workflow_started,
        chart: data.chart,
        chart_suggestions: data.chart_suggestions || [],
        data_insights: data.data_insights || "",
        requires_chart_selection: data.requires_chart_selection || false,
        followup_suggestions: data.chart?.followup_suggestions || []
      };

      setMessages((prev) => [...prev, aiResponse]);
    } catch (error: any) {
      console.error("Error calling SQL chat API:", error);
      setError(error.message);

      let errorContent = `I'm sorry, I encountered an error: ${error.message}`;
      if (isEmbeddingProcessing) {
        errorContent +=
          "\n\nThis might be related to ongoing document processing. Please try again in a moment.";
      }

      const errorResponse: Message = {
        id: (Date.now() + 1).toString(),
        content: errorContent,
        sender: "ai",
        timestamp: new Date(),
        intent: "error",
      };
      setMessages((prev) => [...prev, errorResponse]);
    } finally {
      setIsTyping(false);
      inputRef.current?.focus();
    }
  };

  // Handle Enter key for sending messages
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(e as any);
    }
  };

  const handleSuggestionClick = (suggestion: string) => {
      setMessage(suggestion)
      setTimeout(() => {
        handleSendMessage({ preventDefault: () => {} } as any)
      }, 100)
    }

    const handleChartSelect = (chartType: string) => {
      setMessage(`Use the ${chartType} chart`)
      setTimeout(() => {
        handleSendMessage({ preventDefault: () => {} } as any)
      }, 100)
    }

    const handleFollowupClick = (suggestion: FollowUpSuggestion) => {
      setMessage(suggestion.action.query_modification)
      setTimeout(() => {
        handleSendMessage({ preventDefault: () => {} } as any)
      }, 100)
    }

  if (!selectedProject) {
    return (
      <div className="flex-1 flex items-center justify-center bg-background">
        <div className="text-center py-8 px-4">
          <Bot className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-foreground mb-2">
            Welcome to Supply Chain Intelligence Assistant
          </h2>
          <p className="text-sm text-muted-foreground mb-4">
            Select a project from the sidebar to begin querying your database.
          </p>
          <div className="flex items-center justify-center gap-4 text-xs text-muted-foreground">
            <div className="flex items-center gap-1">
              <Database className="h-4 w-4" />
              <span>Schema</span>
            </div>
            <div className="flex items-center gap-1">
              <Building2 className="h-4 w-4" />
              <span>Rules</span>
            </div>
            <div className="flex items-center gap-1">
              <BookOpen className="h-4 w-4" />
              <span>Docs</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-background">
      {/* **NEW: Embedding Processing Banner** */}
      {/* {isEmbeddingProcessing && <EmbeddingProcessingBanner />} */}

      {/* ADD: Conversation Selector */}
      {/* {selectedProject && (
        <ConversationSelector 
          conversations={conversations}
          currentConversationId={currentConversationId}
          onConversationChange={onConversationChange}
          onNewConversation={onNewConversation}
        />
      )} */}

      {/* Error Banner */}
      {error && (
        <Alert variant="destructive" className="mx-3 mt-3 flex-shrink-0">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="text-sm">{error}</AlertDescription>
        </Alert>
      )}

      {/* Messages Area - Responsive with proper scrolling */}
      <div
        className="flex-1 overflow-y-auto px-3 py-4 min-h-0"
        ref={messagesEndRef}
      >
        <div className="max-w-4xl mx-auto space-y-4">
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              conversation_id={currentConversationId}
              onCopy={handleCopy}
              onFeedback={handleFeedback}
              onSuggestionClick={handleSuggestionClick}
              onChartSelect={handleChartSelect}
              onFollowupClick={handleFollowupClick}
            />
          ))}

          {isTyping && (
            <div className="flex gap-2 justify-start">
              <Avatar className="h-6 w-6 flex-shrink-0 mt-1">
                <AvatarFallback className="bg-primary text-primary-foreground text-xs">
                  <Bot className="h-3 w-3" />
                </AvatarFallback>
              </Avatar>
              <Card className="bg-card border-border shadow-sm">
                <CardContent className="p-3">
                  <div className="flex items-center gap-2">
                    <div className="flex space-x-1">
                      <span className="h-2 w-2 rounded-full bg-primary animate-bounce [animation-delay:-0.3s]"></span>
                      <span className="h-2 w-2 rounded-full bg-primary animate-bounce [animation-delay:-0.15s]"></span>
                      <span className="h-2 w-2 rounded-full bg-primary animate-bounce"></span>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {isEmbeddingProcessing
                        ? "Answering (limited by processing)..."
                        : "Answering..."}
                    </span>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </div>

      <Separator className="flex-shrink-0" />

      {/* Input Area - Responsive */}
      <div className="p-3 flex-shrink-0 bg-background border-t">
        <form onSubmit={handleSendMessage} className="max-w-4xl mx-auto">
          <div className="flex items-center gap-2">
            <Input
              ref={inputRef}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder={
                isEmbeddingProcessing
                  ? `Embeddings processing... Ask about "${selectedProject.name}" (limited responses)`
                  : `Ask anything about "${selectedProject.name}"`
              }
              className={`flex-1 text-sm h-15 rounded-4xl xl:h-20 placeholder:text-gray-400 
    focus:placeholder:text-transparent  ${isEmbeddingProcessing ? "border-amber-300 bg-amber-50/30" : ""
                }`}
              disabled={isTyping}
              autoComplete="off"
            />
            <Button
              type="submit"
              size="sm"
              disabled={!message.trim() || isTyping}
              className={`px-3 bg-secondary ${isEmbeddingProcessing ? "bg-amber-600 hover:bg-amber-700" : ""
                }`}
              variant={isEmbeddingProcessing ? "secondary" : "default"}
            >
              {isTyping ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : isEmbeddingProcessing ? (
                <Clock className="h-4 w-4" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
          <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              {/* <span>Project: {selectedProject.name}</span> */}
              {isEmbeddingProcessing && (
                <Badge
                  variant="secondary"
                  className="bg-amber-100 text-amber-700 text-xs py-0"
                >
                  <Loader2 className="h-2 w-2 mr-1 animate-spin" />
                  Processing
                </Badge>
              )}
            </div>
            <span className="hidden sm:inline">
              {isEmbeddingProcessing
                ? "Limited responses during processing • Press Enter to send"
                : "Enhanced with schema, rules & docs • Try 'generate PO for today' • Press Enter to send"}
            </span>
          </div>

          {/* **NEW: Processing warning message** */}
          {isEmbeddingProcessing && (
            <div className="mt-2 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800">
              <div className="flex items-center gap-1">
                <Info className="h-3 w-3" />
                <span className="font-medium">Processing in progress:</span>
              </div>
              <span>
                Document embeddings are being created. Chat responses may be
                limited until completion.
              </span>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
