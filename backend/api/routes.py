"""
REST API routes
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional
import uuid
from datetime import datetime
from loguru import logger

from models.scraping_job import (
    ScrapingJob,
    SearchCriteria,
    JobStatus
)
from models.events import UserSelectionResponse


router = APIRouter()

# In-memory job storage (replace with database in production)
jobs: dict[str, ScrapingJob] = {}


@router.post("/jobs/create")
async def create_scraping_job(
    keywords: str,
    court_name: str,
    judge_name: str,
    num_documents: Optional[int] = None,
    num_pages: Optional[int] = None
):
    """
    Create a new scraping job
    
    Args:
        keywords: Search keywords
        court_name: Court name to search
        judge_name: Judge name
        num_documents: Number of documents to scrape (optional)
        num_pages: Number of pages to scrape (optional)
    
    Returns:
        Job details including job_id
    """
    # Create search criteria
    search_criteria = SearchCriteria(
        keywords=keywords,
        court_name=court_name,
        judge_name=judge_name
    )
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # Create job
    job = ScrapingJob(
        job_id=job_id,
        search_criteria=search_criteria,
        num_documents=num_documents,
        num_pages=num_pages
    )
    
    # Store job
    jobs[job_id] = job
    
    logger.info(f"Created job {job_id}")
    
    return {
        "job_id": job_id,
        "status": job.status,
        "created_at": job.created_at.isoformat(),
        "search_criteria": search_criteria.dict()
    }


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """
    Get job status and details
    
    Args:
        job_id: Job identifier
    
    Returns:
        Job details
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    return {
        "job_id": job.job_id,
        "status": job.status,
        "summary": job.get_summary(),
        "search_criteria": job.search_criteria.dict(),
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None
    }


@router.get("/jobs/{job_id}/results")
async def get_job_results(job_id: str):
    """
    Get detailed job results
    
    Args:
        job_id: Job identifier
    
    Returns:
        Job results including documents and downloads
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    return {
        "job_id": job.job_id,
        "status": job.status,
        "documents": [doc.dict() for doc in job.documents],
        "downloads": [dl.dict() for dl in job.downloads],
        "summary": job.get_summary()
    }


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """
    Cancel a running job
    
    Args:
        job_id: Job identifier
    
    Returns:
        Cancellation confirmation
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    if job.status not in [JobStatus.PENDING, JobStatus.RUNNING, JobStatus.PAUSED]:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled")
    
    job.status = JobStatus.CANCELLED
    job.completed_at = datetime.now()
    
    logger.info(f"Cancelled job {job_id}")
    
    return {
        "job_id": job_id,
        "status": job.status,
        "message": "Job cancelled successfully"
    }


@router.get("/jobs")
async def list_jobs(
    status: Optional[JobStatus] = None,
    limit: int = 10
):
    """
    List all jobs, optionally filtered by status
    
    Args:
        status: Filter by job status (optional)
        limit: Maximum number of jobs to return
    
    Returns:
        List of jobs
    """
    job_list = list(jobs.values())
    
    # Filter by status if provided
    if status:
        job_list = [job for job in job_list if job.status == status]
    
    # Sort by creation time (newest first)
    job_list.sort(key=lambda x: x.created_at, reverse=True)
    
    # Limit results
    job_list = job_list[:limit]
    
    return {
        "jobs": [
            {
                "job_id": job.job_id,
                "status": job.status,
                "created_at": job.created_at.isoformat(),
                "summary": job.get_summary()
            }
            for job in job_list
        ],
        "total": len(job_list)
    }


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """
    Delete a job
    
    Args:
        job_id: Job identifier
    
    Returns:
        Deletion confirmation
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    del jobs[job_id]
    
    logger.info(f"Deleted job {job_id}")
    
    return {
        "job_id": job_id,
        "message": "Job deleted successfully"
    }


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_jobs": len([j for j in jobs.values() if j.status == JobStatus.RUNNING])
    }