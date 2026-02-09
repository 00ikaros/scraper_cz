"""
Page 1 Handler: Login and Search Form
"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from loguru import logger
from playwright.async_api import Page

from config.settings import settings
from utils.helpers import fuzzy_match, wait_for_stable_count


class Page1Handler:
    """Handles Bloomberg Law login and search form"""
    
    def __init__(self, page: Page, selectors: dict):
        self.page = page
        self.selectors = selectors
        self.login_selectors = selectors.get('page1_login', {})
        self.search_selectors = selectors.get('page1_search', {})
    
    async def wait_for_manual_login(self, timeout: int = 300) -> bool:
        """
        Wait for user to manually complete login

        Args:
            timeout: Maximum seconds to wait (default: 5 minutes)

        Returns:
            True if login detected successful
        """
        logger.info(f"Waiting for manual login (timeout: {timeout}s)")

        import asyncio
        start_time = asyncio.get_event_loop().time()

        while True:
            current_url = self.page.url

            # Check if we've navigated away from login/auth pages
            if 'login' not in current_url.lower() and 'signin' not in current_url.lower() and 'auth' not in current_url.lower():
                logger.info("Manual login detected - user successfully logged in")
                return True

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                logger.error("Manual login timeout")
                return False

            # Wait before checking again
            await asyncio.sleep(2)

    async def login(self, username: str = None, password: str = None) -> bool:
        """
        Login to Bloomberg Law (2-step process with manual fallback)

        Args:
            username: Bloomberg Law username (uses settings if not provided)
            password: Bloomberg Law password (uses settings if not provided)

        Returns:
            True if login successful
        """
        username = username or settings.bloomberg_username
        password = password or settings.bloomberg_password

        if not username or not password:
            raise ValueError("Username and password required")

        # Check for saved session first
        from pathlib import Path
        session_path = Path(settings.screenshots_dir).parent / "session_state.json"

        if session_path.exists():
            try:
                logger.info("Found saved session, attempting to use it...")
                # Just navigate to home page - session should be active
                await self.page.goto("https://www.bloomberglaw.com/home", wait_until='networkidle', timeout=15000)

                current_url = self.page.url
                if 'login' not in current_url.lower() and 'auth' not in current_url.lower():
                    logger.info("Session login successful!")
                    return True
                else:
                    logger.warning("Saved session expired, proceeding with credential login")
            except Exception as session_err:
                logger.warning(f"Session login failed: {session_err}, proceeding with credential login")

        logger.info("Starting login process (2-step)")

        try:
            # Navigate to login page
            await self.page.goto(settings.bloomberg_login_url, wait_until='networkidle')

            # Wait for login form
            username_input = self.login_selectors['username_input']
            await self.page.wait_for_selector(username_input, timeout=10000)

            # STEP 1: Fill username and click Continue
            await self.page.fill(username_input, username)
            logger.debug("Username entered")

            continue_button = self.login_selectors['continue_button']
            await self.page.click(continue_button)
            logger.debug("Clicked Continue button")

            # STEP 2: Wait for password field to appear (initially hidden)
            password_field_container = self.login_selectors['password_field_container']
            await self.page.wait_for_selector(f'{password_field_container}:not([hidden])', timeout=10000)
            logger.debug("Password field appeared")

            # Fill password
            password_input = self.login_selectors['password_input']
            await self.page.fill(password_input, password)
            logger.debug("Password entered")

            # Click Sign In button
            signin_button = self.login_selectors['signin_button']
            await self.page.click(signin_button)
            logger.debug("Clicked Sign In button")

            # Wait for navigation after login (longer timeout)
            try:
                await self.page.wait_for_load_state('networkidle', timeout=45000)
            except Exception as e:
                logger.warning(f"Navigation wait timed out or failed: {e}")

            # Take debug screenshot
            await self.page.screenshot(path=f"{settings.screenshots_dir}/after_signin.png")
            logger.debug("Screenshot taken after sign in")

            # Check for error messages on page
            error_selectors = [
                '.indg_alert__text',  # Error message class from login HTML
                '[role="alert"]',
                '.error-message',
                'text=/invalid|incorrect|failed/i'
            ]

            for error_sel in error_selectors:
                try:
                    error_elem = self.page.locator(error_sel).first
                    if await error_elem.count() > 0:
                        error_text = await error_elem.inner_text()
                        logger.error(f"Login error message: {error_text}")
                        break
                except:
                    pass

            # Verify login success (check if we're on the main page)
            current_url = self.page.url
            logger.info(f"Current URL after login: {current_url}")

            if 'login' not in current_url.lower() and 'signin' not in current_url.lower() and 'auth' not in current_url.lower():
                logger.info("Automated login successful")
                return True
            else:
                logger.warning(f"Automated login failed - still on auth page: {current_url}")
                logger.info("Switching to manual login mode...")

                # FALLBACK: Manual login
                logger.info("=" * 60)
                logger.info("PLEASE LOG IN MANUALLY IN THE BROWSER WINDOW")
                logger.info("The scraper will continue once you're logged in")
                logger.info("=" * 60)

                # Wait for user to manually log in
                manual_success = await self.wait_for_manual_login(timeout=300)

                if manual_success:
                    logger.info("Manual login successful!")

                    # Save session for future use
                    try:
                        session_path = f"{settings.screenshots_dir}/../session_state.json"
                        await self.page.context.storage_state(path=session_path)
                        logger.info(f"Session saved to {session_path}")
                    except Exception as save_err:
                        logger.warning(f"Could not save session: {save_err}")

                    return True
                else:
                    logger.error("Manual login timeout - user did not complete login")
                    return False

        except Exception as e:
            logger.error(f"Login failed with exception: {e}")
            await self.page.screenshot(path=f"{settings.screenshots_dir}/login_error.png")
            raise
    
    async def select_content_type(self, content_type: str = "Court Dockets"):
        """
        Select content type from dropdown
        
        Args:
            content_type: Content type to select (default: "Court Dockets")
        """
        logger.info(f"Selecting content type: {content_type}")
        
        try:
            # Click dropdown
            dropdown_selector = self.search_selectors['content_type_dropdown']
            await self.page.click(dropdown_selector)
            
            # Wait for options to appear
            await self.page.wait_for_timeout(500)
            
            # Click the option
            await self.page.click(f'text="{content_type}"')
            
            logger.debug(f"Content type selected: {content_type}")
            
        except Exception as e:
            logger.error(f"Failed to select content type: {e}")
            raise
    
    async def open_advanced_search(self):
        """Open advanced search modal"""
        logger.info("Opening advanced search modal")
        
        try:
            # Click "Select Sources" button
            select_sources_btn = self.search_selectors['select_sources_button']
            await self.page.click(select_sources_btn)
            
            # Wait for modal to appear
            keywords_input = self.search_selectors['keywords_input']
            await self.page.wait_for_selector(keywords_input, timeout=5000)
            
            logger.debug("Advanced search modal opened")
            
        except Exception as e:
            logger.error(f"Failed to open advanced search: {e}")
            raise
    
    async def fill_keywords(self, keywords: str):
        """
        Fill keywords field
        
        Args:
            keywords: Search keywords
        """
        logger.info(f"Filling keywords: {keywords}")
        
        try:
            keywords_input = self.search_selectors['keywords_input']
            await self.page.fill(keywords_input, keywords)
            logger.debug("Keywords filled")
            
        except Exception as e:
            logger.error(f"Failed to fill keywords: {e}")
            raise
    
    async def get_court_options(self, court_input_text: str) -> Dict[str, List[str]]:
        """
        Get court options based on input text

        Args:
            court_input_text: Text to search for courts

        Returns:
            Dictionary with 'exact_matches', 'fuzzy_matches', and 'all_options'
        """
        logger.info(f"Getting court options for: {court_input_text}")

        try:
            # Fill court input
            court_input = self.search_selectors['court_input']
            await self.page.fill(court_input, court_input_text)

            # Wait for autocomplete to filter results
            await self.page.wait_for_timeout(1500)

            # Try to wait for options to appear
            court_checkboxes = self.search_selectors['court_checkboxes']
            try:
                count = await wait_for_stable_count(
                    self.page,
                    court_checkboxes,
                    stable_checks=3,
                    check_interval=0.3,
                    timeout=5.0
                )
                logger.debug(f"Found {count} checkbox options")
            except TimeoutError:
                logger.warning("Court options did not stabilize, proceeding anyway")

            # Get all visible options
            all_labels = await self.page.locator(court_checkboxes).all_text_contents()
            all_labels = [opt.strip() for opt in all_labels if opt.strip()]

            # FILTER: Only keep items that look like courts (contain "Court" or "Dockets")
            # This filters out categories like "Administrative Dismissal", "Consumer Discretionary", etc.
            options = [
                opt for opt in all_labels
                if ('court' in opt.lower() or 'docket' in opt.lower())
            ]

            logger.debug(f"Filtered from {len(all_labels)} total to {len(options)} court options")

            if not options:
                logger.warning("No court options found after filtering")
                return {
                    'exact_matches': [],
                    'fuzzy_matches': [],
                    'all_options': []
                }

            # Perform fuzzy matching
            exact_matches, fuzzy_matches = fuzzy_match(court_input_text, options, threshold=0.6)

            logger.info(f"Found {len(options)} court options ({len(exact_matches)} exact, {len(fuzzy_matches)} fuzzy)")

            return {
                'exact_matches': exact_matches,
                'fuzzy_matches': fuzzy_matches,
                'all_options': options[:20]  # Limit to first 20 for display
            }

        except Exception as e:
            logger.error(f"Failed to get court options: {e}")
            raise
    
    async def select_court(self, court_name: str) -> bool:
        """
        Select a specific court by name

        Args:
            court_name: Exact court name to select, or '__SKIP__' to skip selection

        Returns:
            True if selection successful or skipped
        """
        # Handle skip signal
        if court_name == '__SKIP__':
            logger.info("Skipping court selection (user already selected manually)")
            return True

        logger.info(f"Selecting court: {court_name}")

        try:
            # Find and click the checkbox for this court
            court_checkboxes = self.search_selectors['court_checkboxes']

            # Click the label matching the court name
            await self.page.click(f'{court_checkboxes}:has-text("{court_name}")')

            # Verify checkbox is checked
            await self.page.wait_for_timeout(500)

            logger.debug(f"Court selected: {court_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to select court: {e}")
            return False
    
    async def fill_judge(self, judge_name: str = None):
        """
        Fill judge name field (optional)

        Args:
            judge_name: Judge name (optional, can be None or empty)
        """
        if not judge_name or not judge_name.strip():
            logger.info("No judge name provided, skipping")
            return

        logger.info(f"Filling judge name: {judge_name}")

        try:
            judge_input = self.search_selectors['judge_input']
            await self.page.fill(judge_input, judge_name)
            logger.debug("Judge name filled")

        except Exception as e:
            logger.error(f"Failed to fill judge name: {e}")
            raise
    
    async def click_search(self):
        """Click the search button"""
        logger.info("Clicking search button")

        try:
            # Close any unwanted modals first (like "Add to Dashboard")
            try:
                close_button = self.search_selectors.get('modal_close_button')
                if close_button:
                    close_buttons = self.page.locator(close_button)
                    count = await close_buttons.count()
                    if count > 0:
                        logger.debug(f"Found {count} modal close buttons, closing unwanted modals")
                        # Close all except the main search modal
                        for i in range(min(count, 3)):  # Max 3 to avoid infinite loops
                            try:
                                await close_buttons.nth(i).click(timeout=1000)
                                await self.page.wait_for_timeout(300)
                            except:
                                pass
            except Exception as modal_err:
                logger.debug(f"No unwanted modals to close: {modal_err}")

            # Now click the correct Search button
            search_button = self.search_selectors['search_button']
            await self.page.click(search_button, timeout=10000)
            logger.debug("Search button clicked")

            # Wait a moment for page to react
            await self.page.wait_for_timeout(1000)

            # Check if "Add Tile to Dashboard" modal appeared and close it
            try:
                add_tile_close = 'button.modal-close-wrapper'
                if await self.page.locator(add_tile_close).count() > 0:
                    logger.warning("'Add Tile to Dashboard' modal appeared, closing it")
                    await self.page.click(add_tile_close)
                    await self.page.wait_for_timeout(500)
            except:
                pass

            # Wait for navigation to results page
            await self.page.wait_for_load_state('networkidle', timeout=30000)

            logger.info("Search submitted successfully")

        except Exception as e:
            logger.error(f"Failed to submit search: {e}")
            await self.page.screenshot(path=f"{settings.screenshots_dir}/search_error.png")
            raise
    
    async def perform_search(
        self,
        keywords: str,
        court_name: str,
        judge_name: str,
        on_court_selection_needed: callable = None
    ) -> bool:
        """
        Complete search workflow
        
        Args:
            keywords: Search keywords
            court_name: Court name (may require user selection)
            judge_name: Judge name
            on_court_selection_needed: Callback function when court selection needed
        
        Returns:
            True if search successful
        """
        logger.info("Starting complete search workflow")
        
        try:
            # Select content type
            await self.select_content_type("Court Dockets")
            
            # Open advanced search
            await self.open_advanced_search()
            
            # Fill keywords
            await self.fill_keywords(keywords)
            
            # Handle court selection (interactive)
            court_options = await self.get_court_options(court_name)
            
            if not court_options['all_options']:
                raise ValueError(f"No courts found matching: {court_name}")
            
            # If exact match found and only one, select it automatically
            if len(court_options['exact_matches']) == 1:
                selected_court = court_options['exact_matches'][0]
                logger.info(f"Auto-selecting exact match: {selected_court}")
            else:
                # Need user selection
                if on_court_selection_needed:
                    selected_court = await on_court_selection_needed(
                        court_name,
                        court_options
                    )
                else:
                    # Default to first option
                    selected_court = court_options['all_options'][0]
                    logger.warning(f"No selection callback provided, using first option: {selected_court}")
            
            # Select the court
            await self.select_court(selected_court)
            
            # Fill judge name
            await self.fill_judge(judge_name)
            
            # Submit search
            await self.click_search()
            
            logger.info("Search workflow completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Search workflow failed: {e}")
            raise