"""
Data models for the scraping application
"""
from .events import (
    WebSocketEvent,
    StateChangeEvent,
    CourtSelectionEvent,
    TranscriptOptionsEvent,
    ProgressEvent,
    ErrorEvent,
    UserSelectionResponse
)
from .scraping_job import (
    ScrapingJob,
    SearchCriteria,
    DocumentResult,
    TranscriptEntry,
    DownloadResult
)
from .cmecf_job import (
    CMECFScrapingJob,
    CMECFDownloadResult,
    CaseNumber,
    TranscriptMatch
)

__all__ = [
    # Events
    'WebSocketEvent',
    'StateChangeEvent',
    'CourtSelectionEvent',
    'TranscriptOptionsEvent',
    'ProgressEvent',
    'ErrorEvent',
    'UserSelectionResponse',
    # Bloomberg models
    'ScrapingJob',
    'SearchCriteria',
    'DocumentResult',
    'TranscriptEntry',
    'DownloadResult',
    # CMECF models
    'CMECFScrapingJob',
    'CMECFDownloadResult',
    'CaseNumber',
    'TranscriptMatch'
]