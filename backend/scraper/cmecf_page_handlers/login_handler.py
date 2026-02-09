"""
CMECF Login Handler
Handles authentication to the CMECF system
"""
from playwright.async_api import Page
from typing import Dict, Any
from loguru import logger

from config.settings import settings


class CMECFLoginHandler:
    """Handles CMECF login process"""

    def __init__(self, page: Page, selectors: Dict[str, Any]):
        self.page = page
        self.selectors = selectors
        self.login_selectors = selectors.get('login', {})

    async def navigate_to_docket_page(self) -> bool:
        """
        Navigate to the docket page (will redirect to login if not authenticated)

        Returns:
            True if navigation successful
        """
        try:
            logger.info(f"Navigating to CMECF docket page: {settings.cmecf_docket_url}")
            await self.page.goto(settings.cmecf_docket_url, wait_until='networkidle')

            # Check if we're on a login page
            current_url = self.page.url
            logger.info(f"Current URL after navigation: {current_url}")

            return True

        except Exception as e:
            logger.error(f"Failed to navigate to docket page: {e}")
            raise

    async def is_login_required(self) -> bool:
        """
        Check if login is required (login form is present)

        Returns:
            True if login form is visible
        """
        try:
            username_selector = self.login_selectors.get('username_input', '#loginForm\\:loginName')
            login_form = await self.page.query_selector(username_selector)
            return login_form is not None
        except Exception:
            return False

    async def is_on_docket_page(self) -> bool:
        """
        Check if we're on the docket report page

        Returns:
            True if on docket page
        """
        try:
            current_url = self.page.url
            return 'DktRpt.pl' in current_url or 'cgi-bin' in current_url
        except Exception:
            return False

    async def login(self) -> bool:
        """
        Perform login to CMECF

        Returns:
            True if login successful
        """
        try:
            # Get selectors
            username_selector = self.login_selectors.get('username_input', '#loginForm\\:loginName')
            password_selector = self.login_selectors.get('password_input', '#loginForm\\:password')
            client_code_selector = self.login_selectors.get('client_code_input', '#loginForm\\:clientCode')
            login_button_selector = self.login_selectors.get('login_button', '#loginForm\\:fbtnLogin')

            logger.info("Filling login form...")

            # Wait for username field and fill it
            await self.page.wait_for_selector(username_selector, state='visible', timeout=10000)
            await self.page.fill(username_selector, settings.cmecf_username)
            logger.debug(f"Filled username: {settings.cmecf_username}")

            # Fill password
            await self.page.fill(password_selector, settings.cmecf_password)
            logger.debug("Filled password")

            # Fill client code if provided (leave empty if not)
            if settings.cmecf_client_code:
                await self.page.fill(client_code_selector, settings.cmecf_client_code)
                logger.debug("Filled client code")

            # Click login button
            logger.info("Clicking login button...")
            await self.page.click(login_button_selector)

            # Wait for navigation
            await self.page.wait_for_load_state('networkidle', timeout=30000)

            # Verify we're now on the docket page
            if await self.is_on_docket_page():
                logger.info("Login successful - on docket page")
                return True
            else:
                # Check if we're still on login page (login failed)
                if await self.is_login_required():
                    logger.error("Login failed - still on login page")
                    return False
                else:
                    # We might be on some other page, check URL
                    current_url = self.page.url
                    logger.info(f"After login, current URL: {current_url}")
                    return True

        except Exception as e:
            logger.error(f"Login error: {e}")
            raise

    async def ensure_logged_in(self) -> bool:
        """
        Ensure we're logged in, login if necessary

        Returns:
            True if logged in successfully
        """
        try:
            # Navigate to docket page
            await self.navigate_to_docket_page()

            # Check if login is needed
            if await self.is_login_required():
                logger.info("Login required, performing login...")
                return await self.login()
            elif await self.is_on_docket_page():
                logger.info("Already logged in and on docket page")
                return True
            else:
                # Unknown state, try to navigate again
                logger.warning("Unknown page state, attempting login...")
                return await self.login()

        except Exception as e:
            logger.error(f"Error ensuring logged in: {e}")
            raise
