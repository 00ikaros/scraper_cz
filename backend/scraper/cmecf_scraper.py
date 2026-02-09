"""
Main CMECF scraper orchestrator
"""
import asyncio
import json
import random
from pathlib import Path
from typing import Optional, List, Dict, Any
from loguru import logger

from .browser_manager import BrowserManager
from .state_machine import StateMachine, ScraperState
from .cmecf_page_handlers import (
    CMECFLoginHandler,
    CMECFCaseEntryHandler,
    CMECFResultsHandler,
    CMECFDocumentDetailHandler
)

from models.cmecf_job import (
    CMECFScrapingJob,
    CMECFDownloadResult,
    CaseNumber,
    TranscriptMatch
)
from config.settings import settings
from api.websocket_handler import ConnectionManager


class CMECFScraper:
    """Main CMECF scraper orchestrator"""

    def __init__(self, client_id: str, connection_manager: ConnectionManager):
        self.client_id = client_id
        self.connection_manager = connection_manager

        self.browser_manager = BrowserManager()
        self.state_machine = StateMachine()

        # Set up state change callback
        self.state_machine.set_state_change_callback(self._on_state_change)

        # Load CMECF selectors
        selectors_path = Path(__file__).parent.parent / "config" / "cmecf_selectors.json"
        with open(selectors_path, 'r') as f:
            self.selectors = json.load(f)

        # Page handlers (initialized after browser starts)
        self.login_handler: Optional[CMECFLoginHandler] = None
        self.case_entry_handler: Optional[CMECFCaseEntryHandler] = None
        self.results_handler: Optional[CMECFResultsHandler] = None
        self.document_handler: Optional[CMECFDocumentDetailHandler] = None

        self.current_job: Optional[CMECFScrapingJob] = None
        self.results_page_url: str = ""

    async def _on_state_change(self, state: ScraperState, previous_state: Optional[ScraperState], message: str):
        """Callback for state changes - sends to frontend"""
        await self.connection_manager.send_state_change(
            self.client_id,
            state.value,
            message,
            previous_state.value if previous_state else None
        )

    async def initialize(self, downloads_base_dir: Optional[str] = None):
        """Initialize scraper and browser. Optionally set download dir (folder for PDFs)."""
        await self.state_machine.transition_to(
            ScraperState.INITIALIZING,
            "Initializing browser and CMECF scraper"
        )

        try:
            # Initialize browser
            await self.browser_manager.initialize(headless=settings.headless_mode)

            # Initialize page handlers
            page = self.browser_manager.page
            if downloads_base_dir:
                downloads_dir = str(Path(downloads_base_dir) / "PACER")
            else:
                downloads_dir = settings.pacer_downloads_dir

            self.login_handler = CMECFLoginHandler(page, self.selectors)
            self.case_entry_handler = CMECFCaseEntryHandler(page, self.selectors)
            self.results_handler = CMECFResultsHandler(page, self.selectors)
            self.document_handler = CMECFDocumentDetailHandler(page, self.selectors, downloads_dir)

            logger.info("CMECF Scraper initialized successfully")

        except Exception as e:
            await self.state_machine.transition_to(ScraperState.ERROR, f"Initialization failed: {e}")
            raise

    async def login(self) -> bool:
        """Login to CMECF"""
        await self.state_machine.transition_to(
            ScraperState.LOGGING_IN,
            "Logging into CMECF (PACER)"
        )

        try:
            success = await self.login_handler.ensure_logged_in()

            if success:
                await self.connection_manager.send_info(
                    self.client_id,
                    "Login successful - on CMECF docket page"
                )
            else:
                await self.connection_manager.send_error(
                    self.client_id,
                    "Login failed - please check credentials"
                )

            return success

        except Exception as e:
            logger.error(f"Login error: {e}")
            await self.connection_manager.send_error(
                self.client_id,
                f"Login error: {str(e)}"
            )
            return False

    async def process_case(self, case_number: str) -> CaseNumber:
        """
        Process a single case number

        Args:
            case_number: The case number to process

        Returns:
            CaseNumber with results
        """
        case_result = CaseNumber(case_number=case_number)

        try:
            await self.state_machine.transition_to(
                ScraperState.SEARCHING,
                f"Processing case: {case_number}"
            )

            await self.connection_manager.send_info(
                self.client_id,
                f"Processing case: {case_number}"
            )

            # Submit case number
            if not await self.case_entry_handler.submit_case_number(case_number):
                case_result.status = "failed"
                case_result.errors.append("Failed to submit case number")
                return case_result

            # Wait for and verify results page
            if not await self.results_handler.wait_for_results_page():
                case_result.status = "failed"
                case_result.errors.append("Failed to load results page")
                return case_result

            # Store results page URL
            self.results_page_url = await self.results_handler.get_results_page_url()
            logger.info(f"Results page URL: {self.results_page_url}")

            # Find transcript entries
            await self.state_machine.transition_to(
                ScraperState.EXTRACTING_ENTRIES,
                "Finding transcript entries"
            )

            transcript_entries = await self.results_handler.find_transcript_entries()
            case_result.transcripts_found = len(transcript_entries)

            if not transcript_entries:
                await self.connection_manager.send_info(
                    self.client_id,
                    f"No matching transcripts found for case {case_number}"
                )
                case_result.status = "completed"
                return case_result

            await self.connection_manager.send_info(
                self.client_id,
                f"Found {len(transcript_entries)} transcript(s) for case {case_number}"
            )

            # Process each transcript entry
            for idx, entry in enumerate(transcript_entries):
                await self.connection_manager.send_progress(
                    self.client_id,
                    f"Downloading transcript {idx + 1}/{len(transcript_entries)} (#{entry.doc_number})",
                    idx + 1,
                    len(transcript_entries)
                )

                download_result = await self.process_transcript_entry(case_number, entry)

                if download_result.status == "SUCCESS":
                    case_result.transcripts_downloaded += 1
                    entry.downloaded = True
                    entry.filename = download_result.filename
                else:
                    entry.error = download_result.error_message
                    case_result.errors.append(
                        f"Doc #{entry.doc_number}: {download_result.error_message}"
                    )

                # Add to job downloads
                if self.current_job:
                    self.current_job.add_download(download_result)

                # Navigate back to results if more entries to process
                if idx < len(transcript_entries) - 1:
                    await self._navigate_back_to_results(case_number)

                    # Random delay between documents
                    await self._random_delay()

            case_result.status = "completed"
            return case_result

        except Exception as e:
            logger.error(f"Error processing case {case_number}: {e}")
            case_result.status = "failed"
            case_result.errors.append(str(e))
            return case_result

    async def process_transcript_entry(
        self,
        case_number: str,
        entry: TranscriptMatch
    ) -> CMECFDownloadResult:
        """
        Process a single transcript entry (click, view document, download)

        Args:
            case_number: The case number
            entry: The transcript entry to process

        Returns:
            CMECFDownloadResult
        """
        try:
            # Check if entry has a link
            if not entry.has_link:
                logger.warning(f"Document #{entry.doc_number} has no clickable link")
                return CMECFDownloadResult(
                    status="NO_LINK",
                    case_number=case_number,
                    doc_number=entry.doc_number,
                    error_message="Document has no clickable link"
                )

            await self.state_machine.transition_to(
                ScraperState.NAVIGATING_TO_DOCUMENT,
                f"Opening document #{entry.doc_number}"
            )

            # Click the document number (navigates in same page)
            if not await self.results_handler.click_document_number(entry.doc_number):
                return CMECFDownloadResult(
                    status="FAILED",
                    case_number=case_number,
                    doc_number=entry.doc_number,
                    error_message="Failed to click document link"
                )

            await self.state_machine.transition_to(
                ScraperState.DOWNLOADING,
                f"Downloading document #{entry.doc_number}"
            )

            # Download the document
            result = await self.document_handler.download_document(case_number, entry.doc_number)

            if result['status'] == 'SUCCESS':
                await self.connection_manager.send_event(
                    self.client_id,
                    {
                        'type': 'DOWNLOAD_SUCCESS',
                        'filename': result['filename'],
                        'case_number': case_number,
                        'doc_number': entry.doc_number
                    }
                )

                # Brief wait after download
                logger.info("Download complete, waiting 5 seconds...")
                await asyncio.sleep(5)

                return CMECFDownloadResult(
                    status="SUCCESS",
                    case_number=case_number,
                    doc_number=entry.doc_number,
                    filename=result['filename'],
                    file_path=result['filepath']
                )
            else:
                return CMECFDownloadResult(
                    status="FAILED",
                    case_number=case_number,
                    doc_number=entry.doc_number,
                    error_message=result.get('error', 'Unknown error')
                )

        except Exception as e:
            logger.error(f"Error processing transcript entry: {e}")
            return CMECFDownloadResult(
                status="FAILED",
                case_number=case_number,
                doc_number=entry.doc_number,
                error_message=str(e)
            )

    async def _navigate_back_to_results(self, case_number: str):
        """
        Return to results page: go back twice, verify we're on results.
        If we land on an error page (e.g. "Incomplete request"), recover by
        re-entering the case number and loading results again.
        """
        await self.state_machine.transition_to(
            ScraperState.RETURNING_TO_RESULTS,
            "Returning to results page"
        )

        # Use browser back twice (PDF/doc view → document detail → results)
        try:
            await self.results_handler.go_back_to_results()
        except Exception as e:
            logger.warning(f"Go-back failed: {e}, will try recovery")

        await asyncio.sleep(1)

        # Double-check we're on the results page
        if await self.results_handler.is_on_results_page():
            logger.info("Navigated back to results page")
            return

        # We're not on results (e.g. "Incomplete request") – recover
        if await self.results_handler.is_on_error_page():
            logger.warning("Landed on error page after back; re-entering case number to recover")
        else:
            logger.warning("Not on results page after back; re-entering case number to recover")

        await self._recover_to_results_page(case_number)

    async def _recover_to_results_page(self, case_number: str):
        """
        Recover to results page by going to case entry, re-submitting case number,
        and waiting for results. Used when back-navigation lands on an error page.
        """
        await self.connection_manager.send_info(
            self.client_id,
            f"Re-entering case {case_number} to return to results..."
        )
        await self._navigate_to_case_entry()
        await asyncio.sleep(1)
        if not await self.case_entry_handler.submit_case_number(case_number):
            raise RuntimeError(f"Recovery failed: could not re-submit case number {case_number}")
        if not await self.results_handler.wait_for_results_page():
            raise RuntimeError(f"Recovery failed: results page did not load for {case_number}")
        self.results_page_url = await self.results_handler.get_results_page_url()
        logger.info("Recovered to results page")

    async def _random_delay(self):
        """Wait a random time between documents"""
        wait_times = self.selectors.get('wait_times', {}).get('between_documents', {})
        min_wait = wait_times.get('min', 5000) / 1000
        max_wait = wait_times.get('max', 10000) / 1000

        delay = random.uniform(min_wait, max_wait)
        logger.debug(f"Waiting {delay:.1f} seconds before next document...")

        import asyncio
        await asyncio.sleep(delay)

    async def _navigate_to_case_entry(self):
        """Navigate back to case entry page"""
        try:
            await self.browser_manager.page.goto(
                settings.cmecf_docket_url,
                wait_until='networkidle'
            )
        except Exception as e:
            logger.error(f"Error navigating to case entry: {e}")
            raise

    async def run_scraping_job(
        self,
        job: CMECFScrapingJob,
        downloads_base_dir: Optional[str] = None,
    ) -> CMECFScrapingJob:
        """
        Run complete CMECF scraping job

        Args:
            job: CMECFScrapingJob with case numbers
            downloads_base_dir: Optional base folder for PDFs (PACER subfolder created under it)

        Returns:
            Updated job with results
        """
        self.current_job = job
        job.mark_started()

        try:
            # Initialize (with optional download path)
            await self.initialize(downloads_base_dir=downloads_base_dir)

            # Login
            if not await self.login():
                job.mark_failed("Login failed")
                return job

            # Process each case number
            total_cases = len(job.case_numbers)

            for idx, case_number in enumerate(job.case_numbers):
                job.current_case_index = idx

                await self.connection_manager.send_progress(
                    self.client_id,
                    f"Processing case {idx + 1}/{total_cases}: {case_number}",
                    idx + 1,
                    total_cases
                )

                # Navigate to case entry page (except for first case)
                if idx > 0:
                    await self._navigate_to_case_entry()

                # Process the case
                case_result = await self.process_case(case_number)
                job.add_case_result(case_number, case_result)
                job.cases_processed += 1

                # Log any errors for this case
                for error in case_result.errors:
                    job.add_error(case_number, "", error)

                # Random delay between cases
                if idx < total_cases - 1:
                    await self._random_delay()

            # Complete
            await self.state_machine.transition_to(
                ScraperState.COMPLETED,
                "CMECF scraping completed"
            )

            job.mark_completed()

            # Send completion message
            await self.connection_manager.send_complete(
                self.client_id,
                f"Scraping complete! Downloaded {job.total_transcripts_downloaded} transcripts from {job.cases_processed} cases",
                job.get_summary()
            )

            return job

        except Exception as e:
            logger.error(f"CMECF scraping job failed: {e}")
            job.mark_failed(str(e))

            await self.connection_manager.send_error(
                self.client_id,
                f"Scraping job failed: {str(e)}"
            )

            return job

        finally:
            await self.cleanup()

    async def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up CMECF scraper resources")
        await self.browser_manager.cleanup()
        self.state_machine.reset()
