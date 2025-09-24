"""
WebSocket routes for real-time PO workflow notifications
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from app.websocket.connection_manager import manager
from app.utils.auth_utils import get_current_user
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str, token: str = None):
    """WebSocket endpoint for project-specific PO workflow notifications"""
    try:
        # Authenticate user from token
        if not token:
            await websocket.close(code=4001, reason="Authentication token required")
            return
        
        user = await get_current_user(token)
        if not user:
            await websocket.close(code=4001, reason="Invalid token")
            return
        
        # Connect WebSocket
        await manager.connect(websocket, project_id, user["id"])
        
        # Send initial connection confirmation
        await manager.send_personal_message(
            json.dumps({
                "type": "connection_established",
                "project_id": project_id,
                "message": "Connected to PO workflow notifications",
                "user_id": user["id"]
            }),
            websocket
        )
        
        # Keep connection alive and handle incoming messages
        try:
            while True:
                data = await websocket.receive_text()
                # Handle any incoming messages if needed (like heartbeat)
                logger.info(f"Received WebSocket message from user {user['id']}: {data}")
        except WebSocketDisconnect:
            manager.disconnect(websocket)
            logger.info(f"WebSocket disconnected for user {user['id']}")
        
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close(code=4000, reason="Internal server error")
