"use client"

import { useState, useEffect, useCallback, useMemo } from "react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Calendar } from "@/components/ui/calendar"
import AlertSection from "@/components/alert-section"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
// import { Input } from "@/components/ui/input"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { 
  Eye,
  Download, 
  FileText, 
  CalendarIcon, 
  Plus, 
  Loader2, 
  CheckCircle, 
  XCircle, 
  Clock, 
  RefreshCw,
  Wifi,
  WifiOff,
  FileSpreadsheet
} from "lucide-react"
import { format } from "date-fns"
import { toast } from "sonner"

interface PurchaseOrder {
  po_number: string
  vendor_name: string
  total_amount: number
  status: "generated" | "pending_approval" | "approved" | "rejected" | "sent_to_vendor"
  needs_approval: boolean
  pdf_path: string
  order_date: string
  created_at: string
  materials_count?: number
}

interface Project {
  id: string
  name: string
}

interface POSidebarProps {
  selectedProject: Project | null
}

interface WebSocketMessage {
  type: 'workflow_progress' | 'workflow_complete' | 'workflow_error' | 'po_status_update' | 'connection_established'
  project_id?: string
  workflow_id?: string
  po_number?: string
  step?: string
  message?: string
  error?: string
  status?: string
  timestamp?: string
}

type FilterType = 'all' | 'pending' | 'sent_to_vendor' | 'rejected'

export function POSidebar({ selectedProject }: POSidebarProps) {
  const [selectedDate, setSelectedDate] = useState<Date>(new Date())
  const [todayPOs, setTodayPOs] = useState<PurchaseOrder[]>([])
  const [selectedDatePOs, setSelectedDatePOs] = useState<PurchaseOrder[]>([])
  // const [isGenerating, setIsGenerating] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  // const [showDatePicker, setShowDatePicker] = useState(false)
  const [workflowStatus, setWorkflowStatus] = useState<string | null>(null)
  // const [naturalDateInput, setNaturalDateInput] = useState("")
  
  // Enhanced filter states for multiple status options
  const [todayFilter, setTodayFilter] = useState<FilterType>('all')
  const [selectedDateFilter, setSelectedDateFilter] = useState<FilterType>('all')
  
  // WebSocket state
  const [wsConnection, setWsConnection] = useState<WebSocket | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [connectionRetries, setConnectionRetries] = useState(0)
  const [lastWorkflowError, setLastWorkflowError] = useState<{date: string, error: string} | null>(null)
  
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "https://retail-ai-chatbot.onrender.com"

  // Filter and sort Today's POs
  const filteredTodayPOs = useMemo(() => {
    switch (todayFilter) {
      case 'pending':
        return todayPOs.filter(po => po.status === 'pending_approval');
      case 'sent_to_vendor':
        return todayPOs.filter(po => po.status === 'sent_to_vendor' || po.status === 'approved');
      case 'rejected':
        return todayPOs.filter(po => po.status === 'rejected');
      default:
        return todayPOs;
    }
  }, [todayPOs, todayFilter]);

  const sortedTodayPOs = useMemo(() => {
    return filteredTodayPOs.sort((a, b) => {
      // Sort by priority: pending -> rejected -> sent_to_vendor -> others
      const priority: Record<string, number> = { 
        'pending_approval': 0, 
        'rejected': 1, 
        'sent_to_vendor': 2, 
        'approved': 2 
      };
      return (priority[a.status] || 3) - (priority[b.status] || 3);
    });
  }, [filteredTodayPOs]);

  // Filter and sort Selected Date POs
  const filteredSelectedDatePOs = useMemo(() => {
    switch (selectedDateFilter) {
      case 'pending':
        return selectedDatePOs.filter(po => po.status === 'pending_approval');
      case 'sent_to_vendor':
        return selectedDatePOs.filter(po => po.status === 'sent_to_vendor' || po.status === 'approved');
      case 'rejected':
        return selectedDatePOs.filter(po => po.status === 'rejected');
      default:
        return selectedDatePOs;
    }
  }, [selectedDatePOs, selectedDateFilter]);

  const sortedSelectedDatePOs = useMemo(() => {
    return filteredSelectedDatePOs.sort((a, b) => {
      // Sort by priority: pending -> rejected -> sent_to_vendor -> others
      const priority: Record<string, number> = { 
        'pending_approval': 0, 
        'rejected': 1, 
        'sent_to_vendor': 2, 
        'approved': 2 
      };
      return (priority[a.status] || 3) - (priority[b.status] || 3);
    });
  }, [filteredSelectedDatePOs]);

  // Helper function to get status counts
  const getStatusCounts = (pos: PurchaseOrder[]) => ({
    pending: pos.filter(po => po.status === 'pending_approval').length,
    sent_to_vendor: pos.filter(po => po.status === 'sent_to_vendor' || po.status === 'approved').length,
    rejected: pos.filter(po => po.status === 'rejected').length,
    total: pos.length
  });

  // Filter Buttons Component
  const FilterButtons = ({ 
    currentFilter, 
    onFilterChange, 
    counts 
  }: { 
    currentFilter: FilterType;
    onFilterChange: (filter: FilterType) => void;
    counts: { pending: number; sent_to_vendor: number; rejected: number; total: number };
  }) => (
    <div className="flex items-center gap-1 flex-wrap">
      <Button
        size="sm"
        variant={currentFilter === 'all' ? "default" : "outline"}
        onClick={() => onFilterChange('all')}
        className="h-6 text-xs px-2 bg-secondary"
      >
        All ({counts.total})
      </Button>
      
      {counts.pending > 0 && (
        <Button
          size="sm"
          variant={currentFilter === 'pending' ? "destructive" : "outline"}
          onClick={() => onFilterChange('pending')}
          className="h-6 text-xs px-2"
        >
          <Clock className="h-3 w-3 mr-1" />
          Pending ({counts.pending})
        </Button>
      )}
      
      {counts.sent_to_vendor > 0 && (
        <Button
          size="sm"
          variant={currentFilter === 'sent_to_vendor' ? "default" : "outline"}
          onClick={() => onFilterChange('sent_to_vendor')}
          className={`h-6 text-xs px-2 ${
            currentFilter === 'sent_to_vendor' 
              ? 'bg-green-600 hover:bg-green-700 text-white' 
              : 'bg-green-100 hover:bg-green-200 text-green-800 border-green-300'
          }`}
        >
          <CheckCircle className="h-3 w-3 mr-1" />
          Sent ({counts.sent_to_vendor})
        </Button>
      )}
      
      {counts.rejected > 0 && (
        <Button
          size="sm"
          variant={currentFilter === 'rejected' ? "destructive" : "outline"}
          onClick={() => onFilterChange('rejected')}
          className={`h-6 text-xs px-2 ${
            currentFilter !== 'rejected' 
              ? 'bg-red-100 hover:bg-red-200 text-red-800 border-red-300' 
              : ''
          }`}
        >
          <XCircle className="h-3 w-3 mr-1" />
          Rejected ({counts.rejected})
        </Button>
      )}
    </div>
  );
  
  // WebSocket connection management
  useEffect(() => {
    if (!selectedProject) {
      if (wsConnection) {
        wsConnection.close()
        setWsConnection(null)
        setIsConnected(false)
      }
      return
    }

    connectWebSocket()
    
    return () => {
      if (wsConnection) {
        wsConnection.close()
      }
    }
  }, [selectedProject?.id])

  const connectWebSocket = useCallback(() => {
    if (!selectedProject) return

    try {
      const token = localStorage.getItem('access_token')
      if (!token) {
        console.warn('No access token available for WebSocket connection')
        return
      }

      const wsUrl = `${API_BASE_URL.replace('http', 'ws')}/ws/${selectedProject.id}?token=${token}`
      
      console.log(`🔌 Connecting to WebSocket: ${wsUrl}`)
      
      const ws = new WebSocket(wsUrl)
      
      ws.onopen = () => {
        console.log('✅ WebSocket connected')
        setIsConnected(true)
        setWsConnection(ws)
        setConnectionRetries(0)
        toast.success('🔗 Connected to real-time updates', { duration: 2000 })
      }
      
      ws.onmessage = (event) => {
        try {
          const data: WebSocketMessage = JSON.parse(event.data)
          handleWebSocketMessage(data)
        } catch (error) {
          console.error('Error parsing WebSocket message:', error)
        }
      }
      
      ws.onclose = (event) => {
        console.log('🔌 WebSocket disconnected:', event.code, event.reason)
        setIsConnected(false)
        setWsConnection(null)
        
        if (selectedProject && connectionRetries < 5) {
          const delay = Math.min(1000 * Math.pow(2, connectionRetries), 30000)
          console.log(`🔄 Reconnecting in ${delay}ms... (attempt ${connectionRetries + 1})`)
          
          setTimeout(() => {
            setConnectionRetries(prev => prev + 1)
            connectWebSocket()
          }, delay)
        }
      }
      
      ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error)
        toast.error('Connection error - using polling fallback')
      }

    } catch (error) {
      console.error('Failed to create WebSocket connection:', error)
    }
  }, [selectedProject?.id, connectionRetries])

  const handleWebSocketMessage = (data: WebSocketMessage) => {
    console.log('📨 WebSocket message:', data)
    
    switch (data.type) {
      case 'workflow_progress':
        setWorkflowStatus(data.message || 'Processing...')
        toast.info(`🔄 ${data.message}`, { duration: 3000 })
        break
        
      case 'workflow_complete':
        // setIsGenerating(false)
        setWorkflowStatus(null)
        setLastWorkflowError(null) 
        const successMessage = data.message || 'Purchase orders generated successfully!'
        toast.success(`🎉 ${successMessage}`, { duration: 5000, description: 'Check the PO lists below for your new purchase orders'})

        setTimeout(() => {
          fetchTodayPOs()
          if (!isToday(selectedDate)) {
            fetchPOsForDate(format(selectedDate, 'yyyy-MM-dd'))
          }
        }, 1000)
        break
        
      case 'workflow_error':
        const errorDate = new Date().toLocaleDateString()
        // setIsGenerating(false)
        setWorkflowStatus(null)
        setLastWorkflowError({
          date: errorDate,
          error: data.error || data.message || 'Unknown error'
        })
        toast.error(`❌ ${data.error || data.message || "Unknown error"}`, { duration: 7000 })
        break
        
      case 'po_status_update':
        toast.info(`📋 ${data.message}`, { duration: 4000 })
        
        console.log('🔄 Processing PO status update:', data)
      
        const { po_number, status, message } = data;
        
        // 🚀 ENHANCED DEBUG LOGGING
        console.log(`🔍 Updating PO ${po_number} from any status to ${status}`)
        console.log(`📊 Current todayPOs count: ${todayPOs.length}`)
        console.log(`📊 Current selectedDatePOs count: ${selectedDatePOs.length}`)
        
        if (po_number && status) {
          // Update Today's POs with detailed logging
          setTodayPOs(prev => {
            console.log('🔍 Before update - todayPOs:', prev.map(po => `${po.po_number}:${po.status}`))
            
            const updated = prev.map(po => {
              if (po.po_number === po_number) {
                console.log(`✅ Found PO ${po_number}, updating status from ${po.status} to ${status}`)
                return { ...po, status: status as any }
              }
              return po
            })
            
            console.log('🔍 After update - todayPOs:', updated.map(po => `${po.po_number}:${po.status}`))
            return updated
          })
          
          // Update Selected Date POs with detailed logging
          setSelectedDatePOs(prev => {
            console.log('🔍 Before update - selectedDatePOs:', prev.map(po => `${po.po_number}:${po.status}`))
            
            const updated = prev.map(po => {
              if (po.po_number === po_number) {
                console.log(`✅ Found PO ${po_number} in selected date, updating status from ${po.status} to ${status}`)
                return { ...po, status: status as any }
              }
              return po
            })
            
            console.log('🔍 After update - selectedDatePOs:', updated.map(po => `${po.po_number}:${po.status}`))
            return updated
          })
          
          // Show toast notification
          if (status === 'approved') {
            toast.success(`✅ ${message || `PO ${po_number} approved`}`, { duration: 5000 })
          } else if (status === 'rejected') {
            toast.error(`❌ ${message || `PO ${po_number} rejected`}`, { duration: 5000 })
          } else if (status === 'sent_to_vendor') {
            toast.success(`📤 ${message || `PO ${po_number} sent to vendor`}`, { duration: 5000 })
          } else {
            toast.info(`📋 ${message || `PO ${po_number} status updated to ${status}`}`, { duration: 4000 })
          }
          
          console.log(`✅ PO ${po_number} status updated to ${status} in both lists`)
        } else {
          console.error('❌ Missing po_number or status in WebSocket message:', data)
        }
        break
        
      case 'connection_established':
        console.log('🎯 Connection established for project:', data.project_id)
        break
        
      default:
        console.log('❓ Unknown WebSocket message type:', data.type)
    }
  }

  // Initial data loading and polling fallback
  useEffect(() => {
    if (!selectedProject) return

    fetchTodayPOs()
    if (!isToday(selectedDate)) {
      fetchPOsForDate(format(selectedDate, 'yyyy-MM-dd'))
    }

    const interval = setInterval(() => {
      // if (!isConnected && !isGenerating) {
      if (!isConnected) {
        fetchTodayPOs()
        if (!isToday(selectedDate)) {
          fetchPOsForDate(format(selectedDate, 'yyyy-MM-dd'))
        }
      }
    }, 15000)

    return () => clearInterval(interval)
  }, [selectedProject, selectedDate, isConnected])
  // }, [selectedProject, selectedDate, isConnected, isGenerating])

  const isToday = (date: Date) => {
    const today = new Date()
    return format(date, 'yyyy-MM-dd') === format(today, 'yyyy-MM-dd')
  }

  const fetchTodayPOs = async () => {
    if (!selectedProject) return

    try {
      const token = localStorage.getItem('access_token')
      const today = format(new Date(), 'yyyy-MM-dd')
      
      const response = await fetch(
        `${API_BASE_URL}/po/project/${selectedProject.id}?order_date=${today}`, 
        {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      )

      if (response.ok) {
        const data = await response.json()
        setTodayPOs(data.pos || [])
      } else {
        console.error('Failed to fetch today POs:', response.status)
      }
    } catch (error) {
      console.error('Error fetching today POs:', error)
    }
  }

  const fetchPOsForDate = async (dateStr: string) => {
    if (!selectedProject || isToday(new Date(dateStr))) return

    setIsLoading(true)
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(
        `${API_BASE_URL}/po/project/${selectedProject.id}?order_date=${dateStr}`, 
        {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      )

      if (response.ok) {
        const data = await response.json()
        setSelectedDatePOs(data.pos || [])
      }
    } catch (error) {
      console.error('Error fetching POs for date:', error)
    } finally {
      setIsLoading(false)
    }
  }

  // Refresh function
  const handleRefresh = async () => {
    if (!selectedProject || isRefreshing) return

    setIsRefreshing(true)
    try {
      await fetchTodayPOs()
      if (!isToday(selectedDate)) {
        await fetchPOsForDate(format(selectedDate, 'yyyy-MM-dd'))
      }
      toast.success('📋 POs refreshed!')
    } catch (error) {
      toast.error('Failed to refresh POs')
    } finally {
      setIsRefreshing(false)
    }
  }

  // const generatePOForDate = async (dateInput: string) => {
  //   if (!selectedProject) return

  //   setIsGenerating(true)
  //   setWorkflowStatus("Starting PO generation...")

  //   try {
  //     const token = localStorage.getItem('access_token')
  //     const response = await fetch(
  //       `${API_BASE_URL}/po/generate?project_id=${selectedProject.id}`, 
  //       {
  //         method: 'POST',
  //         headers: {
  //           'Authorization': `Bearer ${token}`,
  //           'Content-Type': 'application/json',
  //         },
  //         body: JSON.stringify({
  //           order_date: dateInput,
  //           trigger_query: `Generate PO for ${dateInput} from sidebar`
  //         }),
  //       }
  //     )

  //     if (response.ok) {
  //       const data = await response.json()

  //       if (data.success) {
  //         if (data.workflow_id) {
  //           if (!isConnected) {
  //             setWorkflowStatus("Analyzing materials and vendors...")
  //             monitorWorkflowPolling(data.workflow_id, dateInput)
  //           }
  //         } else if (data.message) {
  //           toast.info(`✅ ${data.message}`)
  //           setIsGenerating(false)
  //           setWorkflowStatus(null)
  //         }
          
  //         if (data.date_interpretation) {
  //           toast.info(`📅 ${data.date_interpretation}`, { duration: 3000 })
  //         }
  //       } else {
  //         toast.error(`❌ ${data.message || 'PO generation failed'}`)
  //         setIsGenerating(false)
  //         setWorkflowStatus(null)
  //       }
  //     } else {
  //       const errorText = await response.text()
  //       console.error('PO generation request failed:', response.status, errorText)
  //       toast.error('Failed to generate PO. Please check console for details.')
  //       setIsGenerating(false)
  //       setWorkflowStatus(null)
  //     }
  //   } catch (error) {
  //     console.error('Error generating PO:', error)
  //     toast.error('Failed to generate PO. Please try again.')
  //     setIsGenerating(false)
  //     setWorkflowStatus(null)
  //   }
  // }

  // // **SINGLE UNIFIED GENERATE FUNCTION**
  // const handleGeneratePO = () => {
  //   if (naturalDateInput.trim()) {
  //     // Use natural date input if provided
  //     generatePOForDate(naturalDateInput.trim())
  //     setNaturalDateInput("")
  //   } else if (!isToday(selectedDate)) {
  //     // Use selected calendar date if not today
  //     const dateStr = format(selectedDate, 'yyyy-MM-dd')
  //     generatePOForDate(dateStr)
  //   } else {
  //     // Default to today
  //     const today = format(new Date(), 'yyyy-MM-dd')
  //     generatePOForDate(today)
  //   }
  // }

  // const monitorWorkflowPolling = async (workflowId: string, dateStr?: string) => {
  //   const token = localStorage.getItem('access_token')
  //   let attempts = 0
  //   const maxAttempts = 60

  //   const checkStatus = async () => {
  //     try {
  //       const response = await fetch(
  //         `${API_BASE_URL}/po/workflow/${workflowId}/status`,
  //         {
  //           headers: {
  //             'Authorization': `Bearer ${token}`,
  //           },
  //         }
  //       )

  //       if (response.ok) {
  //         const data = await response.json()
          
  //         if (data.workflow_status?.status === 'completed') {
  //           const posCount = data.workflow_status?.pos_generated?.length || 0
  //           toast.success(`🎉 Generated ${posCount} PO(s) successfully!`)
            
  //           fetchTodayPOs()
  //           if (dateStr && !isToday(new Date(dateStr))) {
  //             fetchPOsForDate(dateStr)
  //           }
            
  //           setIsGenerating(false)
  //           setWorkflowStatus(null)
  //           return
  //         } else if (data.workflow_status?.status === 'failed') {
  //           toast.error(`❌ PO generation failed: ${data.workflow_status?.error_message || 'Unknown error'}`)
  //           setIsGenerating(false)
  //           setWorkflowStatus(null)
  //           return
  //         } else if (data.workflow_status?.status === 'running') {
  //           const step = data.workflow_status?.current_step || 0
  //           const stepMessages = [
  //             "Initializing...",
  //             "Checking material shortfalls...",
  //             "Analyzing packaging requirements...",
  //             "Getting vendor pricing...",
  //             "Generating PO documents...",
  //             "Finalizing and sending notifications..."
  //           ]
  //           setWorkflowStatus(stepMessages[step] || "Processing...")
  //         }
  //       }

  //       attempts++
  //       if (attempts < maxAttempts) {
  //         setTimeout(checkStatus, 5000)
  //       } else {
  //         toast.error('❌ Workflow monitoring timeout')
  //         setIsGenerating(false)
  //         setWorkflowStatus(null)
  //       }
  //     } catch (error) {
  //       console.error('Error monitoring workflow:', error)
  //       attempts++
  //       if (attempts < maxAttempts) {
  //         setTimeout(checkStatus, 5000)
  //       } else {
  //         setIsGenerating(false)
  //         setWorkflowStatus(null)
  //       }
  //     }
  //   }

  //   checkStatus()
  // }

  const handleDownload = async (po: PurchaseOrder) => {
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(
        `${API_BASE_URL}/po/download/${po.po_number}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      )

      if (response.ok) {
        // Get the PDF as blob
        const pdfBlob = await response.blob();
        
        // Create download link and trigger download
        const downloadUrl = window.URL.createObjectURL(pdfBlob);
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = `${po.po_number}.pdf`;
        document.body.appendChild(link);
        link.click();
        
        // Cleanup
        document.body.removeChild(link);
        window.URL.revokeObjectURL(downloadUrl);
        
        toast.success(`✅ Downloaded ${po.po_number}.pdf`);
      } else {
        throw new Error(`Download failed: ${response.status}`);
      }
    } catch (error) {
      console.error('Download error:', error);
      toast.error('Failed to download PO');
    }
  };

  const handleViewPDF = async (po: PurchaseOrder) => {
    try {
      const token = localStorage.getItem('access_token');
      
      const response = await fetch(`${API_BASE_URL}/po/view/${po.po_number}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (response.ok) {
        const pdfBlob = await response.blob();
        const pdfUrl = window.URL.createObjectURL(pdfBlob);
        
        // Open in new tab for viewing
        window.open(pdfUrl, '_blank');
        
        // Clean up after delay
        setTimeout(() => window.URL.revokeObjectURL(pdfUrl), 60000);
        
        toast.success(`📄 Opening ${po.po_number} for viewing`);
      } else {
        throw new Error(`View failed: ${response.status}`);
      }
    } catch (error) {
      console.error('View error:', error);
      toast.error('Failed to open PDF for viewing');
    }
  };

  const getStatusIcon = (status: string) => {
    const iconMap = {
      'approved': { icon: <CheckCircle className="h-3 w-3 text-green-500" />, tooltip: 'Approved' },
      'sent_to_vendor': { icon: <CheckCircle className="h-3 w-3 text-green-500" />, tooltip: 'Sent to Vendor' },
      'rejected': { icon: <XCircle className="h-3 w-3 text-red-500" />, tooltip: 'Rejected' },
      'pending_approval': { icon: <Clock className="h-3 w-3 text-yellow-500" />, tooltip: 'Pending Approval' },
      'generated': { icon: <Clock className="h-3 w-3 text-blue-500" />, tooltip: 'Generated' }
    }
    return iconMap[status as keyof typeof iconMap] || iconMap['generated']
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'approved':
      case 'sent_to_vendor':
        return 'bg-green-100 text-green-800'
      case 'rejected':
        return 'bg-red-100 text-red-800'
      case 'pending_approval':
        return 'bg-yellow-100 text-yellow-800'
      default:
        return 'bg-blue-100 text-blue-800'
    }
  }

  // Helper function to get the display text for the button
  // const getGenerateButtonText = () => {
  //   if (naturalDateInput.trim()) {
  //     return `Generate PO for "${naturalDateInput}"`
  //   } else if (!isToday(selectedDate)) {
  //     return `Generate PO for ${format(selectedDate, 'MMM dd')}`
  //   } else {
  //     return "Generate PO for Today"
  //   }
  // }

  if (!selectedProject) {
    return (
      <div className="p-4 text-center">
        <FileText className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
        <p className="text-xs text-muted-foreground">Select a project to view documents</p>
      </div>
    )
  }

  return (
    <TooltipProvider>
      <div className="flex flex-col h-full overflow-y-auto">
        {/* Alert Section */}
        {/* <AlertSection></AlertSection> */}
        {/* Header */}
        <div className="p-3 border-b">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium text-sm">Generated Documents</h3>
            <div className="flex items-center gap-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  {isConnected ? (
                    <Wifi className="h-3 w-3 text-green-500" />
                  ) : (
                    <WifiOff className="h-3 w-3 text-orange-500" />
                  )}
                </TooltipTrigger>
                <TooltipContent>
                  {isConnected ? 'Real-time updates active' : 'Using polling fallback'}
                </TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleRefresh}
                    disabled={isRefreshing}
                    className="h-6 w-6 p-0 hover:bg-blue-50 hover:border-blue-200 transition-colors"
                  >
                    <RefreshCw className={`h-3 w-3 ${isRefreshing ? 'animate-spin' : ''}`} />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  Refresh PO list
                </TooltipContent>
              </Tooltip>
            </div>
          </div>

          {/* <Badge variant="secondary" className="text-xs w-full justify-center">
            {selectedProject.name}
          </Badge> */}
        </div>

        {/* **UNIFIED GENERATION INTERFACE** */}
        {/* <div className="p-3 border-b">
          <div className="space-y-2">
            // Natural Date Input
            <Input
              placeholder="Enter date (today, tomorrow, 16-09, etc.)"
              value={naturalDateInput}
              onChange={(e) => setNaturalDateInput(e.target.value)}
              className="text-xs h-8"
              onKeyPress={(e) => {
                if (e.key === 'Enter') {
                  handleGeneratePO()
                }
              }}
            />

            // Calendar Date Picker 
            <Popover open={showDatePicker} onOpenChange={setShowDatePicker}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start text-xs h-8"
                >
                  <CalendarIcon className="mr-2 h-3 w-3" />
                  {format(selectedDate, "MMM dd, yyyy")}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar
                  mode="single"
                  selected={selectedDate}
                  onSelect={(date) => {
                    if (date) {
                      setSelectedDate(date)
                      setShowDatePicker(false)
                    }
                  }}
                  initialFocus
                />
              </PopoverContent>
            </Popover>

            // **PO GENERATE BUTTON**
            <Button
              onClick={handleGeneratePO}
              disabled={isGenerating}
              className="w-full h-8 text-xs hover:bg-green-600 transition-colors"
              size="sm"
            >
              {isGenerating ? (
                <>
                  <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Plus className="mr-2 h-3 w-3" />
                  {getGenerateButtonText()}
                </>
              )}
            </Button>
          </div> */}
          <div className="p-3 border-b">
            <div className="text-center">
              <p className="text-xs text-muted-foreground mb-1">
                💬 Generate documents using chat commands
              </p>
              <p className="text-xs text-blue-600 font-medium">
                Try: "generate documents for today"
              </p>
            </div>
          
            <div className="p-3 border-b">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-medium">View Date</h4>
              </div>
              
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full justify-start text-xs h-8"
                  >
                    <CalendarIcon className="mr-2 h-3 w-3" />
                    {format(selectedDate, "MMM dd, yyyy")}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar
                    mode="single"
                    selected={selectedDate}
                    onSelect={(date) => {
                      if (date) {
                        setSelectedDate(date)
                      }
                    }}
                    initialFocus
                  />
                </PopoverContent>
              </Popover>
            </div>

          {workflowStatus && (
            <div className="mt-2 bg-blue-50 border border-blue-200 rounded p-2">
              <div className="flex items-center gap-2">
                <Loader2 className="h-3 w-3 animate-spin text-blue-600" />
                <p className="text-xs text-blue-800">{workflowStatus}</p>
              </div>
            </div>
          )}

          
          {workflowStatus && (
            <div className="mt-2 border border-blue-200 rounded bg-gradient-to-r from-blue-50 to-blue-100 dark:from-blue-900/40 dark:to-blue-800/40">
              <div className="p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                  <span className="text-sm font-semibold text-blue-900 dark:text-blue-100">
                    Generating Purchase Order
                  </span>
                </div>
                <div className="text-xs text-blue-800 dark:text-blue-200 leading-relaxed">
                  {workflowStatus}
                </div>
                <div className="mt-2 text-xs text-blue-600 dark:text-blue-300">
                  💬 You can continue chatting while this processes in the background
                </div>
              </div>
            </div>
          )}

        </div>

        {/* SCROLLABLE CONTENT AREA */}
        <div className="flex-1 overflow-hidden">
          <div className="h-full overflow-y-auto">
            
            {/* TODAY'S POs - Enhanced with multi-status filtering */}
            <div className="p-3 border-b">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-xs font-medium text-muted-foreground">
                  Today's documents ({filteredTodayPOs.length})
                </h4>
              </div>

              {/* Filter Buttons for Today's documents */}
              <div className="mb-3">
                <FilterButtons
                  currentFilter={todayFilter}
                  onFilterChange={setTodayFilter}
                  counts={getStatusCounts(todayPOs)}
                />
              </div>

              {filteredTodayPOs.length === 0 ? (
                <div className="text-center py-4">
                  <p className="text-xs text-muted-foreground">
                    {todayFilter === 'all' ? "No documents for today" : `No ${todayFilter.replace('_', ' ')} documents for today`}
                  </p>
                </div>
              ) : (
                <div className="space-y-2 max-h-80 overflow-y-auto">
                  {sortedTodayPOs.map((po) => {
                    const statusInfo = getStatusIcon(po.status)
                    const isPending = po.status === 'pending_approval'
                    const isRejected = po.status === 'rejected'
                    const isSent = po.status === 'sent_to_vendor' || po.status === 'approved'
                    
                    return (
                      <Card 
                        key={po.po_number} 
                        className={`p-2 transition-all duration-200 ${
                          isPending 
                            ? 'border-orange-300 bg-orange-50 hover:shadow-md hover:border-orange-400' 
                            : isRejected
                            ? 'border-red-300 bg-red-50 hover:shadow-md hover:border-red-400'
                            : isSent
                            ? 'border-green-300 bg-green-50 hover:shadow-md hover:border-green-400'
                            : 'hover:shadow-md hover:border-blue-200'
                        }`}
                      >
                        <div className="space-y-2">
                          <div className="flex items-start justify-between">
                            <div className="flex items-center gap-2">
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <FileSpreadsheet className="h-3 w-3 text-red-600" />
                                </TooltipTrigger>
                                <TooltipContent>
                                  PDF Document
                                </TooltipContent>
                              </Tooltip>
                              <div>
                                <p className={`text-xs font-medium ${
                                  isPending ? 'text-orange-800' : 
                                  isRejected ? 'text-red-800' : 
                                  isSent ? 'text-green-800' : ''
                                }`}>
                                  {po.po_number}
                                </p>
                                {isPending && (
                                  <p className="text-xs text-orange-600 font-medium">⏳ Awaiting Approval</p>
                                )}
                                {isRejected && (
                                  <p className="text-xs text-red-600 font-medium">❌ Rejected</p>
                                )}
                                {isSent && (
                                  <p className="text-xs text-green-600 font-medium">✅ Sent to Vendor</p>
                                )}
                              </div>
                            </div>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <div className="cursor-help">
                                  {statusInfo.icon}
                                </div>
                              </TooltipTrigger>
                              <TooltipContent>
                                {statusInfo.tooltip}
                              </TooltipContent>
                            </Tooltip>
                          </div>

                          <div className="flex justify-between items-center">
                            <span className={`text-xs font-medium ${
                              isPending ? 'text-orange-800' : 
                              isRejected ? 'text-red-800' : 
                              isSent ? 'text-green-800' : ''
                            }`}>
                              ${po.total_amount.toLocaleString()}
                              <p className="text-xs text-muted-foreground truncate">
                                {po.vendor_name}
                              </p>
                            </span>
                            {/* <Badge 
                              className={`${getStatusColor(po.status)} text-xs`} 
                              variant="secondary"
                            >
                              {po.status.replace('_', ' ').toUpperCase()}
                            </Badge> */}
                          
                          
                            <div className="flex gap-1">
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className={`flex-1 h-6 text-xs transition-colors ${
                                      isPending 
                                        ? 'hover:bg-orange-100 hover:border-orange-300 hover:text-orange-700' 
                                        : isRejected
                                        ? 'hover:bg-red-100 hover:border-red-300 hover:text-red-700'
                                        : isSent
                                        ? 'hover:bg-green-100 hover:border-green-300 hover:text-green-700'
                                        : 'hover:bg-blue-50 hover:border-blue-200 hover:text-blue-700'
                                    }`}
                                    onClick={() => handleViewPDF(po)}
                                  >
                                    <Eye className="h-3 w-3 mr-1" />
                  
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>View {po.po_number} in browser</TooltipContent>
                              </Tooltip>
                              
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className="flex-1 h-6 text-xs hover:bg-gray-100 hover:border-gray-300 hover:text-gray-700 transition-colors"
                                    onClick={() => handleDownload(po)}
                                  >
                                    <Download className="h-3 w-3 mr-1" />
                          
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Download {po.po_number}</TooltipContent>
                              </Tooltip>
                            </div>
                          </div>
                        </div>
                      </Card>
                    )
                  })}
                </div>
              )}
            </div>

            {/* SELECTED DATE POs - Enhanced with multi-status filtering */}
            {!isToday(selectedDate) && (
              <div className="p-3">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-xs font-medium text-muted-foreground">
                    Documents for {format(selectedDate, 'MMM dd, yyyy')} ({filteredSelectedDatePOs.length})
                  </h4>
                </div>
                
                {/* Filter Buttons for Selected Date POs */}
                <div className="mb-3">
                  <FilterButtons
                    currentFilter={selectedDateFilter}
                    onFilterChange={setSelectedDateFilter}
                    counts={getStatusCounts(selectedDatePOs)}
                  />
                </div>

                {isLoading ? (
                  <div className="text-center py-2">
                    <Loader2 className="h-4 w-4 animate-spin mx-auto" />
                  </div>
                ) : sortedSelectedDatePOs.length > 0 ? (
                  <div className="space-y-2 max-h-80 overflow-y-auto">
                    {sortedSelectedDatePOs.map((po) => {
                      const statusInfo = getStatusIcon(po.status)
                      const isPending = po.status === 'pending_approval'
                      const isRejected = po.status === 'rejected'
                      const isSent = po.status === 'sent_to_vendor' || po.status === 'approved'
                      
                      return (
                        <Card 
                          key={po.po_number} 
                          className={`p-2 transition-all duration-200 ${
                            isPending 
                              ? 'border-orange-300 bg-orange-50 hover:shadow-md hover:border-orange-400' 
                              : isRejected
                              ? 'border-red-300 bg-red-50 hover:shadow-md hover:border-red-400'
                              : isSent
                              ? 'border-green-300 bg-green-50 hover:shadow-md hover:border-green-400'
                              : 'hover:shadow-md hover:border-blue-200'
                          }`}
                        >
                          <div className="space-y-1">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <FileSpreadsheet className="h-3 w-3 text-red-600" />
                                  </TooltipTrigger>
                                  <TooltipContent>
                                    PDF Document
                                  </TooltipContent>
                                </Tooltip>
                                <div>
                                  <p className={`text-xs font-medium ${
                                    isPending ? 'text-orange-800' : 
                                    isRejected ? 'text-red-800' : 
                                    isSent ? 'text-green-800' : ''
                                  }`}>
                                    {po.po_number}
                                  </p>
                                  {isPending && (
                                    <p className="text-xs text-orange-600 font-medium">⏳ Awaiting Approval</p>
                                  )}
                                  {isRejected && (
                                    <p className="text-xs text-red-600 font-medium">❌ Rejected</p>
                                  )}
                                  {isSent && (
                                    <p className="text-xs text-green-600 font-medium">✅ Sent to Vendor</p>
                                  )}
                                </div>
                              </div>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <div className="cursor-help">
                                    {statusInfo.icon}
                                  </div>
                                </TooltipTrigger>
                                <TooltipContent>
                                  {statusInfo.tooltip}
                                </TooltipContent>
                              </Tooltip>
                            </div>
                            
                            <div className="flex justify-between items-center">
                              <div className="flex flex-col">
                                <p className={`text-xs font-medium ${
                                  isPending ? 'text-orange-800' : 
                                  isRejected ? 'text-red-800' : 
                                  isSent ? 'text-green-800' : 'text-muted-foreground'
                                }`}>
                                  ${po.total_amount.toLocaleString()}
                                </p>
                                <p className="text-xs text-muted-foreground truncate">
                                  {po.vendor_name}
                                </p>
                              </div>
                              
                              <div className="flex gap-1">
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      className={`h-5 w-8 p-0 text-xs transition-colors ${
                                        isPending 
                                          ? 'hover:bg-orange-100 hover:border-orange-300' 
                                          : isRejected
                                          ? 'hover:bg-red-100 hover:border-red-300'
                                          : isSent
                                          ? 'hover:bg-green-100 hover:border-green-300'
                                          : 'hover:bg-blue-50 hover:border-blue-200'
                                      }`}
                                      onClick={() => handleViewPDF(po)}
                                    >
                                      <Eye className="h-2 w-2" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>View {po.po_number}</TooltipContent>
                                </Tooltip>
                                
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      className="h-5 w-8 p-0 text-xs hover:bg-gray-100 hover:border-gray-300 transition-colors"
                                      onClick={() => handleDownload(po)}
                                    >
                                      <Download className="h-2 w-2" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent>Download {po.po_number}</TooltipContent>
                                </Tooltip>
                              </div>
                            </div>
                          </div>
                        </Card>
                      )
                    })}
                  </div>
                ) : (
                  <div className="text-center py-4">
                    <p className="text-xs text-muted-foreground">
                      {selectedDateFilter === 'all' ? "No documents for this date" : `No ${selectedDateFilter.replace('_', ' ')} documents for this date`}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </TooltipProvider>
  )
}
