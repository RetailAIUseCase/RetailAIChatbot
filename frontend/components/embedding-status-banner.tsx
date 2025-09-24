import React, { useState, useEffect } from 'react';
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Loader2, CheckCircle, AlertCircle } from "lucide-react";

interface EmbeddingStatus {
  total: number;
  processing: number;
  completed: number;
  failed: number;
  pending: number;
}

interface EmbeddingStatusBannerProps {
  projectId: string;
  onStatusChange?: (isProcessing: boolean) => void;
}

export function EmbeddingStatusBanner({ projectId, onStatusChange }: EmbeddingStatusBannerProps) {
  const [status, setStatus] = useState<EmbeddingStatus | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "https://retail-ai-chatbot.onrender.com"
  const fetchStatus = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(
        `${API_BASE_URL}/documents/project/${projectId}/embedding-status`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Accept': 'application/json'
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setStatus(data.embedding_status);
        const processing = data.is_processing;
        setIsProcessing(processing);
        onStatusChange?.(processing);
        setError(null);
      } else {
        setError('Failed to fetch status');
      }
    } catch (err) {
      setError('Network error');
    }
  };

  useEffect(() => {
    if (!projectId) return;
    // Initial fetch
    fetchStatus();
  }, [projectId]);

  useEffect(() => {
    if (!projectId || !isProcessing) return;

    const interval = setInterval(() => {
      fetchStatus();
    }, 3000);

    return () => clearInterval(interval);
  }, [projectId, isProcessing]);

  if (error || !status || status.total === 0) return null;

  const progressPercentage = status.total > 0 
    ? Math.round(((status.completed + status.failed) / status.total) * 100) 
    : 0;

  if (!isProcessing && status.completed === status.total) return null;

  return (
    <Card className="mx-4 mb-4 p-4 bg-blue-50 border-blue-200">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {isProcessing ? (
            <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
          ) : status.failed > 0 ? (
            <AlertCircle className="h-4 w-4 text-orange-500" />
          ) : (
            <CheckCircle className="h-4 w-4 text-green-500" />
          )}
          
          <span className="font-medium text-sm">
            {isProcessing ? 'Processing Documents...' : 'Processing Complete'}
          </span>
        </div>
        
        <div className="flex gap-2">
          {status.processing > 0 && (
            <Badge variant="secondary" className="bg-blue-100 text-blue-700">
              {status.processing} processing
            </Badge>
          )}
          {status.pending > 0 && (
            <Badge variant="outline">
              {status.pending} pending
            </Badge>
          )}
          {status.completed > 0 && (
            <Badge variant="secondary" className="bg-green-100 text-green-700">
              {status.completed} completed
            </Badge>
          )}
          {status.failed > 0 && (
            <Badge variant="destructive">
              {status.failed} failed
            </Badge>
          )}
        </div>
      </div>
      
      <Progress value={progressPercentage} className="h-2" />
      <p className="text-xs text-gray-600 mt-1">
        {status.completed + status.failed} of {status.total} documents processed
      </p>
    </Card>
  );
}
