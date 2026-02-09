"""
Playwright browser lifecycle management
"""
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from typing import Optional
from loguru import logger
from config.settings import settings


class BrowserManager:
    """Manages Playwright browser instance and context"""
    
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._is_initialized = False
    
    async def initialize(self, headless: bool = None):
        """
        Initialize Playwright browser
        
        Args:
            headless: Whether to run in headless mode (overrides settings)
        """
        if self._is_initialized:
            logger.warning("Browser already initialized")
            return
        
        headless_mode = headless if headless is not None else settings.headless_mode
        
        logger.info(f"Initializing browser (headless={headless_mode})")
        
        try:
            # Launch Playwright
            self.playwright = await async_playwright().start()
            
            # Launch browser
            self.browser = await self.playwright.chromium.launch(
                headless=headless_mode,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-gpu',
                    '--disable-software-rasterizer',
                    '--disable-features=VizDisplayCompositor',
                    '--disable-popup-blocking',  # Allow popups/new windows
                    # Removed --single-process as it causes instability with multiple pages
                ]
            )
            
            # Create browser context
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            # Set default timeout
            self.context.set_default_timeout(settings.browser_timeout)
            self.context.set_default_navigation_timeout(settings.page_load_timeout)
            
            # Create initial page
            self.page = await self.context.new_page()
            
            self._is_initialized = True
            logger.info("Browser initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            await self.cleanup()
            raise
    
    async def new_page(self) -> Page:
        """
        Create a new page in the current context
        
        Returns:
            New page instance
        """
        if not self._is_initialized:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        page = await self.context.new_page()
        logger.debug("Created new page")
        return page
    
    async def save_session_state(self, filepath: str):
        """
        Save browser session state (cookies, local storage)
        
        Args:
            filepath: Path to save session state
        """
        if not self._is_initialized:
            raise RuntimeError("Browser not initialized")
        
        try:
            await self.context.storage_state(path=filepath)
            logger.info(f"Session state saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save session state: {e}")
            raise
    
    async def load_session_state(self, filepath: str):
        """
        Load browser session state from file
        
        Args:
            filepath: Path to session state file
        """
        if not self._is_initialized:
            await self.initialize()
        
        try:
            # Create new context with saved state
            await self.context.close()
            self.context = await self.browser.new_context(
                storage_state=filepath,
                viewport={'width': 1920, 'height': 1080}
            )
            self.page = await self.context.new_page()
            logger.info(f"Session state loaded from {filepath}")
        except Exception as e:
            logger.error(f"Failed to load session state: {e}")
            raise
    
    async def screenshot(self, filename: str, full_page: bool = False) -> str:
        """
        Take screenshot of current page
        
        Args:
            filename: Filename for screenshot
            full_page: Whether to capture full page
        
        Returns:
            Path to screenshot
        """
        if not self.page:
            raise RuntimeError("No active page")
        
        from utils.helpers import take_screenshot
        return await take_screenshot(self.page, filename, full_page)
    
    async def go_to(self, url: str, wait_until: str = 'networkidle'):
        """
        Navigate to URL
        
        Args:
            url: URL to navigate to
            wait_until: Wait condition ('load', 'domcontentloaded', 'networkidle')
        """
        if not self.page:
            raise RuntimeError("No active page")
        
        logger.info(f"Navigating to: {url}")
        try:
            await self.page.goto(url, wait_until=wait_until)
            logger.debug(f"Navigation complete: {url}")
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            raise
    
    async def wait_for_selector(self, selector: str, timeout: float = None, state: str = 'visible'):
        """
        Wait for selector to be in specified state
        
        Args:
            selector: CSS selector
            timeout: Timeout in milliseconds
            state: Element state ('attached', 'detached', 'visible', 'hidden')
        """
        if not self.page:
            raise RuntimeError("No active page")
        
        timeout = timeout or settings.browser_timeout
        
        try:
            await self.page.wait_for_selector(selector, timeout=timeout, state=state)
            logger.debug(f"Selector found: {selector}")
        except Exception as e:
            logger.error(f"Selector not found: {selector} - {e}")
            # Take debug screenshot
            await self.screenshot(f"error_selector_{selector.replace(' ', '_')[:30]}")
            raise
    
    async def cleanup(self):
        """Clean up browser resources"""
        logger.info("Cleaning up browser resources")
        
        try:
            if self.page:
                try:
                    await self.page.close()
                except Exception as e:
                    # Ignore if transport/connection already closed (e.g. during server shutdown)
                    if 'closed' not in str(e).lower() and 'handler is closed' not in str(e).lower():
                        logger.error(f"Error closing page: {e}")
                self.page = None

            if self.context:
                try:
                    await self.context.close()
                except Exception as e:
                    if 'closed' not in str(e).lower():
                        logger.error(f"Error closing context: {e}")
                self.context = None

            if self.browser:
                try:
                    await self.browser.close()
                except Exception as e:
                    if 'closed' not in str(e).lower():
                        logger.error(f"Error closing browser: {e}")
                self.browser = None

            if self.playwright:
                try:
                    await self.playwright.stop()
                except Exception as e:
                    logger.debug(f"Playwright stop: {e}")
                self.playwright = None

            self._is_initialized = False
            logger.info("Browser cleanup complete")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    async def __aenter__(self):
        """Context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        await self.cleanup()
    
    @property
    def is_initialized(self) -> bool:
        """Check if browser is initialized"""
        return self._is_initialized