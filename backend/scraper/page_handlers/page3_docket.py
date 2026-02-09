"""
Page 3 Handler: Docket Entries and Transcript Downloads
"""
import re
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from loguru import logger
from playwright.async_api import Page, Download

from models.scraping_job import TranscriptEntry, DownloadResult
from config.settings import settings
from utils.helpers import sanitize_filename, extract_text_preview


class Page3Handler:
    """Handles Bloomberg Law docket entries page"""

    def __init__(self, page: Page, selectors: dict, downloads_dir: Optional[str] = None):
        self.page = page
        self.selectors = selectors.get('page3_docket', {})
        self.transcript_patterns = selectors.get('transcript_patterns', [])
        self._downloads_dir = downloads_dir  # override from settings when set
    
    async def wait_for_docket_entries(self):
        """Wait for docket entries section to load"""
        logger.info("Waiting for docket entries to load")

        try:
            docket_section = self.selectors['docket_section']
            await self.page.wait_for_selector(docket_section, timeout=30000)

            # Also wait for table
            table_header = self.selectors['table_header']
            await self.page.wait_for_selector(table_header, timeout=10000)

            # CRITICAL: Wait for actual entry rows to load (not just header)
            entry_rows = self.selectors['entry_rows']
            await self.page.wait_for_selector(entry_rows, timeout=15000)

            # Give a short delay for all entries to fully render
            await self.page.wait_for_timeout(1000)

            logger.debug("Docket entries section loaded")

        except Exception as e:
            logger.error(f"Docket entries failed to load: {e}")
            raise
    
    async def get_all_entries(self) -> List[TranscriptEntry]:
        """
        Get all docket entries from the page
        
        Returns:
            List of all entries (not just transcripts)
        """
        logger.info("Extracting all docket entries")
        
        try:
            entry_rows = self.selectors['entry_rows']
            rows = self.page.locator(entry_rows)
            
            count = await rows.count()
            logger.debug(f"Found {count} docket entries")
            
            entries = []
            
            for i in range(count):
                row = rows.nth(i)
                
                try:
                    # Get entry number
                    entry_num_selector = self.selectors['entry_number']
                    entry_num = await row.locator(entry_num_selector).inner_text()
                    
                    # Get filed date
                    filed_date_selector = self.selectors['filed_date']
                    filed_date = await row.locator(filed_date_selector).inner_text()
                    
                    # Get description
                    description_selector = self.selectors['description_column']
                    description = await row.locator(description_selector).inner_text()

                    # Check if download button exists
                    download_btn_selector = self.selectors['download_button']
                    has_download = await row.locator(download_btn_selector).count() > 0

                    entry = TranscriptEntry(
                        entry_num=entry_num.strip(),
                        filed_date=filed_date.strip(),
                        description=description.strip(),
                        has_download=has_download
                    )

                    # DEBUG: Log the extracted description
                    logger.debug(f"Entry {i} - #{entry_num.strip()}: {description.strip()[:100]}... (download={has_download})")

                    entries.append(entry)
                    
                except Exception as e:
                    logger.warning(f"Failed to parse entry {i}: {e}")
                    continue
            
            logger.info(f"Extracted {len(entries)} docket entries")
            return entries
            
        except Exception as e:
            logger.error(f"Failed to get docket entries: {e}")
            raise
    
    def _get_enabled_patterns(self) -> List[str]:
        """
        Get list of enabled transcript patterns
        
        Returns:
            List of regex patterns
        """
        enabled_patterns = []
        
        for pattern_config in self.transcript_patterns:
            if pattern_config.get('enabled', True):
                enabled_patterns.append(pattern_config['pattern'])
        
        return enabled_patterns
    
    def _matches_transcript_pattern(self, description: str) -> Tuple[bool, Optional[str]]:
        """
        Check if description matches any transcript pattern

        Args:
            description: Entry description text

        Returns:
            Tuple of (matches, matched_pattern)
        """
        patterns = self._get_enabled_patterns()
        logger.debug(f"Checking description against {len(patterns)} patterns: '{description[:80]}...'")

        for pattern in patterns:
            if re.search(pattern, description, re.IGNORECASE):
                logger.debug(f"✓ MATCHED pattern: '{pattern}'")
                return True, pattern
            else:
                logger.debug(f"✗ No match for pattern: '{pattern}'")

        return False, None
    
    async def find_downloadable_entries(self, pattern_matching: bool = True) -> List[TranscriptEntry]:
        """
        Find all downloadable entries (HYBRID MODE)

        Args:
            pattern_matching: If True, mark entries that match patterns (but return all downloadable)
                             If False, return all downloadable entries without pattern checking

        Returns:
            List of all downloadable entries with pattern match indicators
        """
        logger.info("Finding downloadable entries (hybrid mode)")

        all_entries = await self.get_all_entries()

        # Filter to only entries with download buttons
        downloadable_entries = [e for e in all_entries if e.has_download]

        logger.info(f"Found {len(downloadable_entries)} entries with download buttons (out of {len(all_entries)} total)")

        # Mark which entries match patterns (for highlighting in UI)
        if pattern_matching:
            enabled_patterns = self._get_enabled_patterns()
            logger.debug(f"Using {len(enabled_patterns)} pattern(s) for highlighting: {enabled_patterns}")

            pattern_match_count = 0
            for entry in downloadable_entries:
                matches, pattern = self._matches_transcript_pattern(entry.description)
                if matches:
                    entry.matched_pattern = pattern
                    pattern_match_count += 1
                    logger.debug(f"✓ Pattern match: Entry {entry.entry_num}")
                else:
                    entry.matched_pattern = None

            logger.info(f"Pattern matches: {pattern_match_count}/{len(downloadable_entries)} entries")

        return downloadable_entries

    async def find_transcript_entries(self) -> List[TranscriptEntry]:
        """
        Find entries matching transcript patterns (LEGACY - for backward compatibility)

        Returns:
            List of transcript entries matching patterns
        """
        logger.info("Finding transcript entries (pattern-only mode)")

        # Log enabled patterns
        enabled_patterns = self._get_enabled_patterns()
        logger.debug(f"Using {len(enabled_patterns)} enabled pattern(s): {enabled_patterns}")

        all_entries = await self.get_all_entries()

        transcript_entries = []

        for entry in all_entries:
            matches, pattern = self._matches_transcript_pattern(entry.description)

            if matches:
                entry.matched_pattern = pattern
                transcript_entries.append(entry)
                logger.debug(f"Found transcript: Entry {entry.entry_num} - {extract_text_preview(entry.description, 50)}")

        logger.info(f"Found {len(transcript_entries)} transcript entries")
        return transcript_entries
    
    async def download_transcript(
        self,
        entry: TranscriptEntry,
        document_title: str
    ) -> DownloadResult:
        """
        Download a specific transcript entry
        
        Args:
            entry: TranscriptEntry to download
            document_title: Title of the parent document
        
        Returns:
            DownloadResult with status and file info
        """
        logger.info(f"Downloading transcript: Entry {entry.entry_num}")
        
        if not entry.has_download:
            logger.warning(f"Entry {entry.entry_num} has no download button")
            return DownloadResult(
                status="NO_DOWNLOAD",
                entry_num=entry.entry_num,
                error_message="No download button available"
            )
        
        try:
            # Find the row for this entry
            entry_rows = self.selectors['entry_rows']
            rows = self.page.locator(entry_rows)
            
            target_row = None
            count = await rows.count()
            
            # Find the matching row
            for i in range(count):
                row = rows.nth(i)
                entry_num_elem = row.locator(self.selectors['entry_number'])
                row_entry_num = await entry_num_elem.inner_text()
                
                if row_entry_num.strip() == entry.entry_num:
                    target_row = row
                    break
            
            if not target_row:
                logger.error(f"Could not find row for entry {entry.entry_num}")
                return DownloadResult(
                    status="FAILED",
                    entry_num=entry.entry_num,
                    error_message="Row not found"
                )
            
            # Find download button in this row
            download_btn_selector = self.selectors['download_button']
            download_button = target_row.locator(download_btn_selector)
            
            if await download_button.count() == 0:
                logger.error(f"Download button not found for entry {entry.entry_num}")
                return DownloadResult(
                    status="FAILED",
                    entry_num=entry.entry_num,
                    error_message="Download button not found"
                )
            
            # Generate filename
            from utils.helpers import extract_docket_number
            docket_num = extract_docket_number(document_title) or "unknown"
            safe_docket = sanitize_filename(docket_num)
            filename = f"{safe_docket}_entry_{entry.entry_num}.pdf"
            
            # Set up download handler
            async with self.page.expect_download(timeout=60000) as download_info:
                # Click download button
                await download_button.click()
                logger.debug("Download button clicked")
            
            # Get download object
            download = await download_info.value
            
            # Save file to Bloomberg downloads folder
            base = self._downloads_dir or settings.bloomberg_downloads_dir
            downloads_dir = Path(base)
            downloads_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = downloads_dir / filename
            await download.save_as(str(file_path))
            
            logger.info(f"Downloaded: {filename}")
            
            return DownloadResult(
                status="SUCCESS",
                entry_num=entry.entry_num,
                filename=filename,
                file_path=str(file_path)
            )
            
        except Exception as e:
            logger.error(f"Download failed for entry {entry.entry_num}: {e}")
            return DownloadResult(
                status="FAILED",
                entry_num=entry.entry_num,
                error_message=str(e)
            )
    
    async def download_multiple_transcripts(
        self,
        entries: List[TranscriptEntry],
        document_title: str,
        on_progress: callable = None
    ) -> List[DownloadResult]:
        """
        Download multiple transcript entries
        
        Args:
            entries: List of TranscriptEntry objects to download
            document_title: Title of parent document
            on_progress: Optional callback for progress updates
        
        Returns:
            List of DownloadResult objects
        """
        logger.info(f"Downloading {len(entries)} transcripts")
        
        results = []
        
        for idx, entry in enumerate(entries, 1):
            if on_progress:
                await on_progress(idx, len(entries), entry.entry_num)
            
            result = await self.download_transcript(entry, document_title)
            results.append(result)
            
            # Small delay between downloads
            await self.page.wait_for_timeout(1000)
        
        # Summary
        successful = len([r for r in results if r.status == "SUCCESS"])
        logger.info(f"Download complete: {successful}/{len(results)} successful")
        
        return results
    
    async def get_transcript_entries_for_selection(self, use_hybrid_mode: bool = True) -> List[Dict]:
        """
        Get entries formatted for user selection

        Args:
            use_hybrid_mode: If True, return ALL downloadable entries with pattern indicators
                            If False, return only pattern-matching entries (legacy mode)

        Returns:
            List of dictionaries with entry details
        """
        if use_hybrid_mode:
            # HYBRID MODE: Get ALL downloadable entries
            entries = await self.find_downloadable_entries(pattern_matching=True)
        else:
            # LEGACY MODE: Get only pattern-matching entries
            entries = await self.find_transcript_entries()

        formatted_entries = []

        for entry in entries:
            formatted_entries.append({
                'entry_num': entry.entry_num,
                'filed_date': entry.filed_date,
                'description': extract_text_preview(entry.description, 200),
                'matches_pattern': entry.matched_pattern is not None,  # True if matches any pattern
                'has_download': entry.has_download,
                'matched_pattern': entry.matched_pattern  # Which pattern it matched (or None)
            })

        return formatted_entries
    
    async def download_all_matching_transcripts(
        self,
        document_title: str,
        on_progress: callable = None
    ) -> List[DownloadResult]:
        """
        Find and download all transcripts matching patterns
        
        Args:
            document_title: Title of parent document
            on_progress: Optional callback for progress
        
        Returns:
            List of DownloadResult objects
        """
        logger.info("Finding and downloading all matching transcripts")
        
        # Find transcript entries
        transcript_entries = await self.find_transcript_entries()
        
        if not transcript_entries:
            logger.warning("No transcript entries found")
            return []
        
        # Download all
        results = await self.download_multiple_transcripts(
            transcript_entries,
            document_title,
            on_progress
        )
        
        return results