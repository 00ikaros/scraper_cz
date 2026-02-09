"""
WebSocket event models for communication between backend and frontend
"""
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Any, Dict
from datetime import datetime
from enum import Enum


class EventType(str, Enum):
    """Types of WebSocket events"""
    # State changes
    STATE_CHANGE = "STATE_CHANGE"
    
    # Interactive pauses
    COURT_SELECTION = "COURT_SELECTION"
    TRANSCRIPT_OPTIONS = "TRANSCRIPT_OPTIONS"
    
    # Progress updates
    PROGRESS = "PROGRESS"
    DOWNLOAD_SUCCESS = "DOWNLOAD_SUCCESS"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    
    # Informational
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    
    # Completion
    COMPLETE = "COMPLETE"
    NO_TRANSCRIPTS = "NO_TRANSCRIPTS"
    
    # Screenshots
    SCREENSHOT = "SCREENSHOT"


class WebSocketEvent(BaseModel):
    """Base WebSocket event"""
    type: EventType
    timestamp: datetime = Field(default_factory=datetime.now)
    data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


class StateChangeEvent(BaseModel):
    """Event when scraper state changes"""
    type: Literal[EventType.STATE_CHANGE] = EventType.STATE_CHANGE
    state: str
    previous_state: Optional[str] = None
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)


class CourtSelectionEvent(BaseModel):
    """Event requesting user to select court"""
    type: Literal[EventType.COURT_SELECTION] = EventType.COURT_SELECTION
    user_input: str
    options: List[str]
    exact_matches: List[str] = []
    fuzzy_matches: List[str] = []
    message: str = "Please select the correct court from the options"
    timestamp: datetime = Field(default_factory=datetime.now)


class TranscriptEntry(BaseModel):
    """Individual transcript entry data"""
    entry_num: str
    filed_date: str
    description: str
    matches_pattern: bool
    has_download: bool
    matched_pattern: Optional[str] = None


class TranscriptOptionsEvent(BaseModel):
    """Event showing transcript options for selection"""
    type: Literal[EventType.TRANSCRIPT_OPTIONS] = EventType.TRANSCRIPT_OPTIONS
    document_title: str
    document_index: int
    total_documents: int
    entries: List[TranscriptEntry]
    message: str = "Select transcript entries to download"
    timestamp: datetime = Field(default_factory=datetime.now)


class ProgressEvent(BaseModel):
    """Progress update event"""
    type: Literal[EventType.PROGRESS] = EventType.PROGRESS
    message: str
    current: Optional[int] = None
    total: Optional[int] = None
    percentage: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ErrorEvent(BaseModel):
    """Error event"""
    type: Literal[EventType.ERROR] = EventType.ERROR
    message: str
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ScreenshotEvent(BaseModel):
    """Screenshot event for debugging"""
    type: Literal[EventType.SCREENSHOT] = EventType.SCREENSHOT
    image_base64: str
    description: str
    timestamp: datetime = Field(default_factory=datetime.now)


# User responses from frontend to backend

class UserSelectionResponse(BaseModel):
    """Base class for user selection responses"""
    action: str
    timestamp: datetime = Field(default_factory=datetime.now)


class CourtSelectionResponse(UserSelectionResponse):
    """User's court selection"""
    action: Literal["select_court", "cancel"] = "select_court"
    selected_court: Optional[str] = None


class TranscriptSelectionResponse(UserSelectionResponse):
    """User's transcript selection"""
    action: Literal["download_all", "download_selected", "skip", "manual_select"] = "download_all"
    selected_indices: Optional[List[int]] = None  # Indices of entries to download


class DocumentCountResponse(UserSelectionResponse):
    """User's document count selection"""
    action: Literal["by_count", "by_pages", "cancel"] = "by_count"
    count: Optional[int] = None  # Number of documents or pages