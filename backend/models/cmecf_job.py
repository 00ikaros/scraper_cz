"""
Data models for CMECF scraping jobs and results
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class CMECFJobStatus(str, Enum):
    """Job status states"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CaseNumber(BaseModel):
    """Individual case number entry"""
    case_number: str
    status: str = "pending"  # pending, processing, completed, failed
    transcripts_found: int = 0
    transcripts_downloaded: int = 0
    errors: List[str] = []


class TranscriptMatch(BaseModel):
    """A transcript entry matching the pattern"""
    doc_number: str
    filing_date: str
    docket_text: str
    has_link: bool = True
    downloaded: bool = False
    filename: Optional[str] = None
    error: Optional[str] = None


class CMECFDownloadResult(BaseModel):
    """Result of a transcript download"""
    status: str  # SUCCESS, FAILED, NO_LINK
    case_number: str
    doc_number: str
    filename: Optional[str] = None
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class CMECFScrapingJob(BaseModel):
    """Complete CMECF scraping job"""
    job_id: str
    status: CMECFJobStatus = CMECFJobStatus.PENDING

    # Case numbers to process
    case_numbers: List[str] = []

    # Progress tracking
    current_case_index: int = 0
    cases_processed: int = 0
    total_transcripts_found: int = 0
    total_transcripts_downloaded: int = 0

    # Results per case
    case_results: Dict[str, CaseNumber] = {}

    # All download results
    downloads: List[CMECFDownloadResult] = []

    # Error tracking
    errors: List[Dict[str, Any]] = []

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def mark_started(self):
        """Mark job as started"""
        self.status = CMECFJobStatus.RUNNING
        self.started_at = datetime.now()

    def mark_completed(self):
        """Mark job as completed"""
        self.status = CMECFJobStatus.COMPLETED
        self.completed_at = datetime.now()

    def mark_failed(self, error: str):
        """Mark job as failed"""
        self.status = CMECFJobStatus.FAILED
        self.errors.append({"message": error, "timestamp": datetime.now().isoformat()})
        self.completed_at = datetime.now()

    def add_case_result(self, case_number: str, result: CaseNumber):
        """Add result for a case"""
        self.case_results[case_number] = result
        self.total_transcripts_found += result.transcripts_found
        self.total_transcripts_downloaded += result.transcripts_downloaded

    def add_download(self, download: CMECFDownloadResult):
        """Add a download result"""
        self.downloads.append(download)
        if download.status == "SUCCESS":
            self.total_transcripts_downloaded += 1

    def add_error(self, case_number: str, doc_number: str, error: str):
        """Add an error entry"""
        self.errors.append({
            "case_number": case_number,
            "doc_number": doc_number,
            "error": error,
            "timestamp": datetime.now().isoformat()
        })

    def get_summary(self) -> Dict[str, Any]:
        """Get job summary"""
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "cases_total": len(self.case_numbers),
            "cases_processed": self.cases_processed,
            "transcripts_found": self.total_transcripts_found,
            "transcripts_downloaded": self.total_transcripts_downloaded,
            "errors_count": len(self.errors),
            "duration": self._calculate_duration()
        }

    def _calculate_duration(self) -> Optional[float]:
        """Calculate job duration in seconds"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        elif self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return None

    def get_error_report(self) -> List[Dict[str, Any]]:
        """Get error report for CSV export"""
        return self.errors