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
} from "lucide-react";
import { toast } from "@/components/ui/use-toast";

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
}

interface Message {
  id: string;
  content: string;
  sender: "user" | "ai";
  timestamp: Date;
  relatedDocuments?: string[];
  sqlQuery?: string;
  queryResult?: SQLChatResponse["query_result"];
  intent?: string;
  confidence?: number;
  tables_used?: string[];
  suggestion?: string[]; 
  business_rules_applied?: string[]; // New field
  reference_context?: string[]; // New field
  sample_data?: Array<Record<string, any>>;
  total_rows?: number;
  retrieval_stats?: SQLChatResponse["retrieval_stats"]; // New field
  context_sources?: string[]; // New field
  po_workflow?: SQLChatResponse["po_workflow"];
  // po_suggestion?: SQLChatResponse["po_suggestion"];
  po_workflow_started?: boolean;
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

// Add props for processing state
interface ChatInterfaceProps {
  selectedProject: Project | null;
  isEmbeddingProcessing?: boolean;
  conversations: Conversation[];
  currentConversationId: string | null;
  onConversationChange: (conversationId: string | null) => void;
  onNewConversation: () => void;
}
// **NEW: Context Sources Display Component**
// const ContextSourcesDisplay = ({
//   context_sources,
//   retrieval_stats
// }: {
//   context_sources?: string[]
//   retrieval_stats?: SQLChatResponse['retrieval_stats']
// }) => {
//   if (!context_sources || context_sources.length === 0) return null

//   const getSourceIcon = (source: string) => {
//     switch (source) {
//       case 'database_schema':
//         return <Database className="h-3 w-3" />
//       case 'business_rules':
//         return <Building2 className="h-3 w-3" />
//       case 'documentation':
//         return <BookOpen className="h-3 w-3" />
//       default:
//         return <Info className="h-3 w-3" />
//     }
//   }

//   const getSourceLabel = (source: string) => {
//     switch (source) {
//       case 'database_schema':
//         return 'Schema'
//       case 'business_rules':
//         return 'Rules'
//       case 'documentation':
//         return 'Docs'
//       default:
//         return source
//     }
//   }

//   const getSourceCount = (source: string) => {
//     if (!retrieval_stats) return null
//     switch (source) {
//       case 'database_schema':
//         return retrieval_stats.metadata_results
//       case 'business_rules':
//         return retrieval_stats.business_logic_results
//       case 'documentation':
//         return retrieval_stats.reference_results
//       default:
//         return null
//     }
//   }

//   return (
//     <div className="flex items-center gap-1 flex-wrap">
//       <Activity className="h-3 w-3 text-primary" />
//       <span className="text-xs text-muted-foreground">Sources:</span>
//       {context_sources.map((source, index) => {
//         const count = getSourceCount(source)
//         return (
//           <Badge key={index} variant="outline" className="text-xs py-0 px-1 h-4 flex items-center gap-1">
//             {getSourceIcon(source)}
//             <span>{getSourceLabel(source)}</span>
//             {count !== null && <span className="text-muted-foreground">({count})</span>}
//           </Badge>
//         )
//       })}
//     </div>
//   )
// }

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

// Auto-scroll Hook (unchanged)
const useChatScroll = (dep: any) => {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight;
    }
  }, [dep]);

  return ref;
};

// Utility functions (unchanged)
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
  onCopy,
  onFeedback,
}: {
  message: Message;
  onCopy: (content: string) => void;
  onFeedback: (messageId: string, type: "up" | "down") => void;
}) => {
  const formatTimestamp = (timestamp: Date) => {
    return timestamp.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getMessageWidth = (content: string, sender: string) => {
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

  const messageWidthClass = getMessageWidth(message.content, message.sender);
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
          <AvatarFallback className="bg-primary text-primary-foreground text-xs">
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
              ? "bg-primary text-primary-foreground border-primary"
              : "bg-card border-border"
            } shadow-sm overflow-hidden`}
          style={{ maxWidth: "100%" }}
        >
          <CardContent className="px-3 py-2 overflow-hidden">
            <div className="space-y-1 overflow-hidden">
              <p className="text-sm leading-5 whitespace-pre-wrap break-words">
                {message.content}
              </p>
              {message.sender === "ai" && message.suggestion && message.suggestion.length > 0 && (
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
              )}


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
                    sqlQuery={message.sqlQuery}
                    queryResult={message.queryResult}
                    data={message.queryResult?.data}
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
            {message.sender === "ai" && (
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
            )}
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
// Add this component above your ChatInterface component
// const ConversationSelector = ({
//   conversations,
//   currentConversationId,
//   onConversationChange,
//   onNewConversation
// }: {
//   conversations: Conversation[]
//   currentConversationId: string | null
//   onConversationChange: (conversationId: string | null) => void
//   onNewConversation: () => void
// }) => {
//   // Don't show if no conversations exist and no current conversation
//   if (conversations.length === 0 && !currentConversationId) {
//     return null
//   }

//   return (
//     <div className="px-3 py-2 bg-background/95 backdrop-blur border-b">
//       <div className="max-w-4xl mx-auto">
//         <div className="flex items-center gap-2">
//           <DropdownMenu>
//             <DropdownMenuTrigger asChild>
//               <Button variant="outline" size="sm" className="flex-1 justify-start">
//                 <MessageSquare className="h-4 w-4 mr-2" />
//                 {currentConversationId ?
//                   conversations.find(c => c.id === currentConversationId)?.title?.slice(0, 40) + "..." || "Current Chat"
//                   : "New Chat"
//                 }
//                 <ChevronDown className="h-4 w-4 ml-auto" />
//               </Button>
//             </DropdownMenuTrigger>
//             <DropdownMenuContent className="w-80" align="start">
//               <DropdownMenuItem onClick={onNewConversation}>
//                 <Plus className="h-4 w-4 mr-2" />
//                 New Chat
//               </DropdownMenuItem>
//               {conversations.length > 0 && (
//                 <>
//                   <DropdownMenuSeparator />
//                   <div className="max-h-60 overflow-y-auto">
//                     {conversations.map(conv => (
//                       <DropdownMenuItem
//                         key={conv.id}
//                         onClick={() => onConversationChange(conv.id)}
//                         className={currentConversationId === conv.id ? "bg-accent" : ""}
//                       >
//                         <div className="flex flex-col items-start w-full">
//                           <span className="font-medium truncate w-full">
//                             {conv.title || "Untitled Chat"}
//                           </span>
//                           <span className="text-xs text-muted-foreground">
//                             {new Date(conv.updated_at).toLocaleDateString()} • {conv.message_count} messages
//                           </span>
//                         </div>
//                       </DropdownMenuItem>
//                     ))}
//                   </div>
//                 </>
//               )}
//             </DropdownMenuContent>
//           </DropdownMenu>

//           <Button variant="outline" size="sm" onClick={onNewConversation}>
//             <Plus className="h-4 w-4" />
//           </Button>
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

  const API_BASE_URL =
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "https://retail-ai-chatbot.onrender.com";

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
            content: `Hello! I'm your SQL Assistant for "${selectedProject.name}". 
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
                content: `Hello! I'm your SQL Assistant for "${selectedProject.name}". I can help you query your database using schema information, business rules, and documentation. What would you like to know?`,
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
          let suggestion = msg.metadata;
          if (typeof queryResult === "string") {
            try {
              queryResult = JSON.parse(queryResult);
            } catch (e) {
              console.warn("Failed to parse query_result:", e);
              queryResult = null;
            }
          }
          if (typeof suggestion === "string") {
            try {
              suggestion = JSON.parse(suggestion);
            } catch (e) {
              console.warn("Failed to parse suggestion:", e);
              suggestion = null;
            }
          }
          return {
            id: msg.id,
            content: msg.content,
            sender: msg.role === "user" ? "user" : "ai",
            timestamp: new Date(msg.created_at),
            sqlQuery: msg.sql_query,
            queryResult: queryResult,
            intent: msg.intent,
            tables_used: msg.tables_used,
            suggestion: suggestion?.suggested_next_questions,
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
        sqlQuery: data.sql_query,
        queryResult: data.query_result,
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
              onCopy={handleCopy}
              onFeedback={handleFeedback}
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
              className={`px-3 ${isEmbeddingProcessing ? "bg-amber-600 hover:bg-amber-700" : ""
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
