"""
FastAPI application entry point
Bloomberg Law & CMECF Scraper Backend
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional, List
import os
import uvicorn
from pathlib import Path
from loguru import logger

from config.settings import settings
from api.routes import router
from api.auth import (
    login as auth_login,
    get_current_user,
    get_download_path,
    set_download_path,
)
from api.websocket_handler import websocket_endpoint, connection_manager
from scraper.bloomberg_scraper import BloombergScraper
from scraper.cmecf_scraper import CMECFScraper
from models.scraping_job import ScrapingJob
from models.cmecf_job import CMECFScrapingJob
import asyncio


# Store active scraping tasks
active_tasks = {}


# Request model for Bloomberg scraping
class ScrapeRequest(BaseModel):
    keywords: str
    court_name: str
    judge_name: str
    client_id: str
    # Legacy parameter (backward compatibility)
    num_documents: Optional[int] = None
    # New selection mode parameters
    selection_mode: str = "manual"
    document_range_start: int = 1
    document_range_end: Optional[int] = None
    download_mode: str = "all_downloadable"
    download_path: Optional[str] = None


# Request model for CMECF scraping
class CMECFScrapeRequest(BaseModel):
    case_numbers: List[str]
    client_id: str
    download_path: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class SettingsUpdateRequest(BaseModel):
    download_path: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info("Starting Document Scraper API (Bloomberg Law & CMECF)")
    logger.info(f"Frontend served at: http://{settings.app_host}:{settings.app_port}")
    logger.info(f"API docs at: http://{settings.app_host}:{settings.app_port}/docs")
    yield
    logger.info("Shutting down Document Scraper API")


# Create FastAPI app
app = FastAPI(
    title="Document Scraper API",
    description="Interactive web scraping for Bloomberg Law and CMECF (PACER) transcripts",
    version="1.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (frontend)
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")
    logger.info(f"Frontend directory mounted: {frontend_dir}")


# Include API routes
app.include_router(router, prefix="/api")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Avoid 404 when the browser requests a tab icon."""
    return Response(status_code=204)


@app.get("/")
async def root():
    """Serve frontend"""
    frontend_index = frontend_dir / "index.html"
    if frontend_index.exists():
        return FileResponse(str(frontend_index))
    return {"message": "Document Scraper API", "status": "running"}


@app.post("/api/auth/login")
async def login(request: LoginRequest):
    """Login with username/password. Returns token on success."""
    token = auth_login(request.username, request.password)
    if not token:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"success": True, "token": token, "username": request.username}


@app.get("/api/auth/status")
async def auth_status(username: str = Depends(get_current_user)):
    """Requires valid token. Returns current user."""
    return {"authenticated": True, "username": username}


@app.get("/api/settings")
async def get_settings(username: str = Depends(get_current_user)):
    """Get app settings (e.g. download path)."""
    return {"download_path": get_download_path() or ""}


@app.put("/api/settings")
async def update_settings(
    body: SettingsUpdateRequest,
    username: str = Depends(get_current_user),
):
    """Update download path."""
    set_download_path(body.download_path or None)
    return {"download_path": get_download_path() or ""}


@app.websocket("/ws")
async def websocket_route(
    websocket: WebSocket,
    client_id: str = None,
    token: str = None,
):
    """WebSocket endpoint; requires token query param for auth."""
    from api.auth import _validate_token
    if not token or not _validate_token(token):
        await websocket.close(code=4401)
        return
    if not client_id:
        import uuid
        client_id = str(uuid.uuid4())
    await websocket_endpoint(websocket, client_id)


@app.post("/api/scrape/start")
async def start_scraping(request: ScrapeRequest, username: str = Depends(get_current_user)):
    """
    Start a scraping job

    Args:
        request: Scrape request with keywords, court_name, judge_name, client_id, num_documents

    Returns:
        Job information
    """
    from models.scraping_job import SearchCriteria

    try:
        # Create search criteria
        search_criteria = SearchCriteria(
            keywords=request.keywords,
            court_name=request.court_name,
            judge_name=request.judge_name
        )

        # Create job
        import uuid
        job_id = str(uuid.uuid4())

        from models.scraping_job import SelectionMode, DownloadMode

        job = ScrapingJob(
            job_id=job_id,
            search_criteria=search_criteria,
            # Legacy
            num_documents=request.num_documents,
            # New selection mode
            selection_mode=SelectionMode(request.selection_mode),
            document_range_start=request.document_range_start,
            document_range_end=request.document_range_end,
            download_mode=DownloadMode(request.download_mode)
        )

        # Create scraper
        scraper = BloombergScraper(request.client_id, connection_manager)
        download_base = request.download_path or get_download_path()

        # Start scraping in background (pass download path to scraper)
        task = asyncio.create_task(scraper.run_scraping_job(job, downloads_base_dir=download_base))
        active_tasks[job_id] = task

        logger.info(f"Started scraping job {job_id} for client {request.client_id}")

        return {
            "status": "started",
            "job_id": job_id,
            "message": "Scraping job started"
        }

    except Exception as e:
        logger.error(f"Error starting scraping job: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.post("/api/cmecf/scrape/start")
async def start_cmecf_scraping(request: CMECFScrapeRequest, username: str = Depends(get_current_user)):
    """
    Start a CMECF scraping job

    Args:
        request: CMECF scrape request with case_numbers and client_id

    Returns:
        Job information
    """
    try:
        import uuid
        job_id = str(uuid.uuid4())

        # Create job
        job = CMECFScrapingJob(
            job_id=job_id,
            case_numbers=request.case_numbers
        )

        # Create scraper
        scraper = CMECFScraper(request.client_id, connection_manager)
        download_base = request.download_path or get_download_path()

        # Start scraping in background (pass download path to scraper)
        task = asyncio.create_task(scraper.run_scraping_job(job, downloads_base_dir=download_base))
        active_tasks[job_id] = task

        logger.info(f"Started CMECF scraping job {job_id} for client {request.client_id}")
        logger.info(f"Processing {len(request.case_numbers)} case numbers")

        return {
            "status": "started",
            "job_id": job_id,
            "message": f"CMECF scraping job started for {len(request.case_numbers)} case(s)"
        }

    except Exception as e:
        logger.error(f"Error starting CMECF scraping job: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "app": "Document Scraper (Bloomberg & CMECF)",
        "version": "1.1.0"
    }


def main():
    """Run the application"""
    logger.info("Starting Document Scraper API...")
    # Use PORT from environment (e.g. Railway, Heroku) when set
    port = int(os.environ.get("PORT", settings.app_port))
    host = "0.0.0.0" if port != settings.app_port else settings.app_host

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()