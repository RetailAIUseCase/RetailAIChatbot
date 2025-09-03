"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Download, FileText, CalendarIcon, Filter, Search, Trash2, Eye } from "lucide-react"
import { format } from "date-fns"

interface GeneratedDocument {
  id: string
  name: string
  type: "analysis" | "summary" | "report" | "insights"
  projectId: string
  projectName: string
  generatedAt: Date
  size: string
  status: "ready" | "generating" | "failed"
  description?: string
}

interface Project {
  id: string
  name: string
}

interface DownloadManagementProps {
  selectedProject: Project | null
  projects: Project[]
}

const documentTypeConfig = {
  analysis: { label: "Analysis Report", color: "bg-blue-500" },
  summary: { label: "Summary Document", color: "bg-green-500" },
  report: { label: "Detailed Report", color: "bg-purple-500" },
  insights: { label: "AI Insights", color: "bg-orange-500" },
}

export function DownloadManagement({ selectedProject, projects }: DownloadManagementProps) {
  const [documents, setDocuments] = useState<GeneratedDocument[]>([
    {
      id: "1",
      name: "Q4 Financial Analysis",
      type: "analysis",
      projectId: "1",
      projectName: "Project Alpha",
      generatedAt: new Date(),
      size: "2.4 MB",
      status: "ready",
      description: "Comprehensive analysis of Q4 financial data with trends and insights",
    },
    {
      id: "2",
      name: "Data Validation Summary",
      type: "summary",
      projectId: "1",
      projectName: "Project Alpha",
      generatedAt: new Date(Date.now() - 86400000), // Yesterday
      size: "1.8 MB",
      status: "ready",
      description: "Summary of data validation results and quality metrics",
    },
    {
      id: "3",
      name: "Market Research Insights",
      type: "insights",
      projectId: "2",
      projectName: "Beta Analysis",
      generatedAt: new Date(Date.now() - 172800000), // 2 days ago
      size: "3.1 MB",
      status: "ready",
      description: "AI-generated insights from market research data",
    },
    {
      id: "4",
      name: "Processing Report",
      type: "report",
      projectId: "1",
      projectName: "Project Alpha",
      generatedAt: new Date(),
      size: "0.5 MB",
      status: "generating",
      description: "Detailed processing report with methodology and results",
    },
  ])

  const [filteredDocuments, setFilteredDocuments] = useState<GeneratedDocument[]>(documents)
  const [searchQuery, setSearchQuery] = useState("")
  const [dateFilter, setDateFilter] = useState<string>("all")
  const [typeFilter, setTypeFilter] = useState<string>("all")
  const [projectFilter, setProjectFilter] = useState<string>("all")
  const [customDateRange, setCustomDateRange] = useState<{
    from: Date | undefined
    to: Date | undefined
  }>({ from: undefined, to: undefined })
  const [isCustomDateOpen, setIsCustomDateOpen] = useState(false)
  const [previewDocument, setPreviewDocument] = useState<GeneratedDocument | null>(null)

  useEffect(() => {
    let filtered = documents

    // Filter by selected project if any
    if (selectedProject) {
      filtered = filtered.filter((doc) => doc.projectId === selectedProject.id)
    } else if (projectFilter !== "all") {
      filtered = filtered.filter((doc) => doc.projectId === projectFilter)
    }

    // Filter by search query
    if (searchQuery) {
      filtered = filtered.filter(
        (doc) =>
          doc.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          doc.description?.toLowerCase().includes(searchQuery.toLowerCase()),
      )
    }

    // Filter by document type
    if (typeFilter !== "all") {
      filtered = filtered.filter((doc) => doc.type === typeFilter)
    }

    // Filter by date
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const yesterday = new Date(today.getTime() - 86400000)
    const weekAgo = new Date(today.getTime() - 7 * 86400000)
    const monthAgo = new Date(today.getTime() - 30 * 86400000)

    switch (dateFilter) {
      case "today":
        filtered = filtered.filter((doc) => doc.generatedAt >= today)
        break
      case "yesterday":
        filtered = filtered.filter((doc) => doc.generatedAt >= yesterday && doc.generatedAt < today)
        break
      case "week":
        filtered = filtered.filter((doc) => doc.generatedAt >= weekAgo)
        break
      case "month":
        filtered = filtered.filter((doc) => doc.generatedAt >= monthAgo)
        break
      case "custom":
        if (customDateRange.from && customDateRange.to) {
          filtered = filtered.filter(
            (doc) => doc.generatedAt >= customDateRange.from! && doc.generatedAt <= customDateRange.to!,
          )
        }
        break
    }

    // Sort by date (newest first)
    filtered.sort((a, b) => b.generatedAt.getTime() - a.generatedAt.getTime())

    setFilteredDocuments(filtered)
  }, [documents, selectedProject, searchQuery, dateFilter, typeFilter, projectFilter, customDateRange])

  const handleDownload = (document: GeneratedDocument) => {
    // Simulate download
    console.log(`Downloading: ${document.name}`)

    // Create a blob URL for demonstration
    const blob = new Blob(
      [
        `Generated document: ${document.name}\n\nProject: ${document.projectName}\nGenerated: ${document.generatedAt.toLocaleString()}\n\n${document.description || "No description available."}`,
      ],
      {
        type: "text/plain",
      },
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${document.name.replace(/\s+/g, "_")}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const handleDelete = (documentId: string) => {
    setDocuments((prev) => prev.filter((doc) => doc.id !== documentId))
  }

  const generateNewDocument = (type: "analysis" | "summary" | "report" | "insights") => {
    if (!selectedProject) return

    const newDoc: GeneratedDocument = {
      id: Date.now().toString(),
      name: `${documentTypeConfig[type].label} - ${selectedProject.name}`,
      type,
      projectId: selectedProject.id,
      projectName: selectedProject.name,
      generatedAt: new Date(),
      size: "0 MB",
      status: "generating",
      description: `AI-generated ${type} for ${selectedProject.name}`,
    }

    setDocuments((prev) => [newDoc, ...prev])

    // Simulate generation process
    setTimeout(() => {
      setDocuments((prev) =>
        prev.map((doc) =>
          doc.id === newDoc.id
            ? { ...doc, status: "ready" as const, size: `${(Math.random() * 3 + 0.5).toFixed(1)} MB` }
            : doc,
        ),
      )
    }, 3000)
  }

  const formatDate = (date: Date) => {
    const now = new Date()
    const diffTime = now.getTime() - date.getTime()
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24))

    if (diffDays === 0) return "Today"
    if (diffDays === 1) return "Yesterday"
    if (diffDays < 7) return `${diffDays} days ago`
    return format(date, "MMM dd, yyyy")
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-medium text-foreground">Generated Documents</h3>
          <Badge variant="secondary" className="text-xs">
            {filteredDocuments.length} documents
          </Badge>
        </div>

        {/* Generate New Document */}
        {selectedProject && (
          <div className="space-y-2">
            <Label className="text-xs text-muted-foreground">Generate New</Label>
            <div className="grid grid-cols-2 gap-1">
              <Button
                size="sm"
                variant="outline"
                className="text-xs h-7 bg-transparent"
                onClick={() => generateNewDocument("analysis")}
              >
                Analysis
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="text-xs h-7 bg-transparent"
                onClick={() => generateNewDocument("summary")}
              >
                Summary
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="text-xs h-7 bg-transparent"
                onClick={() => generateNewDocument("report")}
              >
                Report
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="text-xs h-7 bg-transparent"
                onClick={() => generateNewDocument("insights")}
              >
                Insights
              </Button>
            </div>
          </div>
        )}
      </div>

      {!selectedProject ? (
        <div className="flex-1 flex items-center justify-center p-4">
          <div className="text-center">
            <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">Select a project to view generated documents</p>
            <p className="text-xs text-muted-foreground mt-1">Choose a project from the sidebar to get started</p>
          </div>
        </div>
      ) : (
        <>
          {/* Filters */}
          <div className="p-4 border-b border-border space-y-3">
            {/* Search */}
            <div className="relative">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search documents..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 h-9"
              />
            </div>

            {/* Filters */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Filter className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Filters</span>
              </div>

              <div className="space-y-2">
                <Select value={dateFilter} onValueChange={setDateFilter}>
                  <SelectTrigger className="h-8">
                    <SelectValue placeholder="Date range" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All dates</SelectItem>
                    <SelectItem value="today">Today</SelectItem>
                    <SelectItem value="yesterday">Yesterday</SelectItem>
                    <SelectItem value="week">This week</SelectItem>
                    <SelectItem value="month">This month</SelectItem>
                    <SelectItem value="custom">Custom range</SelectItem>
                  </SelectContent>
                </Select>

                {dateFilter === "custom" && (
                  <Popover open={isCustomDateOpen} onOpenChange={setIsCustomDateOpen}>
                    <PopoverTrigger asChild>
                      <Button variant="outline" className="h-8 text-xs bg-transparent">
                        <CalendarIcon className="mr-2 h-3 w-3" />
                        {customDateRange.from ? (
                          customDateRange.to ? (
                            <>
                              {format(customDateRange.from, "LLL dd")} - {format(customDateRange.to, "LLL dd")}
                            </>
                          ) : (
                            format(customDateRange.from, "LLL dd, y")
                          )
                        ) : (
                          "Pick dates"
                        )}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar
                        initialFocus
                        mode="range"
                        defaultMonth={customDateRange.from}
                        selected={{
                          from: customDateRange.from,
                          to: customDateRange.to,
                        }}
                        onSelect={(range) => {
                          setCustomDateRange({
                            from: range?.from,
                            to: range?.to,
                          })
                        }}
                        numberOfMonths={1}
                      />
                    </PopoverContent>
                  </Popover>
                )}

                <Select value={typeFilter} onValueChange={setTypeFilter}>
                  <SelectTrigger className="h-8">
                    <SelectValue placeholder="Document type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All types</SelectItem>
                    <SelectItem value="analysis">Analysis Reports</SelectItem>
                    <SelectItem value="summary">Summaries</SelectItem>
                    <SelectItem value="report">Detailed Reports</SelectItem>
                    <SelectItem value="insights">AI Insights</SelectItem>
                  </SelectContent>
                </Select>

                {!selectedProject && (
                  <Select value={projectFilter} onValueChange={setProjectFilter}>
                    <SelectTrigger className="h-8">
                      <SelectValue placeholder="Project" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All projects</SelectItem>
                      {projects.map((project) => (
                        <SelectItem key={project.id} value={project.id}>
                          {project.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>
          </div>

          {/* Documents List */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {filteredDocuments.length === 0 ? (
              <div className="text-center py-8">
                <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
                <p className="text-sm text-muted-foreground">No documents found</p>
                {selectedProject && (
                  <p className="text-xs text-muted-foreground mt-1">
                    Generate your first document using the buttons above
                  </p>
                )}
              </div>
            ) : (
              filteredDocuments.map((doc) => (
                <Card key={doc.id} className="p-3">
                  <div className="space-y-2">
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <div className={`w-2 h-2 rounded-full ${documentTypeConfig[doc.type].color}`} />
                          <h5 className="font-medium text-sm truncate">{doc.name}</h5>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {doc.projectName} • {formatDate(doc.generatedAt)} • {doc.size}
                        </p>
                        {doc.description && (
                          <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{doc.description}</p>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center justify-between">
                      <Badge
                        variant={
                          doc.status === "ready" ? "default" : doc.status === "generating" ? "secondary" : "destructive"
                        }
                        className="text-xs"
                      >
                        {doc.status === "ready" && "Ready"}
                        {doc.status === "generating" && "Generating..."}
                        {doc.status === "failed" && "Failed"}
                      </Badge>

                      <div className="flex items-center gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-6 w-6 p-0"
                          onClick={() => setPreviewDocument(doc)}
                          disabled={doc.status !== "ready"}
                        >
                          <Eye className="h-3 w-3" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-6 w-6 p-0"
                          onClick={() => handleDownload(doc)}
                          disabled={doc.status !== "ready"}
                        >
                          <Download className="h-3 w-3" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-6 w-6 p-0 text-destructive hover:text-destructive"
                          onClick={() => handleDelete(doc.id)}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  </div>
                </Card>
              ))
            )}
          </div>
        </>
      )}

      {/* Preview Dialog */}
      <Dialog open={!!previewDocument} onOpenChange={() => setPreviewDocument(null)}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <div
                className={`w-3 h-3 rounded-full ${previewDocument ? documentTypeConfig[previewDocument.type].color : ""}`}
              />
              {previewDocument?.name}
            </DialogTitle>
            <DialogDescription>
              {previewDocument?.projectName} • Generated{" "}
              {previewDocument ? formatDate(previewDocument.generatedAt) : ""}
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <div className="bg-muted p-4 rounded-lg">
              <p className="text-sm">{previewDocument?.description || "No preview available for this document."}</p>
              <div className="mt-4 p-3 bg-background rounded border text-xs text-muted-foreground">
                This is a preview of the generated document. The actual file contains comprehensive analysis and
                detailed insights based on your uploaded documents.
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPreviewDocument(null)}>
              Close
            </Button>
            {previewDocument && (
              <Button onClick={() => handleDownload(previewDocument)}>
                <Download className="h-4 w-4 mr-2" />
                Download
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
