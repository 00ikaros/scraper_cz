"""
CMECF Results Page Handler
Handles finding transcript entries and navigating to documents
"""
from playwright.async_api import Page
from typing import Dict, Any, List, Optional
from loguru import logger
import asyncio
import re

from models.cmecf_job import TranscriptMatch


class CMECFResultsHandler:
    """Handles results page navigation and transcript finding"""

    def __init__(self, page: Page, selectors: Dict[str, Any]):
        self.page = page
        self.selectors = selectors
        self.results_selectors = selectors.get('results_page', {})
        self.wait_times = selectors.get('wait_times', {})
        self.transcript_patterns = selectors.get('transcript_patterns', [])

    async def is_on_error_page(self) -> bool:
        """
        Check if we're on an error page (e.g. "Incomplete request").

        Returns:
            True if error page detected
        """
        try:
            body = await self.page.text_content('body')
            if body:
                return 'Incomplete request' in body or 'Please try your query again' in body
            return False
        except Exception:
            return False

    async def is_on_results_page(self) -> bool:
        """
        Check if we're on the results page (docket sheet)

        Returns:
            True if on results page
        """
        try:
            # Check for bankruptcy header
            header_selector = self.results_selectors.get('bankruptcy_header', 'center b font')
            header = await self.page.query_selector(header_selector)

            if header:
                text = await header.text_content()
                if text and 'Bankruptcy Petition #:' in text:
                    return True

            # Alternative: check for table structure
            table_header_selector = self.results_selectors.get('table_header', 'tbody tr th')
            th = await self.page.query_selector(table_header_selector)

            if th:
                text = await th.text_content()
                if text and 'Filing Date' in text:
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking if on results page: {e}")
            return False

    async def wait_for_results_page(self, timeout: int = 30000) -> bool:
        """
        Wait for results page to load

        Args:
            timeout: Maximum wait time in milliseconds

        Returns:
            True if results page loaded
        """
        try:
            logger.info("Waiting for results page to load...")

            # Wait for table to appear
            await self.page.wait_for_load_state('networkidle', timeout=timeout)

            # Additional wait for table to render
            page_load_wait = self.wait_times.get('page_load', 10000)
            await asyncio.sleep(page_load_wait / 1000)

            # Verify we're on results page
            if await self.is_on_results_page():
                logger.info("Results page loaded successfully")
                return True
            else:
                logger.warning("Page loaded but doesn't appear to be results page")
                return False

        except Exception as e:
            logger.error(f"Error waiting for results page: {e}")
            return False

    async def find_transcript_entries(self) -> List[TranscriptMatch]:
        """
        Find all rows where Docket Text starts with "Transcript regarding hearing held"

        Returns:
            List of TranscriptMatch objects
        """
        transcript_entries = []

        try:
            logger.info("Searching for transcript entries...")

            # Get the pattern and case sensitivity from config
            pattern = "^Transcript regarding hearing held"
            case_sensitive = False  # Default to case-insensitive
            for p in self.transcript_patterns:
                if p.get('enabled', False):
                    pattern = p.get('pattern', pattern)
                    case_sensitive = p.get('case_sensitive', False)
                    break

            # Get all table rows
            rows = await self.page.query_selector_all('tbody tr')
            logger.info(f"Found {len(rows)} rows in table")

            for i, row in enumerate(rows):
                try:
                    # Get all cells in this row
                    cells = await row.query_selector_all('td')

                    if len(cells) < 3:
                        continue  # Skip header rows or invalid rows

                    # Find the document number cell (width="30")
                    doc_number = None
                    has_link = False
                    doc_link = None

                    for cell in cells:
                        width = await cell.get_attribute('width')
                        if width == '30':
                            # This is the # column
                            link = await cell.query_selector('a')
                            if link:
                                doc_number = await link.text_content()
                                doc_number = doc_number.strip() if doc_number else None
                                has_link = True
                                doc_link = await link.get_attribute('href')
                            else:
                                # Number without link
                                text = await cell.text_content()
                                if text:
                                    # Extract just the number
                                    match = re.match(r'^\d+', text.strip())
                                    if match:
                                        doc_number = match.group(0)
                                        has_link = False
                            break

                    if not doc_number:
                        continue

                    # Get filing date (usually first cell or second cell)
                    filing_date = ""
                    for cell in cells[:2]:
                        text = await cell.text_content()
                        if text:
                            text = text.strip()
                            # Check if it looks like a date
                            if re.match(r'\d{2}/\d{2}/\d{4}', text):
                                filing_date = text
                                break

                    # Get docket text (usually the last wide cell)
                    docket_text = ""
                    for cell in cells:
                        text = await cell.text_content()
                        if text and len(text.strip()) > 50:  # Docket text is usually long
                            docket_text = text.strip()
                            break

                    # Check if docket text matches pattern
                    flags = 0 if case_sensitive else re.IGNORECASE
                    if docket_text and re.match(pattern, docket_text, flags):
                        logger.info(f"Found matching transcript: #{doc_number} - {docket_text[:50]}...")

                        entry = TranscriptMatch(
                            doc_number=doc_number,
                            filing_date=filing_date,
                            docket_text=docket_text,
                            has_link=has_link
                        )
                        transcript_entries.append(entry)

                except Exception as row_error:
                    logger.debug(f"Error processing row {i}: {row_error}")
                    continue

            logger.info(f"Found {len(transcript_entries)} matching transcript entries")
            return transcript_entries

        except Exception as e:
            logger.error(f"Error finding transcript entries: {e}")
            return []

    async def click_document_number(self, doc_number: str) -> bool:
        """
        Click on a document number link (navigates in same page)

        Args:
            doc_number: The document number to click

        Returns:
            True if click successful
        """
        try:
            logger.info(f"Clicking document #{doc_number}...")

            # Find all rows
            rows = await self.page.query_selector_all('tbody tr')

            for row in rows:
                cells = await row.query_selector_all('td')

                for cell in cells:
                    width = await cell.get_attribute('width')
                    if width == '30':
                        link = await cell.query_selector('a')
                        if link:
                            link_text = await link.text_content()
                            if link_text and link_text.strip() == str(doc_number):
                                # Found the link, click it
                                href = await link.get_attribute('href')
                                logger.debug(f"Found document link: {href}")

                                await link.click()
                                await self.page.wait_for_load_state('networkidle', timeout=30000)

                                # Wait for page to fully load
                                await asyncio.sleep(3)

                                logger.info(f"Clicked document #{doc_number} - navigated to detail page")
                                return True
                        break

            logger.error(f"Document #{doc_number} link not found")
            return False

        except Exception as e:
            logger.error(f"Error clicking document #{doc_number}: {e}")
            return False

    async def get_results_page_url(self) -> str:
        """
        Get the current results page URL for navigation back

        Returns:
            Current page URL
        """
        return self.page.url

    async def go_back_to_results(self):
        """Navigate back to the results page using browser back"""
        try:
            logger.info("Navigating back to results page...")

            # Go back twice (PDF -> Document Detail -> Results)
            await self.page.go_back()
            await self.page.wait_for_load_state('networkidle', timeout=10000)
            await asyncio.sleep(1)

            await self.page.go_back()
            await self.page.wait_for_load_state('networkidle', timeout=10000)

            # Wait for table to load
            page_load_wait = self.wait_times.get('page_load', 10000)
            await asyncio.sleep(page_load_wait / 1000)

            logger.info("Back on results page")

        except Exception as e:
            logger.error(f"Error navigating back to results: {e}")
            raise

    async def navigate_to_results_url(self, url: str):
        """
        Navigate directly to a saved results URL

        Args:
            url: The results page URL
        """
        try:
            logger.info(f"Navigating to results URL: {url}")
            await self.page.goto(url, wait_until='networkidle')

            page_load_wait = self.wait_times.get('page_load', 10000)
            await asyncio.sleep(page_load_wait / 1000)

        except Exception as e:
            logger.error(f"Error navigating to results URL: {e}")
            raise
