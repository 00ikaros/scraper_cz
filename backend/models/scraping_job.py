"""
Data models for scraping jobs and results
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class JobStatus(str, Enum):
    """Job status states"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SelectionMode(str, Enum):
    """Selection mode for processing documents"""
    MANUAL = "manual"       # Browse & pick entries manually
    AUTOMATED = "automated"  # Auto-download based on criteria


class DownloadMode(str, Enum):
    """Download mode for automated selection"""
    ALL_DOWNLOADABLE = "all_downloadable"      # Download all entries with download button
    PATTERN_MATCHES_ONLY = "pattern_matches"   # Download only entries matching patterns


class SearchCriteria(BaseModel):
    """Search criteria for Bloomberg Law"""
    keywords: str
    court_name: str
    judge_name: str
    content_type: str = "Court Dockets"
    
    # Optional filters
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class DocumentResult(BaseModel):
    """Individual document from search results"""
    title: str
    url: str
    docket_number: Optional[str] = None
    court: Optional[str] = None
    date_filed: Optional[str] = None
    
    # Processing info
    processed: bool = False
    transcripts_found: int = 0
    transcripts_downloaded: int = 0


class TranscriptEntry(BaseModel):
    """Transcript entry from docket"""
    entry_num: str
    filed_date: str
    description: str
    has_download: bool
    matched_pattern: Optional[str] = None
    
    # Download info
    downloaded: bool = False
    filename: Optional[str] = None
    file_path: Optional[str] = None
    download_timestamp: Optional[datetime] = None


class DownloadResult(BaseModel):
    """Result of a transcript download"""
    status: str  # SUCCESS, FAILED, NO_DOWNLOAD
    entry_num: str
    filename: Optional[str] = None
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ScrapingJob(BaseModel):
    """Complete scraping job"""
    job_id: str
    status: JobStatus = JobStatus.PENDING
    
    # Search criteria
    search_criteria: SearchCriteria
    
    # Job parameters
    num_documents: Optional[int] = None  # Legacy - for backward compatibility
    num_pages: Optional[int] = None

    # Selection mode parameters (NEW)
    selection_mode: SelectionMode = SelectionMode.MANUAL
    document_range_start: int = 1
    document_range_end: Optional[int] = None  # None = all results on current page
    download_mode: DownloadMode = DownloadMode.ALL_DOWNLOADABLE

    # Results
    total_results: int = 0
    documents_processed: int = 0
    transcripts_downloaded: int = 0
    
    # Data
    documents: List[DocumentResult] = []
    downloads: List[DownloadResult] = []
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Error tracking
    errors: List[str] = []
    
    def mark_started(self):
        """Mark job as started"""
        self.status = JobStatus.RUNNING
        self.started_at = datetime.now()
    
    def mark_completed(self):
        """Mark job as completed"""
        self.status = JobStatus.COMPLETED
        self.completed_at = datetime.now()
    
    def mark_failed(self, error: str):
        """Mark job as failed"""
        self.status = JobStatus.FAILED
        self.errors.append(error)
        self.completed_at = datetime.now()
    
    def add_document(self, document: DocumentResult):
        """Add a document to the job"""
        self.documents.append(document)
        self.total_results = len(self.documents)
    
    def add_download(self, download: DownloadResult):
        """Add a download result"""
        self.downloads.append(download)
        if download.status == "SUCCESS":
            self.transcripts_downloaded += 1
    
    def get_summary(self) -> Dict[str, Any]:
        """Get job summary"""
        return {
            "job_id": self.job_id,
            "status": self.status,
            "total_results": self.total_results,
            "documents_processed": self.documents_processed,
            "transcripts_downloaded": self.transcripts_downloaded,
            "errors": len(self.errors),
            "duration": self._calculate_duration()
        }
    
    def _calculate_duration(self) -> Optional[float]:
        """Calculate job duration in seconds"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return None