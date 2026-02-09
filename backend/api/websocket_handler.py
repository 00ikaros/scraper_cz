"""
WebSocket handler for real-time communication with frontend
"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any, Optional
import asyncio
import json
from datetime import datetime
from loguru import logger

from models.events import (
    WebSocketEvent,
    EventType,
    StateChangeEvent,
    CourtSelectionEvent,
    TranscriptOptionsEvent,
    ProgressEvent,
    ErrorEvent,
    UserSelectionResponse
)


class ConnectionManager:
    """Manages WebSocket connections"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.pending_responses: Dict[str, asyncio.Future] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept and store WebSocket connection"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Client {client_id} connected")
    
    def disconnect(self, client_id: str):
        """Remove WebSocket connection"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Client {client_id} disconnected")
    
    async def send_event(self, client_id: str, event: WebSocketEvent):
        """Send event to specific client (accepts Pydantic model or plain dict)"""
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            try:
                if isinstance(event, dict):
                    event_dict = event.copy()
                else:
                    event_dict = event.dict() if hasattr(event, 'dict') else event.model_dump()
                
                # Convert datetime objects to ISO format strings
                event_dict = self._serialize_datetime(event_dict)
                
                await websocket.send_json(event_dict)
                logger.debug(f"Sent event {event_dict.get('type')} to {client_id}")
            except Exception as e:
                logger.error(f"Error sending event to {client_id}: {e}")
    
    async def send_state_change(self, client_id: str, state: str, message: str, previous_state: Optional[str] = None):
        """Send state change event"""
        event = StateChangeEvent(
            state=state,
            message=message,
            previous_state=previous_state
        )
        await self.send_event(client_id, event)
    
    async def send_court_selection(self, client_id: str, user_input: str, options: list, exact_matches: list = None, fuzzy_matches: list = None):
        """Send court selection request"""
        event = CourtSelectionEvent(
            user_input=user_input,
            options=options,
            exact_matches=exact_matches or [],
            fuzzy_matches=fuzzy_matches or []
        )
        await self.send_event(client_id, event)
    
    async def send_transcript_options(self, client_id: str, document_title: str, entries: list, document_index: int = 1, total_documents: int = 1):
        """Send transcript options for selection"""
        event = TranscriptOptionsEvent(
            document_title=document_title,
            entries=entries,
            document_index=document_index,
            total_documents=total_documents
        )
        await self.send_event(client_id, event)
    
    async def send_progress(self, client_id: str, message: str, current: int = None, total: int = None):
        """Send progress update"""
        percentage = None
        if current is not None and total is not None and total > 0:
            percentage = (current / total) * 100
        
        event = ProgressEvent(
            message=message,
            current=current,
            total=total,
            percentage=percentage
        )
        await self.send_event(client_id, event)
    
    async def send_error(self, client_id: str, message: str, error_code: str = None, details: dict = None):
        """Send error event"""
        event = ErrorEvent(
            message=message,
            error_code=error_code,
            details=details
        )
        await self.send_event(client_id, event)
    
    async def send_info(self, client_id: str, message: str):
        """Send info message"""
        event = WebSocketEvent(
            type=EventType.INFO,
            message=message
        )
        await self.send_event(client_id, event)
    
    async def send_warning(self, client_id: str, message: str):
        """Send warning message"""
        event = WebSocketEvent(
            type=EventType.WARNING,
            message=message
        )
        await self.send_event(client_id, event)
    
    async def send_complete(self, client_id: str, message: str, data: dict = None):
        """Send completion event"""
        event = WebSocketEvent(
            type=EventType.COMPLETE,
            message=message,
            data=data
        )
        await self.send_event(client_id, event)
    
    async def wait_for_user_response(self, client_id: str, timeout: float = 300.0) -> Optional[Dict[str, Any]]:
        """
        Wait for user response with timeout
        
        Args:
            client_id: Client identifier
            timeout: Timeout in seconds (default 5 minutes)
        
        Returns:
            User response data or None if timeout
        """
        # Create a future for this response
        future = asyncio.get_event_loop().create_future()
        self.pending_responses[client_id] = future
        
        try:
            # Wait for response with timeout
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for user response from {client_id}")
            return None
        finally:
            # Clean up
            if client_id in self.pending_responses:
                del self.pending_responses[client_id]
    
    def set_user_response(self, client_id: str, response: Dict[str, Any]):
        """
        Set user response to resolve waiting future
        
        Args:
            client_id: Client identifier
            response: User response data
        """
        if client_id in self.pending_responses:
            future = self.pending_responses[client_id]
            if not future.done():
                future.set_result(response)
                logger.debug(f"User response received from {client_id}")
    
    def _serialize_datetime(self, obj: Any) -> Any:
        """Recursively serialize datetime objects to ISO format strings"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {key: self._serialize_datetime(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_datetime(item) for item in obj]
        return obj


# Global connection manager instance
connection_manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """
    WebSocket endpoint handler
    
    Args:
        websocket: FastAPI WebSocket connection
        client_id: Unique client identifier
    """
    await connection_manager.connect(websocket, client_id)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            logger.debug(f"Received from {client_id}: {data}")
            
            # Handle different message types
            message_type = data.get("type")
            
            if message_type == "user_response":
                # User responded to a request
                connection_manager.set_user_response(client_id, data.get("data"))
            
            elif message_type == "ping":
                # Heartbeat
                await websocket.send_json({"type": "pong"})
            
            else:
                logger.warning(f"Unknown message type from {client_id}: {message_type}")
    
    except WebSocketDisconnect:
        connection_manager.disconnect(client_id)
        logger.info(f"Client {client_id} disconnected")
    
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
        connection_manager.disconnect(client_id)