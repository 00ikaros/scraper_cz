"""
Main Bloomberg Law scraper orchestrator
"""
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from loguru import logger

from .browser_manager import BrowserManager
from .state_machine import StateMachine, ScraperState
from .page_handlers import Page1Handler, Page2Handler, Page3Handler

from models.scraping_job import (
    ScrapingJob,
    SearchCriteria,
    DocumentResult,
    DownloadResult
)
from config.settings import settings
from api.websocket_handler import ConnectionManager


class BloombergScraper:
    """Main scraper orchestrator"""
    
    def __init__(self, client_id: str, connection_manager: ConnectionManager):
        self.client_id = client_id
        self.connection_manager = connection_manager
        
        self.browser_manager = BrowserManager()
        self.state_machine = StateMachine()
        
        # Set up state change callback
        self.state_machine.set_state_change_callback(self._on_state_change)
        
        # Load selectors
        selectors_path = Path(__file__).parent.parent / "config" / "selectors.json"
        with open(selectors_path, 'r') as f:
            self.selectors = json.load(f)
        
        # Page handlers (initialized after browser starts)
        self.page1: Optional[Page1Handler] = None
        self.page2: Optional[Page2Handler] = None
        self.page3: Optional[Page3Handler] = None
        
        self.current_job: Optional[ScrapingJob] = None
    
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
            "Initializing browser and scraper"
        )
        
        try:
            # Initialize browser
            await self.browser_manager.initialize(headless=settings.headless_mode)
            
            # Initialize page handlers (optional custom download dir for Bloomberg)
            page = self.browser_manager.page
            bloomberg_downloads = None
            if downloads_base_dir:
                bloomberg_downloads = str(Path(downloads_base_dir) / "BLOOMBERG")
            self.page1 = Page1Handler(page, self.selectors)
            self.page2 = Page2Handler(page, self.selectors)
            self.page3 = Page3Handler(page, self.selectors, downloads_dir=bloomberg_downloads)
            
            logger.info("Scraper initialized successfully")
            
        except Exception as e:
            await self.state_machine.transition_to(ScraperState.ERROR, f"Initialization failed: {e}")
            raise
    
    async def login(self) -> bool:
        """Login to Bloomberg Law"""
        await self.state_machine.transition_to(
            ScraperState.LOGGING_IN,
            "Logging into Bloomberg Law"
        )
        
        try:
            success = await self.page1.login()
            
            if success:
                await self.connection_manager.send_info(
                    self.client_id,
                    "✓ Login successful"
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
    
    async def perform_search(self, search_criteria: SearchCriteria) -> bool:
        """
        Perform search with given criteria
        
        Args:
            search_criteria: Search parameters
        
        Returns:
            True if search successful
        """
        await self.state_machine.transition_to(
            ScraperState.SEARCHING,
            "Performing search"
        )
        
        try:
            # Perform search with interactive court selection
            success = await self.page1.perform_search(
                keywords=search_criteria.keywords,
                court_name=search_criteria.court_name,
                judge_name=search_criteria.judge_name,
                on_court_selection_needed=self._handle_court_selection
            )
            
            if success:
                await self.connection_manager.send_info(
                    self.client_id,
                    "✓ Search completed successfully"
                )
            
            return success
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            await self.connection_manager.send_error(
                self.client_id,
                f"Search error: {str(e)}"
            )
            return False
    
    async def _handle_court_selection(
        self,
        user_input: str,
        court_options: Dict[str, List[str]]
    ) -> str:
        """
        Handle interactive court selection
        
        Args:
            user_input: User's court search input
            court_options: Dictionary with exact/fuzzy matches
        
        Returns:
            Selected court name
        """
        await self.state_machine.transition_to(
            ScraperState.AWAITING_COURT_SELECTION,
            "Waiting for user to select court"
        )
        
        # Send court options to frontend
        await self.connection_manager.send_court_selection(
            self.client_id,
            user_input,
            court_options['all_options'],
            court_options['exact_matches'],
            court_options['fuzzy_matches']
        )
        
        # Wait for user response
        response = await self.connection_manager.wait_for_user_response(
            self.client_id,
            timeout=300.0  # 5 minutes
        )
        
        if not response:
            # Timeout - use first option
            logger.warning("Court selection timeout, using first option")
            return court_options['all_options'][0]
        
        selected_court = response.get('data', {}).get('selected_court')

        if not selected_court:
            # Default to first option
            selected_court = court_options['all_options'][0]

        if selected_court == '__SKIP__':
            logger.info("User skipped court selection (manual selection in browser)")
            await self.connection_manager.send_info(
                self.client_id,
                "Skipped court selection - using manual browser selection"
            )
        else:
            logger.info(f"User selected court: {selected_court}")

        return selected_court
    
    async def process_documents(self, num_documents: int = None) -> List[DocumentResult]:
        """
        Process documents from search results
        
        Args:
            num_documents: Number of documents to process (None for all on page)
        
        Returns:
            List of processed documents
        """
        await self.state_machine.transition_to(
            ScraperState.PROCESSING_RESULTS,
            "Processing search results"
        )
        
        # Wait for results page
        await self.page2.wait_for_results()
        
        # Get result links
        results = await self.page2.get_result_links()
        
        # Limit if specified
        if num_documents:
            results = results[:num_documents]
        
        await self.connection_manager.send_info(
            self.client_id,
            f"Found {len(results)} documents to process"
        )
        
        return results
    
    async def process_single_document(
        self,
        document: DocumentResult,
        document_index: int,
        total_documents: int
    ) -> DocumentResult:
        """
        Process a single document
        
        Args:
            document: DocumentResult object
            document_index: Current document index (1-based)
            total_documents: Total number of documents
        
        Returns:
            Updated DocumentResult with processing info
        """
        await self.connection_manager.send_progress(
            self.client_id,
            f"Processing document {document_index}/{total_documents}",
            document_index,
            total_documents
        )
        
        try:
            # Navigate to document
            await self.state_machine.transition_to(
                ScraperState.NAVIGATING_TO_DOCUMENT,
                f"Opening document {document_index}"
            )
            
            await self.page2.navigate_to_document(document)
            
            # Wait for docket entries
            await self.state_machine.transition_to(
                ScraperState.EXTRACTING_ENTRIES,
                "Extracting docket entries"
            )
            
            await self.page3.wait_for_docket_entries()

            # HYBRID MODE: Find ALL downloadable entries (not just pattern matches)
            downloadable_entries = await self.page3.find_downloadable_entries(pattern_matching=True)

            document.transcripts_found = len(downloadable_entries)

            if not downloadable_entries:
                await self.connection_manager.send_warning(
                    self.client_id,
                    f"No downloadable entries found in document {document_index}"
                )

                # Skip documents with no downloadable entries
                await self.page2.go_back_to_results()
                return document

            # Count how many match patterns (for info)
            pattern_matches = len([e for e in downloadable_entries if e.matched_pattern])
            await self.connection_manager.send_info(
                self.client_id,
                f"Found {len(downloadable_entries)} downloadable entries ({pattern_matches} match patterns)"
            )

            # Handle entry selection/download (user chooses from ALL downloadable entries)
            downloads = await self._handle_transcript_download(
                document,
                downloadable_entries,  # Pass ALL downloadable entries
                document_index,
                total_documents
            )
            
            document.transcripts_downloaded = len([d for d in downloads if d.status == "SUCCESS"])
            document.processed = True
            
            # Go back to results
            await self.state_machine.transition_to(
                ScraperState.RETURNING_TO_RESULTS,
                "Returning to results page"
            )
            
            await self.page2.go_back_to_results()
            
            return document
            
        except Exception as e:
            logger.error(f"Error processing document: {e}")
            await self.connection_manager.send_error(
                self.client_id,
                f"Error processing document {document_index}: {str(e)}"
            )
            
            # Try to go back
            try:
                await self.page2.go_back_to_results()
            except:
                pass
            
            return document

    async def process_documents_automated(self, job: ScrapingJob) -> List[DocumentResult]:
        """
        Process documents in AUTOMATED mode

        Args:
            job: ScrapingJob with selection mode and range parameters

        Returns:
            List of processed documents
        """
        from models.scraping_job import DownloadMode

        # Get all results
        await self.state_machine.transition_to(
            ScraperState.PROCESSING_RESULTS,
            "Processing search results"
        )

        await self.page2.wait_for_results()
        all_results = await self.page2.get_result_links()

        # Apply range filter
        start_idx = job.document_range_start - 1  # Convert to 0-based index
        end_idx = job.document_range_end if job.document_range_end else len(all_results)

        documents_to_process = all_results[start_idx:end_idx]

        await self.connection_manager.send_info(
            self.client_id,
            f"Processing {len(documents_to_process)} documents (#{job.document_range_start} to #{end_idx})"
        )

        # Process each document automatically
        for idx, doc in enumerate(documents_to_process, start=job.document_range_start):
            try:
                await self.connection_manager.send_progress(
                    self.client_id,
                    f"Processing document {idx}/{end_idx}",
                    idx,
                    end_idx
                )

                # Navigate to document
                await self.state_machine.transition_to(
                    ScraperState.NAVIGATING_TO_DOCUMENT,
                    f"Opening document {idx}"
                )

                await self.page2.navigate_to_document(doc)

                # Extract entries
                await self.state_machine.transition_to(
                    ScraperState.EXTRACTING_ENTRIES,
                    "Extracting docket entries"
                )

                await self.page3.wait_for_docket_entries()
                downloadable_entries = await self.page3.find_downloadable_entries(pattern_matching=True)

                # Filter entries based on download mode
                if job.download_mode == DownloadMode.PATTERN_MATCHES_ONLY:
                    entries_to_download = [e for e in downloadable_entries if e.matched_pattern]
                    await self.connection_manager.send_info(
                        self.client_id,
                        f"Found {len(entries_to_download)} entries matching patterns (out of {len(downloadable_entries)} downloadable)"
                    )
                else:  # ALL_DOWNLOADABLE
                    entries_to_download = downloadable_entries
                    await self.connection_manager.send_info(
                        self.client_id,
                        f"Downloading all {len(entries_to_download)} downloadable entries"
                    )

                doc.transcripts_found = len(downloadable_entries)

                # Download entries automatically
                if entries_to_download:
                    await self.state_machine.transition_to(
                        ScraperState.DOWNLOADING,
                        f"Downloading {len(entries_to_download)} entries"
                    )

                    downloads = await self.page3.download_multiple_transcripts(
                        entries_to_download,
                        doc.title
                    )

                    doc.transcripts_downloaded = len([d for d in downloads if d.status == "SUCCESS"])

                    # Notify about downloads
                    for download in downloads:
                        if download.status == "SUCCESS":
                            await self.connection_manager.send_event(
                                self.client_id,
                                {
                                    'type': 'DOWNLOAD_SUCCESS',
                                    'filename': download.filename,
                                    'entry_num': download.entry_num
                                }
                            )

                    job.transcripts_downloaded += doc.transcripts_downloaded
                    job.add_document(doc)

                # Go back to results
                await self.state_machine.transition_to(
                    ScraperState.RETURNING_TO_RESULTS,
                    "Returning to results page"
                )

                await self.page2.go_back_to_results()
                job.documents_processed += 1

            except Exception as e:
                logger.error(f"Error processing document {idx}: {e}")
                await self.connection_manager.send_error(
                    self.client_id,
                    f"Error processing document {idx}: {str(e)}"
                )
                # Continue with next document
                try:
                    await self.page2.go_back_to_results()
                except:
                    pass

        return documents_to_process

    async def _ask_user_skip_or_manual(self) -> str:
        """
        Ask user whether to skip document or manually select
        
        Returns:
            'skip' or 'manual'
        """
        # For now, auto-skip
        # TODO: Implement proper user interaction
        return "skip"
    
    async def _handle_transcript_download(
        self,
        document: DocumentResult,
        transcript_entries: List,
        document_index: int,
        total_documents: int
    ) -> List[DownloadResult]:
        """
        Handle transcript selection and download
        
        Args:
            document: Current document
            transcript_entries: List of found transcript entries
            document_index: Current document index
            total_documents: Total documents
        
        Returns:
            List of DownloadResult objects
        """
        await self.state_machine.transition_to(
            ScraperState.AWAITING_TRANSCRIPT_SELECTION,
            "Waiting for transcript selection"
        )
        
        # Format entries for frontend (HYBRID MODE: all downloadable entries)
        formatted_entries = await self.page3.get_transcript_entries_for_selection(use_hybrid_mode=True)
        
        # Send to frontend
        await self.connection_manager.send_transcript_options(
            self.client_id,
            document.title,
            formatted_entries,
            document_index,
            total_documents
        )
        
        # Wait for user response
        response = await self.connection_manager.wait_for_user_response(
            self.client_id,
            timeout=300.0
        )
        
        if not response:
            # Timeout - download all
            logger.warning("Transcript selection timeout, downloading all")
            action = "download_all"
            selected_indices = None
        else:
            action = response.get('data', {}).get('action', 'download_all')
            selected_indices = response.get('data', {}).get('selected_indices')
        
        # Determine which entries to download
        if action == "skip":
            return []
        elif action == "download_all" or not selected_indices:
            entries_to_download = transcript_entries
        else:
            entries_to_download = [transcript_entries[i] for i in selected_indices if i < len(transcript_entries)]
        
        # Download transcripts
        await self.state_machine.transition_to(
            ScraperState.DOWNLOADING,
            f"Downloading {len(entries_to_download)} transcripts"
        )
        
        async def progress_callback(current, total, entry_num):
            await self.connection_manager.send_progress(
                self.client_id,
                f"Downloading entry {entry_num} ({current}/{total})",
                current,
                total
            )
        
        downloads = await self.page3.download_multiple_transcripts(
            entries_to_download,
            document.title,
            on_progress=progress_callback
        )
        
        # Notify about successful downloads
        for download in downloads:
            if download.status == "SUCCESS":
                await self.connection_manager.send_event(
                    self.client_id,
                    {
                        'type': 'DOWNLOAD_SUCCESS',
                        'filename': download.filename,
                        'entry_num': download.entry_num
                    }
                )
        
        return downloads
    
    async def run_scraping_job(
        self,
        job: ScrapingJob,
        downloads_base_dir: Optional[str] = None,
    ) -> ScrapingJob:
        """
        Run complete scraping job

        Args:
            job: ScrapingJob with search criteria
            downloads_base_dir: Optional base folder for PDFs (BLOOMBERG subfolder under it)

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
            
            # Search
            if not await self.perform_search(job.search_criteria):
                job.mark_failed("Search failed")
                return job
            
            # Process documents based on selection mode
            from models.scraping_job import SelectionMode

            if job.selection_mode == SelectionMode.AUTOMATED:
                # AUTOMATED MODE: Process range automatically
                await self.connection_manager.send_info(
                    self.client_id,
                    f"Automated mode: Processing documents {job.document_range_start}-{job.document_range_end or 'all'}"
                )
                documents = await self.process_documents_automated(job)
            else:
                # MANUAL MODE: Process with user interaction (legacy)
                documents = await self.process_documents(job.num_documents)

                for idx, doc in enumerate(documents, 1):
                    processed_doc = await self.process_single_document(doc, idx, len(documents))
                    job.add_document(processed_doc)
                    job.documents_processed += 1
            
            # Complete
            await self.state_machine.transition_to(
                ScraperState.COMPLETED,
                "Scraping completed successfully"
            )
            
            job.mark_completed()
            
            # Send completion message
            await self.connection_manager.send_complete(
                self.client_id,
                f"✓ Scraping complete! Downloaded {job.transcripts_downloaded} transcripts from {job.documents_processed} documents",
                job.get_summary()
            )
            
            return job
            
        except Exception as e:
            logger.error(f"Scraping job failed: {e}")
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
        logger.info("Cleaning up scraper resources")
        await self.browser_manager.cleanup()
        self.state_machine.reset()