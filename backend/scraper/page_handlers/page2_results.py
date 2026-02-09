"""
Page 2 Handler: Search Results
"""
from typing import List, Dict, Optional
from loguru import logger
from playwright.async_api import Page

from models.scraping_job import DocumentResult


class Page2Handler:
    """Handles Bloomberg Law search results page"""
    
    def __init__(self, page: Page, selectors: dict):
        self.page = page
        self.selectors = selectors.get('page2_results', {})
    
    async def wait_for_results(self):
        """Wait for results page to load"""
        logger.info("Waiting for results page to load")

        try:
            # Wait a bit for page to stabilize
            await self.page.wait_for_load_state('networkidle', timeout=30000)

            # Check for zero results message
            zero_results_selectors = [
                'text=/0 results/i',
                'text=/no results found/i',
                'text=/your search returned no results/i',
                '.no-results'
            ]

            for selector in zero_results_selectors:
                try:
                    zero_elem = self.page.locator(selector).first
                    if await zero_elem.count() > 0:
                        logger.warning("Search returned 0 results")
                        return  # Don't raise error, just return
                except:
                    pass

            # Try to find results container
            results_container = self.selectors['results_container']
            await self.page.wait_for_selector(results_container, timeout=10000)
            logger.debug("Results page loaded")

        except Exception as e:
            # Check again if it's a zero results scenario
            page_text = await self.page.inner_text('body')
            if '0 results' in page_text.lower() or 'no results' in page_text.lower():
                logger.warning("Search returned 0 results (detected from page text)")
                return
            logger.error(f"Results page failed to load: {e}")
            raise
    
    async def get_total_results_count(self) -> int:
        """
        Get total number of results
        
        Returns:
            Total results count
        """
        try:
            results_count_selector = self.selectors['results_count']
            count_text = await self.page.locator(results_count_selector).first.inner_text()
            
            # Extract number from text like "47 results"
            import re
            match = re.search(r'(\d+)', count_text)
            if match:
                count = int(match.group(1))
                logger.info(f"Total results: {count}")
                return count
            
            logger.warning("Could not parse results count")
            return 0
            
        except Exception as e:
            logger.warning(f"Could not get results count: {e}")
            return 0
    
    async def get_result_links(self) -> List[DocumentResult]:
        """
        Get all result links on current page

        Returns:
            List of DocumentResult objects (empty list if no results)
        """
        logger.info("Extracting result links from page")

        try:
            result_links_selector = self.selectors['result_links']
            result_elements = self.page.locator(result_links_selector)

            count = await result_elements.count()

            if count == 0:
                logger.warning("No result links found on page (0 results)")
                return []

            logger.debug(f"Found {count} result links")

            results = []

            for i in range(count):
                element = result_elements.nth(i)

                # Get href and title
                href = await element.get_attribute('href')
                title = await element.inner_text()

                # Extract docket number from title
                from utils.helpers import extract_docket_number
                docket_number = extract_docket_number(title)

                result = DocumentResult(
                    title=title.strip(),
                    url=href,
                    docket_number=docket_number
                )

                results.append(result)

            logger.info(f"Extracted {len(results)} result links")
            return results

        except Exception as e:
            logger.error(f"Failed to extract result links: {e}")
            raise
    
    async def navigate_to_document(self, document: DocumentResult):
        """
        Navigate to a specific document
        
        Args:
            document: DocumentResult object
        """
        logger.info(f"Navigating to document: {document.title[:50]}...")
        
        try:
            # Construct full URL if needed
            url = document.url
            if not url.startswith('http'):
                url = f"https://www.bloomberglaw.com{url}"
            
            await self.page.goto(url, wait_until='networkidle')
            logger.debug("Document page loaded")
            
        except Exception as e:
            logger.error(f"Failed to navigate to document: {e}")
            raise
    
    async def go_back_to_results(self):
        """Navigate back to results page"""
        logger.info("Navigating back to results page")
        
        try:
            await self.page.go_back()
            await self.wait_for_results()
            logger.debug("Back to results page")
            
        except Exception as e:
            logger.error(f"Failed to go back to results: {e}")
            raise
    
    async def has_next_page(self) -> bool:
        """
        Check if there is a next page of results
        
        Returns:
            True if next page exists
        """
        try:
            next_button = self.selectors['next_page_button']
            count = await self.page.locator(next_button).count()
            
            if count > 0:
                # Check if button is enabled
                is_disabled = await self.page.locator(next_button).first.is_disabled()
                return not is_disabled
            
            return False
            
        except Exception as e:
            logger.warning(f"Could not check for next page: {e}")
            return False
    
    async def go_to_next_page(self):
        """Navigate to next page of results"""
        logger.info("Navigating to next page")
        
        try:
            next_button = self.selectors['next_page_button']
            await self.page.click(next_button)
            
            # Wait for new results to load
            await self.page.wait_for_load_state('networkidle')
            await self.wait_for_results()
            
            logger.debug("Next page loaded")
            
        except Exception as e:
            logger.error(f"Failed to go to next page: {e}")
            raise
    
    async def get_all_results(self, max_pages: int = None) -> List[DocumentResult]:
        """
        Get results from multiple pages
        
        Args:
            max_pages: Maximum number of pages to scrape (None for all)
        
        Returns:
            List of all DocumentResult objects
        """
        logger.info(f"Getting results from multiple pages (max: {max_pages or 'all'})")
        
        all_results = []
        page_num = 1
        
        while True:
            # Get results from current page
            results = await self.get_result_links()
            all_results.extend(results)
            
            logger.info(f"Page {page_num}: {len(results)} results (total: {len(all_results)})")
            
            # Check if we should continue
            if max_pages and page_num >= max_pages:
                logger.info(f"Reached max pages limit: {max_pages}")
                break
            
            # Check if there's a next page
            if not await self.has_next_page():
                logger.info("No more pages available")
                break
            
            # Go to next page
            await self.go_to_next_page()
            page_num += 1
        
        logger.info(f"Total results collected: {len(all_results)} from {page_num} pages")
        return all_results