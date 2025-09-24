"""
WebSocket connection manager for real-time PO workflow notifications
"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Store connections by project_id
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Store user info for each connection
        self.connection_users: Dict[WebSocket, Dict] = {}
    
    async def connect(self, websocket: WebSocket, project_id: str, user_id: int):
        """Connect a WebSocket to a specific project"""
        await websocket.accept()
        
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
        
        self.active_connections[project_id].append(websocket)
        self.connection_users[websocket] = {
            "user_id": user_id,
            "project_id": project_id
        }
        
        logger.info(f"WebSocket connected for user {user_id} in project {project_id}")
    
    def disconnect(self, websocket: WebSocket):
        """Disconnect a WebSocket"""
        user_info = self.connection_users.get(websocket)
        if user_info:
            project_id = user_info["project_id"]
            if project_id in self.active_connections:
                if websocket in self.active_connections[project_id]:
                    self.active_connections[project_id].remove(websocket)
                    if not self.active_connections[project_id]:
                        del self.active_connections[project_id]
            
            del self.connection_users[websocket]
            logger.info(f"WebSocket disconnected for user {user_info['user_id']}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send message to a specific WebSocket"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
    
    async def broadcast_to_project(self, project_id: str, message: Dict):
        """Broadcast message to all connections in a project"""
        if project_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[project_id]:
                try:
                    await connection.send_text(json.dumps(message))
                except WebSocketDisconnect:
                    disconnected.append(connection)
                except Exception as e:
                    logger.error(f"Error broadcasting to project {project_id}: {e}")
                    disconnected.append(connection)
            
            # Remove disconnected connections
            for connection in disconnected:
                self.disconnect(connection)
    
    async def notify_workflow_progress(self, project_id: str, workflow_id: str, step: str, message: str):
        """Notify about workflow progress"""
        notification = {
            "type": "workflow_progress",
            "project_id": project_id,
            "workflow_id": workflow_id,
            "step": step,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.broadcast_to_project(project_id, notification)
    
    async def notify_workflow_complete(self, project_id: str, workflow_id: str, message: str):
        """Notify that workflow is complete"""
        notification = {
            "type": "workflow_complete",
            "project_id": project_id,
            "workflow_id": workflow_id,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.broadcast_to_project(project_id, notification)
    
    async def notify_workflow_error(self, project_id: str, workflow_id: str, error: str):
        """Notify about workflow error"""
        notification = {
            "type": "workflow_error",
            "project_id": project_id,
            "workflow_id": workflow_id,
            "error": error,
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.broadcast_to_project(project_id, notification)
    
    async def notify_po_status_update(self, project_id: str, po_number: str, status: str, message: str = None):
        """Notify about PO status updates"""
        notification = {
            "type": "po_status_update",
            "project_id": project_id,
            "po_number": po_number,
            "status": status,
            "message": message or f"PO {po_number} status updated to {status}",
            "timestamp": datetime.utcnow().isoformat()
        }
        await self.broadcast_to_project(project_id, notification)

# Global connection manager
manager = ConnectionManager()
