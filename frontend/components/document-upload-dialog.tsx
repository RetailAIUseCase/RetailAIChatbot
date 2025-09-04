"use client"

import type React from "react"
import { useState, useCallback } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { Upload, X, FileText, CheckCircle, AlertCircle, Database, BookOpen } from "lucide-react"

interface UploadFile {
  id: string
  file: File
  progress: number
  status: "uploading" | "completed" | "error"
  error?: string
}

interface DocumentUploadDialogProps {
  isOpen: boolean
  onClose: () => void
  documentType: "metadata" | "businesslogic" | "references"
  projectId: string
  projectName: string
  onUploadComplete: (files: UploadFile[]) => void
}

const documentTypeConfig = {
  metadata: {
    title: "Upload Metadata Documents",
    description: "Upload metadata files that describe your data schema and properties.",
    icon: Database,
    acceptedTypes: ".json,.doc,.docx,.txt",
    color: "text-primary",
  },
  businesslogic: {
    title: "Upload Business Logic Documents", 
    description: "Upload business logic documents for application workflows and rules.",
    icon: FileText,
    acceptedTypes: ".pdf,.doc,.docx,.txt,.csv",
    color: "text-accent",
  },
  references: {
    title: "Upload Reference Documents",
    description: "Upload reference materials and supporting documentation.",
    icon: BookOpen,
    acceptedTypes: ".pdf,.doc,.docx,.txt,.md,.html",
    color: "text-chart-3",
  },
}

export function DocumentUploadDialog({
  isOpen,
  onClose,
  documentType,
  projectId,
  projectName,
  onUploadComplete,
}: DocumentUploadDialogProps) {
  const [uploadFiles, setUploadFiles] = useState<UploadFile[]>([])
  const [isDragOver, setIsDragOver] = useState(false)
  const [isUploading, setIsUploading] = useState(false)

  const config = documentTypeConfig[documentType]
  const IconComponent = config.icon

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragOver(false)

    const files = Array.from(e.dataTransfer.files)
    handleFiles(files)
  }, [])

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    handleFiles(files)
  }, [])

  const handleFiles = (files: File[]) => {
    const newUploadFiles: UploadFile[] = files.map((file) => ({
      id: `${Date.now()}-${Math.random()}`,
      file,
      progress: 0,
      status: "uploading" as const,
    }))

    setUploadFiles((prev) => [...prev, ...newUploadFiles])
  }

  const removeFile = (fileId: string) => {
    setUploadFiles((prev) => prev.filter((file) => file.id !== fileId))
  }
  
  const handleUpload = async () => {
    if (uploadFiles.length === 0) return

    setIsUploading(true)

    try {
      const formData = new FormData()
      formData.append('project_id', projectId)
      formData.append('document_type', documentType)
      
      // Append each file individually
      uploadFiles.forEach((uploadFile, index) => {
        formData.append(`files`, uploadFile.file) // Backend expects 'files' field
      })

      const token = localStorage.getItem('access_token')
      const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "https://retail-ai-chatbot.onrender.com"
      // **FIXED: Proper API URL and headers**
      const response = await fetch(`${API_BASE_URL}/documents/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Accept': 'application/json'
          // **CRITICAL: Don't set Content-Type with FormData**
        },
        body: formData
      })

      // **FIXED: Proper response handling**
      const contentType = response.headers.get('content-type') || ''
      
      if (contentType.includes('application/json')) {
        const data = await response.json()
        
        if (!response.ok) {
          throw new Error(data.detail || `Upload failed: ${response.status}`)
        }

        // **FIXED: Update file statuses to completed**
        setUploadFiles((prev) =>
          prev.map((file) => ({
            ...file,
            status: "completed" as const,
            progress: 100,
          }))
        )

        // Call completion callback
        const completedFiles = uploadFiles.map(file => ({
          ...file,
          status: "completed" as const,
          progress: 100,
        }))
        
        onUploadComplete(completedFiles)
        
        // Show success message based on actual response
        if (data.failed_count && data.failed_count > 0) {
          alert(`Upload completed: ${data.success_count} successful, ${data.failed_count} failed`)
        }

        return data
        
      } else {
        // Server returned HTML (likely an error page)
        const htmlText = await response.text()
        console.error('Server returned HTML instead of JSON:', htmlText)
        throw new Error(`Server error: Expected JSON but received HTML (Status: ${response.status})`)
      }
      
    } catch (error) {
      console.error('Upload error:', error)
      
      // Update file statuses to error
      setUploadFiles((prev) =>
        prev.map((file) => ({
          ...file,
          status: "error" as const,
          error: error instanceof Error ? error.message : 'Upload failed',
        }))
      )

      // Show error to user
      alert(error instanceof Error ? error.message : 'Upload failed')
      
    } finally {
      setIsUploading(false)
    }
  }

  const handleComplete = () => {
    const completedFiles = uploadFiles.filter((file) => file.status === "completed")
    onUploadComplete(completedFiles)
    setUploadFiles([])
    onClose()
  }

  const completedCount = uploadFiles.filter((file) => file.status === "completed").length
  const errorCount = uploadFiles.filter((file) => file.status === "error").length
  const uploadingCount = uploadFiles.filter((file) => file.status === "uploading").length

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[600px] max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <IconComponent className={`h-5 w-5 ${config.color}`} />
            {config.title}
          </DialogTitle>
          <DialogDescription>
            {config.description} Project: <strong>{projectName}</strong>
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 space-y-4 overflow-y-auto">
          {/* Upload Area */}
          <div
            className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
              isDragOver ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"
            }`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <Upload className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-medium mb-2">Drop files here or click to browse</h3>
            <p className="text-sm text-muted-foreground mb-4">Accepted formats: {config.acceptedTypes}</p>
            <input
              type="file"
              multiple
              accept={config.acceptedTypes}
              onChange={handleFileSelect}
              className="hidden"
              id="file-upload"
            />
            <Button asChild variant="outline">
              <label htmlFor="file-upload" className="cursor-pointer">
                Select Files
              </label>
            </Button>
          </div>

          {/* Upload Progress */}
          {uploadFiles.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="font-medium">Upload Progress</h4>
                <div className="flex gap-2">
                  {completedCount > 0 && (
                    <Badge variant="default" className="text-xs">
                      <CheckCircle className="h-3 w-3 mr-1" />
                      {completedCount} completed
                    </Badge>
                  )}
                  {errorCount > 0 && (
                    <Badge variant="destructive" className="text-xs">
                      <AlertCircle className="h-3 w-3 mr-1" />
                      {errorCount} failed
                    </Badge>
                  )}
                  {uploadingCount > 0 && (
                    <Badge variant="secondary" className="text-xs">
                      {uploadingCount} uploading
                    </Badge>
                  )}
                </div>
              </div>

              <div className="space-y-2 max-h-60 overflow-y-auto">
                {uploadFiles.map((uploadFile) => (
                  <Card key={uploadFile.id} className="p-3">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2 flex-1 min-w-0">
                        <div className="flex-shrink-0">
                          {uploadFile.status === "completed" && <CheckCircle className="h-4 w-4 text-green-500" />}
                          {uploadFile.status === "error" && <AlertCircle className="h-4 w-4 text-destructive" />}
                          {uploadFile.status === "uploading" && (
                            <div className="h-4 w-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{uploadFile.file.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {(uploadFile.file.size / 1024 / 1024).toFixed(2)} MB
                          </p>
                        </div>
                      </div>
                      <Button 
                        size="sm" 
                        variant="ghost" 
                        onClick={() => removeFile(uploadFile.id)} 
                        disabled={isUploading}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>

                    {uploadFile.status === "uploading" && <Progress value={uploadFile.progress} className="h-2" />}

                    {uploadFile.error && <p className="text-xs text-destructive mt-1">{uploadFile.error}</p>}
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isUploading}>
            Cancel
          </Button>
          {uploadFiles.length > 0 && completedCount === 0 && (
            <Button onClick={handleUpload} disabled={isUploading || uploadFiles.length === 0}>
              {isUploading ? (
                <>
                  <Upload className="h-4 w-4 mr-2 animate-spin" />
                  Uploading...
                </>
              ) : (
                `Upload ${uploadFiles.length} files`
              )}
            </Button>
          )}
          {completedCount > 0 && (
            <Button onClick={handleComplete}>
              Complete Upload ({completedCount} files)
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
