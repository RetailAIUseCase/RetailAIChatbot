"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Card } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { DocumentUploadDialog } from "@/components/document-upload-dialog"
import { ChatInterface } from "@/components/chat-interface"
import { DownloadManagement } from "@/components/download-management"
// Add to your imports in the dashboard
import { EmbeddingStatusBanner } from "@/components/embedding-status-banner"
import {
  Settings,
  User,
  LogOut,
  Plus,
  Download,
  Menu,
  X,
  FolderOpen,
  Upload,
  FileText,
  Database,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Loader2,
  MoreVertical,
  Trash2,
} from "lucide-react"

interface Project {
  id: string
  name: string
  description: string
  created_at: string
  updated_at: string
  documentCounts?: {
    metadata: number
    businesslogic: number
    references: number
  }
  documents?: ProjectDocument[]
}

interface ProjectDocument {
  id: string
  name: string
  type: "metadata" | "businesslogic" | "references"
  uploadedAt: string
  size: string
}

interface UserData {
  id: number
  email: string
  full_name?: string
  is_active: boolean
  created_at: string
  updated_at: string
}
// Add embedding status interface
interface EmbeddingStatus {
  total: number
  processing: number
  completed: number
  failed: number
  pending: number
}
export default function DashboardPage() {
  const router = useRouter()
  // User state
  const [user, setUser] = useState<UserData | null>(null)
  const [isLoadingUser, setIsLoadingUser] = useState(true)

  // UI state
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [rightPanelOpen, setRightPanelOpen] = useState(true)
  const [recentDocsExpanded, setRecentDocsExpanded] = useState(false)
  const [isRefreshingCounts, setIsRefreshingCounts] = useState(false)
  const sidebarRef = useRef<HTMLDivElement>(null)

  // Add processing state
  const [isEmbeddingProcessing, setIsEmbeddingProcessing] = useState(false);
  const [embeddingStatus, setEmbeddingStatus] = useState<EmbeddingStatus | null>(null);

  // API base URL
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  
  // Project State
  const [selectedProject, setSelectedProject] = useState<Project | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [isLoadingProjects, setIsLoadingProjects] = useState(false)
  const [isCreatingProject, setIsCreatingProject] = useState(false)
  const [newProjectName, setNewProjectName] = useState("")
  const [newProjectDescription, setNewProjectDescription] = useState("")
  const [isCreateProjectOpen, setIsCreateProjectOpen] = useState(false)
  
  // Delete project state
  const [deleteDialog, setDeleteDialog] = useState<{
    isOpen: boolean
    project: Project | null
    isDeleting: boolean
  }>({
    isOpen: false,
    project: null,
    isDeleting: false,
  })
  
  // Upload State
  const [uploadDialog, setUploadDialog] = useState<{
    isOpen: boolean
    documentType: "metadata" | "businesslogic" | "references"
  }>({
    isOpen: false,
    documentType: "metadata",
  })

  // Function to fetch document counts efficiently
  const fetchDocumentCounts = async (projectId: string): Promise<{metadata: number; businesslogic: number; references: number}> => {
  try {
    const token = localStorage.getItem('access_token')
    const response = await fetch(`${API_BASE_URL}/documents/project/${projectId}`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/json'
      }
    })

    if (!response.ok) {
      console.error(`Failed to fetch documents for project ${projectId}:`, response.status)
      return { metadata: 0, businesslogic: 0, references: 0 }
    }

    const data = await response.json()
    
    // Now we can get counts directly from the API response
    if (data.counts) {
      return {
        metadata: data.counts.metadata || 0,
        businesslogic: data.counts.businesslogic || 0,
        references: data.counts.references || 0,
      }
    }
    
    // Fallback: count from documents array if counts not available
    const documents = data.documents || []
    const counts = {
      metadata: documents.filter((d: any) => d.document_type === 'metadata').length,
      businesslogic: documents.filter((d: any) => d.document_type === 'businesslogic').length,
      references: documents.filter((d: any) => d.document_type === 'references').length,
    }
    return counts
  } catch (error) {
    console.error(`Error fetching documents for project ${projectId}:`, error)
    return { metadata: 0, businesslogic: 0, references: 0 }
  }
}

  // Helper function to refresh project data
  const refreshProjectData = async (projectId: string) => {
    try {
      const token = localStorage.getItem('access_token')
      const [updatedCounts, documentsResponse] = await Promise.all([
        fetchDocumentCounts(projectId),
        fetch(`${API_BASE_URL}/documents/project/${projectId}`, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Accept': 'application/json'
          }
        })
      ])

      if (documentsResponse.ok) {
        const data = await documentsResponse.json()
        const documents = data.documents || []
        
        const transformedDocs: ProjectDocument[] = documents.map((doc: any) => ({
          id: doc.id,
          name: doc.name,
          type: doc.document_type,
          uploadedAt: doc.created_at,
          size: doc.file_size ? `${(doc.file_size / 1024 / 1024).toFixed(1)} MB` : 'Unknown'
        }))

        return { documents: transformedDocs, counts: updatedCounts }
      }
    } catch (error) {
      console.error('Error refreshing project data:', error)
    }
    return null
  }
  
  // Calculate available height for recent documents
  const calculateRecentDocsHeight = () => {
    if (!sidebarRef.current || !selectedProject) return "120px";
    
    const sidebarHeight = sidebarRef.current.offsetHeight;
    const projectsHeight = document.querySelector('.projects-container')?.clientHeight || 0;
    const uploadSectionHeight = document.querySelector('.upload-section')?.clientHeight || 0;
    
    // Calculate available space (subtract projects and upload section heights plus padding)
    const availableHeight = sidebarHeight - projectsHeight - uploadSectionHeight - 100;
    
    // Return a reasonable max height (between 120px and 280px)
    return `${Math.min(Math.max(availableHeight, 120), 280)}px`;
  };

  const [recentDocsHeight, setRecentDocsHeight] = useState("120px");

  // Update recent docs height when sidebar opens/closes or project changes
  useEffect(() => {
    const updateHeight = () => {
      setRecentDocsHeight(calculateRecentDocsHeight());
    };

    updateHeight();
    window.addEventListener('resize', updateHeight);
    
    return () => {
      window.removeEventListener('resize', updateHeight);
    };
  }, [sidebarOpen, selectedProject]);

  // Helper function to get user initials
  const getUserInitials = (user: any): string => {
    if (!user) return "U"
    
    try {
      if (user.full_name && typeof user.full_name === 'string') {
        const names = String(user.full_name).trim().split(' ')
        if (names.length >= 2) {
          return (names[0][0] + names[1][0]).toUpperCase()
        }
        if (names.length === 1) {
          return names[0][0].toUpperCase()
        }
      }
      
      if (user.email && typeof user.email === 'string') {
        return String(user.email)[0].toUpperCase()
      }
    } catch (error) {
      console.error('Error generating user initials:', error)
    }
    
    return "U"
  }

  // Helper function to get display name
  const getDisplayName = (user: any): string => {
    if (!user) return "Loading..."
    
    try {
      if (user.full_name && String(user.full_name).trim()) {
        return String(user.full_name).trim()
      }
      
      if (user.email) {
        return String(user.email).split('@')[0]
      }
    } catch (error) {
      console.error('Error generating display name:', error)
    }
    
    return "User"
  }

  // Fetch user data on component mount
  useEffect(() => {
    const fetchUserData = async () => {
      try {
        const token = localStorage.getItem('access_token')
        
        if (!token) {
          router.push('/login')
          return
        }

        const response = await fetch(`${API_BASE_URL}/auth/me`, {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        })

        if (response.ok) {
          const userData = await response.json()
          setUser(userData)
        } else if (response.status === 401) {
          localStorage.removeItem('access_token')
          localStorage.removeItem('token_type')
          router.push('/login')
        }
      } catch (error) {
        console.error('Error fetching user data:', error)
      } finally {
        setIsLoadingUser(false)
      }
    }
    fetchUserData()
  }, [router, API_BASE_URL])

  // Fetch projects from API
  useEffect(() => {
    const fetchProjects = async () => {
      if (!user) return
      
      try {
        setIsLoadingProjects(true)
        const token = localStorage.getItem('access_token')
        if (!token) return

        const response = await fetch(`${API_BASE_URL}/projects/`, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        })

        if (response.ok) {
          const projectsData = await response.json()
          // Fetch document counts for each project in parallel
          const projectsWithCounts = await Promise.all(
            projectsData.map(async (project: any) => {
              const documentCounts = await fetchDocumentCounts(project.id)
              
              return {
                id: project.id,
                name: project.name,
                description: project.description,
                created_at: project.created_at,
                updated_at: project.updated_at,
                documentCounts,
                documents: [], // Will be loaded when project is selected
              }
            })
          )
          
          setProjects(projectsWithCounts)
        }
      } catch (error) {
        console.error('Error fetching projects:', error)
      } finally {
        setIsLoadingProjects(false)
      }
    }

    fetchProjects()
  }, [user, API_BASE_URL])

  // Fetch documents when a project is selected
  useEffect(() => {
    const fetchProjectDocuments = async () => {
      if (!selectedProject) return

      try {
        const token = localStorage.getItem('access_token')
        const response = await fetch(`${API_BASE_URL}/documents/project/${selectedProject.id}`, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Accept': 'application/json'
          }
        })

        if (response.ok) {
          const data = await response.json()
          const documents = data.documents || []
          
          // Transform to your document format
          const transformedDocs: ProjectDocument[] = documents.map((doc: any) => ({
            id: doc.id,
            name: doc.name,
            type: doc.document_type,
            uploadedAt: doc.created_at,
            size: doc.file_size ? `${(doc.file_size / 1024 / 1024).toFixed(1)} MB` : 'Unknown'
          }))

          // Update the selected project with documents
          setSelectedProject(prev => prev ? { ...prev, documents: transformedDocs } : null)
          
          // Also update in projects array
          setProjects(prev => 
            prev.map(p => 
              p.id === selectedProject.id 
                ? { ...p, documents: transformedDocs }
                : p
            )
          )
        }
      } catch (error) {
        console.error('Error fetching project documents:', error)
      }
    }

    fetchProjectDocuments()
  }, [selectedProject?.id, API_BASE_URL])

  // Refresh counts when upload dialog closes
  useEffect(() => {
    if (!uploadDialog.isOpen && selectedProject) {
      // Refresh document counts when upload dialog closes
      setIsRefreshingCounts(true)
      fetchDocumentCounts(selectedProject.id).then(counts => {
        setProjects(prev => 
          prev.map(p => 
            p.id === selectedProject.id 
              ? { ...p, documentCounts: counts }
              : p
          )
        )
        setSelectedProject(prev => prev ? { ...prev, documentCounts: counts } : null)
      }).finally(() => {
        setIsRefreshingCounts(false)
      })
    }
  }, [uploadDialog.isOpen, selectedProject?.id])

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return
    try {
      setIsCreatingProject(true)
      const token = localStorage.getItem('access_token')
      const response = await fetch(`${API_BASE_URL}/projects/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: newProjectName,
          description: newProjectDescription,
        }),
      })

      if (response.ok) {
        const newProject = await response.json()
        // Transform to match your interface
        const transformedProject = {
          id: newProject.id,
          name: newProject.name,
          description: newProject.description,
          created_at: newProject.created_at,
          updated_at: newProject.updated_at,
          documentCounts: { metadata: 0, businesslogic: 0, references: 0 },
          documents: [],
        }
        
        setProjects([transformedProject, ...projects])
        setSelectedProject(transformedProject)
        setNewProjectName("")
        setNewProjectDescription("")
        setIsCreateProjectOpen(false)
      } else {
        const error = await response.json()
        alert(`Error: ${error.detail}`)
      }
    } catch (error) {
      console.error('Error creating project:', error)
      alert('Failed to create project')
    } finally {
      setIsCreatingProject(false)
    }
  }

  // Delete project handler
  const handleDeleteProject = async () => {
    if (!deleteDialog.project) return
    
    try {
      setDeleteDialog(prev => ({ ...prev, isDeleting: true }))
      const token = localStorage.getItem('access_token')
      if (!token) return
      
      const response = await fetch(`${API_BASE_URL}/projects/${deleteDialog.project.id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      })
      
      if (response.ok) {
        // Remove from local state
        setProjects(prev => prev.filter(project => project.id !== deleteDialog.project!.id))
        
        // If deleted project was selected, clear selection
        if (selectedProject?.id === deleteDialog.project.id) {
          setSelectedProject(null)
        }
        
        setDeleteDialog({ isOpen: false, project: null, isDeleting: false })
      } else {
        const error = await response.json()
        alert(`Error deleting project: ${error.detail || 'Unknown error'}`)
      }
    } catch (error) {
      console.error('Error deleting project:', error)
      alert('Failed to delete project')
    } finally {
      setDeleteDialog(prev => ({ ...prev, isDeleting: false }))
    }
  }
  
  const handleDocumentUpload = (type: "metadata" | "businesslogic" | "references") => {
    setUploadDialog({
      isOpen: true,
      documentType: type,
    })
  }

  // Updated handleUploadComplete function
  const handleUploadComplete = async (uploadedFiles: any[]) => {
    if (!selectedProject) return

    setIsRefreshingCounts(true)
    
    try {
      // Refresh project data from API
      const refreshedData = await refreshProjectData(selectedProject.id)
      
      if (refreshedData) {
        // Update both projects array and selected project with fresh data
        setProjects((prev) =>
          prev.map((project) => {
            if (project.id === selectedProject.id) {
              const updatedProject = {
                ...project,
                documents: refreshedData.documents,
                documentCounts: refreshedData.counts,
              }
              setSelectedProject(updatedProject)
              return updatedProject
            }
            return project
          }),
        )
      }
    } catch (error) {
      console.error('Error refreshing documents after upload:', error)
      
      // Fallback to manual count update if API fails
      const newDocuments: ProjectDocument[] = uploadedFiles.map((uploadFile) => ({
        id: `doc-${Date.now()}-${Math.random()}`,
        name: uploadFile.file?.name || uploadFile.name || 'Unknown',
        type: uploadDialog.documentType,
        uploadedAt: new Date().toISOString().split("T")[0],
        size: uploadFile.file?.size ? `${(uploadFile.file.size / 1024 / 1024).toFixed(1)} MB` : 'Unknown',
      }))

      setProjects((prev) =>
        prev.map((project) => {
          if (project.id === selectedProject.id) {
            const currentCounts = project.documentCounts || { metadata: 0, businesslogic: 0, references: 0 }
            const currentDocs = project.documents || []
            
            const updatedProject = {
              ...project,
              documents: [...currentDocs, ...newDocuments],
              documentCounts: {
                ...currentCounts,
                [uploadDialog.documentType]: currentCounts[uploadDialog.documentType] + newDocuments.length,
              },
            }
            setSelectedProject(updatedProject)
            return updatedProject
          }
          return project
        }),
      )
    } finally {
      setIsRefreshingCounts(false)
    }
  }

  const handleLogout = async () => {
    try {
      // Optional: Call logout endpoint
      const token = localStorage.getItem('access_token')
      if (token) {
        await fetch(`${API_BASE_URL}/auth/logout`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        })
      }
    } catch (error) {
      console.error('Logout error:', error)
    } finally {
      // Clear stored data
      localStorage.removeItem('access_token')
      localStorage.removeItem('token_type')
      
      // Redirect to login
      router.push("/login")
    }
  }
  const checkEmbeddingStatus = async (projectId: string) => {
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(
        `${API_BASE_URL}/documents/project/${projectId}/embedding-status`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Accept': 'application/json'
          }
        }
      )

      if (response.ok) {
        const data = await response.json()
        const status = data.embedding_status
        const processing = data.is_processing

        setEmbeddingStatus(status)
        setIsEmbeddingProcessing(processing)
        
        return { status, processing }
      } else {
        console.warn('Failed to fetch embedding status:', response.status)
        return null
      }
    } catch (error) {
      console.error('Error checking embedding status:', error)
      return null
    }
  }

  // **NEW: Polling effect for embedding status**
  useEffect(() => {
    if (!selectedProject) {
      setIsEmbeddingProcessing(false)
      setEmbeddingStatus(null)
      return
    }

    // Initial check
    checkEmbeddingStatus(selectedProject.id)

    // Set up polling interval
    const interval = setInterval(() => {
      checkEmbeddingStatus(selectedProject.id)
    }, 3000) // Check every 3 seconds

    return () => clearInterval(interval)
  }, [selectedProject?.id, API_BASE_URL])
  
  return (
    <div className="h-screen bg-background flex flex-col overflow-hidden min-h-screen">
      {/* Header */}
      <header className="border-b border-border bg-card px-4 py-3 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold text-foreground">AI Document Intelligence</h1>
          {selectedProject && (
            <Badge variant="secondary" className="hidden md:inline-flex">
              {selectedProject.name}
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-4">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="relative h-8 w-8 rounded-full">
                <Avatar className="h-8 w-8">
                  <AvatarImage src="/generic-user-avatar.png" alt={getDisplayName(user)} />
                  <AvatarFallback>{getUserInitials(user)}</AvatarFallback>
                </Avatar>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-56" align="end" forceMount>
              <div className="flex items-center justify-start gap-2 p-2">
                <div className="flex flex-col space-y-1 leading-none">
                  {isLoadingUser ? (
                    <div className="flex items-center gap-2">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      <span className="text-sm">Loading...</span>
                    </div>
                  ) : user ? (
                    <>
                      <p className="font-medium">{getDisplayName(user)}</p>
                      <p className="w-[200px] truncate text-sm text-muted-foreground">
                        {user.email}
                      </p>
                    </>
                  ) : (
                    <p className="text-sm text-muted-foreground">User not loaded</p>
                  )}
                </div>
              </div>
              <DropdownMenuSeparator />
              <DropdownMenuItem>
                <User className="mr-2 h-4 w-4" />
                <span>Profile</span>
              </DropdownMenuItem>
              <DropdownMenuItem>
                <Settings className="mr-2 h-4 w-4" />
                <span>Settings</span>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleLogout}>
                <LogOut className="mr-2 h-4 w-4" />
                <span>Log out</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Project Management */}
        <aside
          ref={sidebarRef}
          className={`${
            sidebarOpen ? "translate-x-0" : "-translate-x-full lg:-translate-x-full"
          } fixed lg:relative z-30 w-80 h-full bg-sidebar border-r border-sidebar-border transition-transform duration-200 ease-in-out ${
            sidebarOpen ? "lg:block" : "lg:hidden"
          } flex flex-col`}
        >
          <div className="absolute -right-3 top-4 z-40">
            <Button
              variant="outline"
              size="sm"
              className="h-6 w-6 p-0 bg-background border shadow-sm"
              onClick={() => setSidebarOpen(!sidebarOpen)}
            >
              <ChevronLeft className="h-3 w-3" />
            </Button>
          </div>
          
          <div className="p-4 border-b border-sidebar-border flex-shrink-0">
            <Dialog open={isCreateProjectOpen} onOpenChange={setIsCreateProjectOpen}>
              <DialogTrigger asChild>
                <Button className="w-full justify-start gap-2" size="sm">
                  <Plus className="h-4 w-4" />
                  New Project
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-[425px]">
                <DialogHeader>
                  <DialogTitle>Create New Project</DialogTitle>
                  <DialogDescription>
                    Create a new project to organize your documents and AI conversations.
                  </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 py-4">
                  <div className="grid gap-2">
                    <Label htmlFor="project-name">Project Name</Label>
                    <Input
                      id="project-name"
                      value={newProjectName}
                      onChange={(e) => setNewProjectName(e.target.value)}
                      placeholder="Enter project name"
                    />
                  </div>
                  <div className="grid gap-2">
                    <Label htmlFor="project-description">Description (Optional)</Label>
                    <Textarea
                      id="project-description"
                      value={newProjectDescription}
                      onChange={(e) => setNewProjectDescription(e.target.value)}
                      placeholder="Describe your project"
                      rows={3}
                    />
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setIsCreateProjectOpen(false)}>
                    Cancel
                  </Button>
                  <Button onClick={handleCreateProject} disabled={!newProjectName.trim() || isCreatingProject}>
                    {isCreatingProject ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        Creating...
                      </>
                    ) : (
                      'Create Project'
                    )}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>

          <div className="flex-1 overflow-y-auto">
            <div className="p-4 space-y-4">
              <div className="projects-container">
                <h3 className="text-sm font-medium text-sidebar-foreground mb-2">Projects</h3>
                {isLoadingProjects ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span className="ml-2 text-sm">Loading projects...</span>
                  </div>
                ) : projects.length === 0 ? (
                  <div className="text-center py-8">
                    <p className="text-sm text-muted-foreground">No projects yet</p>
                    <p className="text-xs text-muted-foreground">Create your first project to get started</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {projects.map((project) => (
                      <Card
                        key={project.id}
                        className={`p-3 cursor-pointer transition-colors ${
                          selectedProject?.id === project.id
                            ? "bg-sidebar-accent text-sidebar-accent-foreground"
                            : "hover:bg-sidebar-accent/50"
                        }`}
                      >
                        <div className="flex items-start justify-between">
                          <div 
                            className="flex-1 min-w-0 cursor-pointer"
                            onClick={() => setSelectedProject(project)}
                          >
                            <h4 className="font-medium text-sm flex items-center gap-2">
                              <FolderOpen className="h-3 w-3" />
                              {project.name}
                            </h4>
                            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                              {project.description}
                            </p>
                            <div className="flex gap-1 mt-2">
                              <Badge variant="outline" className="text-xs px-1 py-0">
                                {isRefreshingCounts && selectedProject?.id === project.id ? (
                                  <Loader2 className="h-2 w-2 animate-spin mr-1" />
                                ) : null}
                                {(project.documentCounts?.metadata || 0) +
                                  (project.documentCounts?.businesslogic || 0) +
                                  (project.documentCounts?.references || 0)}{" "}
                                docs
                              </Badge>
                            </div>
                          </div>
                          
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-6 w-6 p-0 text-muted-foreground"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <MoreVertical className="h-3 w-3" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-48">
                              <DropdownMenuItem 
                                className="text-destructive focus:text-destructive"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  setDeleteDialog({ isOpen: true, project: project, isDeleting: false })
                                }}
                              >
                                <Trash2 className="mr-2 h-4 w-4" />
                                Delete Project
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </Card>
                    ))}
                  </div>
                )}
              </div>

              {selectedProject && (
                <div className="border-t border-sidebar-border pt-4 upload-section">
                  <h3 className="text-sm font-medium text-sidebar-foreground mb-3">
                    Upload Documents - {selectedProject.name}
                  </h3>

                  <div className="space-y-3">
                    {/* Metadata Documents */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Database className="h-4 w-4 text-primary" />
                          <span className="text-sm font-medium">Metadata</span>
                        </div>
                        <Badge variant="secondary" className="text-xs">
                          {isRefreshingCounts ? (
                            <Loader2 className="h-2 w-2 animate-spin" />
                          ) : (
                            selectedProject.documentCounts?.metadata || 0
                          )}
                        </Badge>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full justify-start gap-2 h-8 bg-transparent"
                        onClick={() => handleDocumentUpload("metadata")}
                        disabled={isRefreshingCounts}
                      >
                        <Upload className="h-3 w-3" />
                        Upload Metadata
                      </Button>
                    </div>

                    {/* Business Logic Documents */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-accent" />
                          <span className="text-sm font-medium">Business logic</span>
                        </div>
                        <Badge variant="secondary" className="text-xs">
                          {isRefreshingCounts ? (
                            <Loader2 className="h-2 w-2 animate-spin" />
                          ) : (
                            selectedProject.documentCounts?.businesslogic || 0
                          )}
                        </Badge>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full justify-start gap-2 h-8 bg-transparent"
                        onClick={() => handleDocumentUpload("businesslogic")}
                        disabled={isRefreshingCounts}
                      >
                        <Upload className="h-3 w-3" />
                        Upload Business logic
                      </Button>
                    </div>

                    {/* Reference Documents */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <BookOpen className="h-4 w-4 text-chart-3" />
                          <span className="text-sm font-medium">References</span>
                        </div>
                        <Badge variant="secondary" className="text-xs">
                          {isRefreshingCounts ? (
                            <Loader2 className="h-2 w-2 animate-spin" />
                          ) : (
                            selectedProject.documentCounts?.references || 0
                          )}
                        </Badge>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full justify-start gap-2 h-8 bg-transparent"
                        onClick={() => handleDocumentUpload("references")}
                        disabled={isRefreshingCounts}
                      >
                        <Upload className="h-3 w-3" />
                        Upload References
                      </Button>
                    </div>
                  </div>

                  {selectedProject.documents && selectedProject.documents.length > 0 && (
                    <div className="border-t border-sidebar-border pt-4 mt-4">
                      <div className="flex justify-between items-center mb-2">
                        <h4 className="text-sm font-medium text-sidebar-foreground">Recent Documents</h4>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 p-1"
                          onClick={() => setRecentDocsExpanded(!recentDocsExpanded)}
                        >
                          {recentDocsExpanded ? (
                            <ChevronUp className="h-3 w-3" />
                          ) : (
                            <ChevronDown className="h-3 w-3" />
                          )}
                        </Button>
                      </div>
                      <div 
                        className="space-y-1 overflow-y-auto transition-all duration-300"
                        style={{ 
                          maxHeight: recentDocsExpanded ? recentDocsHeight : '80px',
                          minHeight: '80px'
                        }}
                      >
                        {selectedProject.documents.slice(0, 7).map((doc) => (
                          <div key={doc.id} className="flex items-center gap-2 p-2 rounded text-xs">
                            {doc.type === "metadata" && <Database className="h-3 w-3 text-primary flex-shrink-0" />}
                            {doc.type === "businesslogic" && <FileText className="h-3 w-3 text-accent flex-shrink-0" />}
                            {doc.type === "references" && <BookOpen className="h-3 w-3 text-chart-3 flex-shrink-0" />}
                            <div className="flex-1 min-w-0">
                              <p className="truncate font-medium">{doc.name}</p>
                              <p className="text-muted-foreground">{doc.size}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </aside>

        {/* Main Chat Area */}
        <main className="flex-1 flex flex-col min-h-0 h-full">
          {selectedProject && (
          <EmbeddingStatusBanner 
            projectId={selectedProject.id} 
            onStatusChange={setIsEmbeddingProcessing}
          />
        )}
          <ChatInterface selectedProject={selectedProject}
           isEmbeddingProcessing={isEmbeddingProcessing} />
        </main>

        {/* Right Panel - Download Management */}
        <aside
          className={`${
            rightPanelOpen ? "translate-x-0" : "translate-x-full lg:translate-x-full"
          } fixed lg:relative z-20 right-0 w-80 h-full bg-card border-l border-border transition-transform duration-200 ease-in-out min-h-0 ${
            rightPanelOpen ? "lg:block" : "lg:hidden"
          } flex flex-col`}
        >
          <div className="absolute -left-3 top-4 z-40">
            <Button
              variant="outline"
              size="sm"
              className="h-6 w-6 p-0 bg-background border shadow-sm"
              onClick={() => setRightPanelOpen(!rightPanelOpen)}
            >
              <ChevronRight className="h-3 w-3" />
            </Button>
          </div>
          <DownloadManagement selectedProject={selectedProject} projects={projects} />
        </aside>
        
        {/* Toggle button for collapsed left sidebar */}
        {!sidebarOpen && (
          <div className="absolute left-4 top-20 z-40">
            <Button
              variant="outline"
              size="sm"
              className="h-8 w-8 p-0 bg-background border shadow-sm"
              onClick={() => setSidebarOpen(true)}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}

        {/* Toggle button for collapsed right sidebar */}
        {!rightPanelOpen && (
          <div className="absolute right-4 top-20 z-40">
            <Button
              variant="outline"
              size="sm"
              className="h-8 w-8 p-0 bg-background border shadow-sm"
              onClick={() => setRightPanelOpen(true)}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>

      {/* Mobile Overlay */}
      {(sidebarOpen || rightPanelOpen) && (
        <div
          className="fixed inset-0 bg-black/50 z-10 lg:hidden"
          onClick={() => {
            setSidebarOpen(false)
            setRightPanelOpen(false)
          }}
        />
      )}

      {/* Delete Confirmation Dialog */}
      <Dialog 
        open={deleteDialog.isOpen} 
        onOpenChange={(open) => !deleteDialog.isDeleting && setDeleteDialog({ isOpen: open, project: null, isDeleting: false })}
      >
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Delete Project</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "<strong>{deleteDialog.project?.name}</strong>"? This action cannot be undone and will delete all associated documents.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button 
              variant="outline" 
              onClick={() => setDeleteDialog({ isOpen: false, project: null, isDeleting: false })}
              disabled={deleteDialog.isDeleting}
            >
              Cancel
            </Button>
            <Button 
              variant="destructive" 
              onClick={handleDeleteProject}
              disabled={deleteDialog.isDeleting}
            >
              {deleteDialog.isDeleting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Deleting...
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete Project
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <DocumentUploadDialog
        isOpen={uploadDialog.isOpen}
        onClose={() => setUploadDialog({ ...uploadDialog, isOpen: false })}
        documentType={uploadDialog.documentType}
        projectId={selectedProject?.id || ""}
        projectName={selectedProject?.name || ""}
        onUploadComplete={handleUploadComplete}
      />
    </div>
  )
}
