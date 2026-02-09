"""
CMECF Document Detail Handler
Handles clicking View Document and downloading PDFs

Logic adapted from cmecf-downloader Chrome extension:
- Get View Document form data
- Submit form programmatically to get HTML response with iframe
- Extract PDF URL from iframe src
- Download PDF with proper authentication
"""
from playwright.async_api import Page
from typing import Dict, Any, Optional
from loguru import logger
from pathlib import Path
from urllib.parse import urlencode, urlparse
import asyncio
import aiohttp
import re
import traceback


class CMECFDocumentDetailHandler:
    """Handles document detail page and PDF downloads"""

    def __init__(self, page: Page, selectors: Dict[str, Any], downloads_dir: str):
        self.current_page = page  # Can be updated to popup page
        self.selectors = selectors
        self.document_selectors = selectors.get('document_detail', {})
        self.pdf_selectors = selectors.get('pdf_page', {})
        self.wait_times = selectors.get('wait_times', {})
        self.downloads_dir = Path(downloads_dir)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

    def set_page(self, page: Page):
        """Set the current page to work with (e.g., popup page)"""
        self.current_page = page

    async def is_on_document_detail_page(self) -> bool:
        """
        Check if we're on the document detail page

        Returns:
            True if View Document button is visible
        """
        try:
            view_doc_selector = self.document_selectors.get(
                'view_document_button',
                "input[type='submit'][value='View Document']"
            )
            button = await self.current_page.query_selector(view_doc_selector)
            return button is not None
        except Exception:
            return False

    async def is_on_error_page(self) -> bool:
        """
        Check if we're on an error page

        Returns:
            True if error page detected
        """
        try:
            body_text = await self.current_page.text_content('body')
            if body_text:
                return 'Incomplete request' in body_text or 'Please try your query again' in body_text
            return False
        except Exception:
            return False

    async def get_view_document_form_data(self) -> Optional[Dict[str, Any]]:
        """
        Get the View Document form data to submit programmatically.

        This follows the logic from cmecf-downloader Chrome extension's
        getViewDocumentFormData() function in content.js.

        Returns:
            Dict with action_url, form_data, and method, or None if failed
        """
        try:
            view_doc_selector = self.document_selectors.get(
                'view_document_button',
                "input[type='submit'][value='View Document']"
            )

            # Use JavaScript to extract form data (similar to Chrome extension)
            form_data = await self.current_page.evaluate(f'''
                () => {{
                    const viewButton = document.querySelector("{view_doc_selector}");
                    if (!viewButton) {{
                        return {{ success: false, error: 'View Document button not found' }};
                    }}

                    // Find the parent form
                    const form = viewButton.closest('form');
                    if (!form) {{
                        return {{ success: false, error: 'Form not found' }};
                    }}

                    // Get form action URL
                    const actionUrl = form.action || window.location.href;

                    // Collect all form data
                    const formData = new FormData(form);
                    const formDataObj = {{}};
                    for (const [key, value] of formData.entries()) {{
                        formDataObj[key] = value;
                    }}

                    return {{
                        success: true,
                        action_url: actionUrl,
                        form_data: formDataObj,
                        method: form.method || 'POST'
                    }};
                }}
            ''')

            if not form_data.get('success'):
                logger.error(f"Failed to get form data: {form_data.get('error')}")
                return None

            logger.info(f"Got View Document form data - action URL: {form_data['action_url']}")
            return form_data

        except Exception as e:
            logger.error(f"Error getting View Document form data: {e}")
            return None

    async def submit_form_and_get_pdf_url(self, form_info: Dict[str, Any]) -> Optional[str]:
        """
        Submit the View Document form programmatically and extract PDF URL from response.

        This follows the logic from cmecf-downloader Chrome extension's
        downloadPdfDirectly() function in background.js.

        Args:
            form_info: Dict containing action_url, form_data, and method

        Returns:
            PDF URL extracted from iframe in response HTML, or None if failed
        """
        try:
            action_url = form_info['action_url']
            form_data = form_info['form_data']
            method = form_info.get('method', 'POST').upper()

            logger.info(f"Submitting View Document form to: {action_url}")
            logger.debug(f"Form data: {form_data}")

            # Get cookies from browser for authenticated request
            cookies = await self.current_page.context.cookies()

            # Build cookie header (browser format)
            cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            cookie_dict = {c['name']: c['value'] for c in cookies}

            # URL encode the form data properly
            form_body = urlencode(form_data)

            logger.debug(f"Form body: {form_body}")

            # Submit the form using aiohttp with proper cookie handling
            async with aiohttp.ClientSession() as session:
                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Cookie': cookie_header,
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Referer': self.current_page.url
                }

                async with session.request(
                    method,
                    action_url,
                    data=form_body,
                    headers=headers,
                    cookies=cookie_dict,
                    allow_redirects=True
                ) as response:
                    logger.info(f"Form submission response: HTTP {response.status}")

                    if response.status != 200:
                        logger.error(f"Form submission failed: HTTP {response.status}")
                        response_text = await response.text()
                        logger.debug(f"Response: {response_text[:500]}")
                        return None

                    html_text = await response.text()
                    logger.info(f"Received HTML response ({len(html_text)} bytes)")
                    logger.debug(f"Response HTML preview: {html_text[:500]}")

                    # Parse the HTML to extract the iframe src (the actual PDF URL)
                    # This regex matches: <iframe ... src="URL" ...>
                    iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html_text, re.IGNORECASE)

                    if not iframe_match:
                        # Try alternative patterns
                        # Some pages use src without quotes or with different formatting
                        iframe_match = re.search(r'<iframe[^>]+src=([^\s>]+)', html_text, re.IGNORECASE)

                    if not iframe_match:
                        logger.error("Could not find PDF iframe in response HTML")
                        logger.debug(f"HTML response: {html_text[:1000]}")
                        return None

                    pdf_url = iframe_match.group(1).strip('"\'')
                    logger.info(f"Extracted PDF URL from iframe: {pdf_url}")

                    # If it's a relative URL, make it absolute
                    if pdf_url.startswith('/'):
                        parsed = urlparse(action_url)
                        base_url = f"{parsed.scheme}://{parsed.netloc}"
                        pdf_url = base_url + pdf_url
                        logger.info(f"Converted to absolute URL: {pdf_url}")

                    return pdf_url

        except Exception as e:
            logger.error(f"Error submitting form and getting PDF URL: {e}")
            logger.debug(traceback.format_exc())
            return None

    async def download_pdf_from_url(self, pdf_url: str, case_number: str, doc_number: str) -> Optional[str]:
        """
        Download PDF from a direct URL with authentication.

        This follows the Chrome extension logic - use browser cookies for authenticated download.

        Args:
            pdf_url: Direct URL to the PDF
            case_number: Case number for filename
            doc_number: Document number for filename

        Returns:
            Path to downloaded file or None if failed
        """
        try:
            filename = f"{case_number}_{doc_number}.pdf"
            filepath = self.downloads_dir / filename

            logger.info(f"Downloading PDF from: {pdf_url}")
            logger.info(f"Saving as: {filename}")

            # Get cookies from browser for authenticated download
            cookies = await self.current_page.context.cookies()

            # Build cookie header string (format: "name1=value1; name2=value2")
            cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

            # Also create simple dict for aiohttp
            cookie_dict = {c['name']: c['value'] for c in cookies}

            # Download using aiohttp with browser cookies - pass cookies to the request, not session
            async with aiohttp.ClientSession() as session:
                headers = {
                    'Cookie': cookie_header,
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                }
                async with session.get(pdf_url, headers=headers, cookies=cookie_dict) as response:
                    if response.status == 200:
                        content = await response.read()

                        # Verify it's actually a PDF
                        if len(content) < 100:
                            logger.error(f"Downloaded content too small: {len(content)} bytes")
                            logger.debug(f"Content preview: {content[:100]}")
                            return None

                        # Check PDF magic bytes
                        if not content.startswith(b'%PDF'):
                            logger.warning("Downloaded content doesn't start with PDF magic bytes")
                            logger.debug(f"First 100 bytes: {content[:100]}")
                            # It might be HTML error page - log it
                            if content.startswith(b'<'):
                                logger.error(f"Received HTML instead of PDF: {content[:500].decode('utf-8', errors='ignore')}")
                                return None

                        # Save the PDF
                        with open(filepath, 'wb') as f:
                            f.write(content)

                        logger.info(f"PDF downloaded successfully: {filepath} ({len(content)} bytes)")
                        return str(filepath)
                    else:
                        logger.error(f"Failed to download PDF: HTTP {response.status}")
                        response_text = await response.text()
                        logger.debug(f"Response body: {response_text[:500]}")
                        return None

        except Exception as e:
            logger.error(f"Error downloading PDF from URL: {e}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return None

    async def click_view_document_and_download(self, case_number: str, doc_number: str) -> Optional[str]:
        """
        Click the View Document button and handle popup/download.

        CRITICAL: CMECF's show_temp.pl URLs are SINGLE-USE. Once the PDF is displayed
        in the browser, that URL is invalidated. We must intercept the PDF response
        BEFORE it displays, similar to how the Chrome extension uses chrome.downloads.onCreated.

        Strategy:
        1. Set up route interception to capture PDF responses
        2. Click "View Document" button
        3. Intercept the PDF as it loads (before display invalidates the URL)
        4. Save the intercepted PDF content

        Args:
            case_number: Case number for filename
            doc_number: Document number for filename

        Returns:
            Path to downloaded file or None if failed
        """
        original_page = self.current_page
        browser_context = original_page.context
        filename = f"{case_number}_{doc_number}.pdf"
        filepath = self.downloads_dir / filename

        # Variables to capture PDF content via route interception
        captured_pdf_content = None
        pdf_captured_event = asyncio.Event()

        async def intercept_pdf_response(route, request):
            """Intercept PDF responses and capture the content (before single-use URL is consumed)."""
            nonlocal captured_pdf_content

            url = request.url
            # Check if this is a PDF request (show_temp.pl or .pdf)
            if 'show_temp.pl' in url or url.endswith('.pdf'):
                logger.info(f"Intercepting PDF request: {url}")
                try:
                    # Fetch the response (this is the only time the single-use URL works)
                    response = await route.fetch()
                    body = await response.body()

                    # Check if it's actually a PDF
                    if body.startswith(b'%PDF'):
                        logger.info(f"Captured PDF content: {len(body)} bytes")
                        captured_pdf_content = body
                        pdf_captured_event.set()

                    # Fulfill with status/headers/body (response body already consumed)
                    await route.fulfill(
                        status=response.status,
                        headers=response.headers,
                        body=body,
                    )
                except Exception as e:
                    logger.error(f"Error intercepting PDF: {e}")
                    await route.continue_()
            else:
                await route.continue_()

        try:
            view_doc_selector = self.document_selectors.get(
                'view_document_button',
                "input[type='submit'][value='View Document']"
            )

            logger.info("Preparing to click View Document (with PDF interception)...")

            # Wait for button to be visible
            await original_page.wait_for_selector(view_doc_selector, state='visible', timeout=10000)

            # Get page count before clicking
            pages_before = set(p for p in browser_context.pages)
            logger.info(f"Pages before click: {len(pages_before)}")

            # Set up listener for new pages (popup)
            new_page_event = asyncio.Event()
            captured_new_page = None

            def on_page(page):
                nonlocal captured_new_page
                logger.info(f"New page/popup detected!")
                captured_new_page = page
                new_page_event.set()

            browser_context.on('page', on_page)

            try:
                # Set up route interception on context so we catch the iframe's PDF request
                # after the main page navigates (show_temp.pl is single-use - must intercept
                # on first load, like the Chrome extension's downloads.onCreated).
                logger.info("Setting up PDF route interception on context...")
                await browser_context.route('**/*', intercept_pdf_response)

                # Block window.close() to prevent CMECF from closing the page
                await original_page.evaluate('''
                    () => {
                        window._originalClose = window.close;
                        window.close = function() {
                            console.log("window.close() blocked by scraper");
                            return false;
                        };
                    }
                ''')

                # Click the View Document button
                logger.info("Clicking View Document button...")
                await original_page.click(view_doc_selector)
                logger.info("Clicked! Waiting for PDF interception or new page...")

                # Wait for either new page or PDF capture (up to 15 seconds)
                try:
                    wait_tasks = [
                        asyncio.create_task(new_page_event.wait()),
                        asyncio.create_task(pdf_captured_event.wait()),
                    ]
                    done, pending = await asyncio.wait(
                        wait_tasks,
                        timeout=15.0,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()
                        try:
                            await t
                        except asyncio.CancelledError:
                            pass
                except asyncio.TimeoutError:
                    logger.info("Timeout waiting for PDF or new page")
                except Exception:
                    pass  # One of them completed

            finally:
                browser_context.remove_listener('page', on_page)
                # Remove route handler from context
                try:
                    await browser_context.unroute('**/*', intercept_pdf_response)
                except Exception:
                    pass

            # Check if we captured PDF content via interception
            if captured_pdf_content:
                logger.info(f"Saving intercepted PDF ({len(captured_pdf_content)} bytes) to {filepath}")
                with open(filepath, 'wb') as f:
                    f.write(captured_pdf_content)
                logger.info(f"PDF saved successfully: {filepath}")
                return str(filepath)

            # CASE 1: New page/popup was opened - set up interception on that page too
            if captured_new_page:
                new_page = captured_new_page
                logger.info(f"Handling new popup window with PDF interception...")

                try:
                    # Set up route interception on the new page
                    await new_page.route('**/*', intercept_pdf_response)

                    # Wait for the new page to load
                    logger.info("Waiting for popup to load...")
                    await new_page.wait_for_load_state('domcontentloaded', timeout=30000)

                    # Wait a bit more for PDF to load in iframe
                    await asyncio.sleep(3)

                    # Check if PDF was captured
                    if captured_pdf_content:
                        logger.info(f"Captured PDF from popup: {len(captured_pdf_content)} bytes")
                        with open(filepath, 'wb') as f:
                            f.write(captured_pdf_content)
                        logger.info(f"PDF saved successfully: {filepath}")
                        await new_page.unroute('**/*', intercept_pdf_response)
                        return str(filepath)

                    # If not captured yet, try to trigger download from the PDF viewer
                    logger.info("PDF not intercepted, trying to download from PDF viewer...")

                    new_page_url = new_page.url
                    logger.info(f"Popup URL: {new_page_url}")

                    # Try using keyboard shortcut to download (Ctrl+S / Cmd+S)
                    # Or find and click the download button in PDF viewer
                    download_path = await self._download_from_pdf_viewer(new_page, filepath)
                    if download_path:
                        await new_page.unroute('**/*', intercept_pdf_response)
                        return download_path

                    await new_page.unroute('**/*', intercept_pdf_response)

                except Exception as popup_error:
                    logger.error(f"Error handling popup: {popup_error}")
                    logger.debug(traceback.format_exc())
                    try:
                        await new_page.unroute('**/*', intercept_pdf_response)
                    except Exception:
                        pass

            # CASE 2: Check if original page navigated to PDF viewer
            logger.info("Checking if original page has PDF viewer...")
            await asyncio.sleep(2)

            try:
                current_url = original_page.url
                logger.info(f"Original page URL after click: {current_url}")

                if '/doc1/' in current_url:
                    # Try to download from PDF viewer on this page
                    download_path = await self._download_from_pdf_viewer(original_page, filepath)
                    if download_path:
                        return download_path

            except Exception as check_error:
                logger.warning(f"Error checking original page: {check_error}")

            logger.error("All download methods failed")
            return None

        except Exception as e:
            logger.error(f"Error in click_view_document_and_download: {e}")
            logger.debug(traceback.format_exc())
            return None

        finally:
            # Ensure we reset to original page
            try:
                if original_page in browser_context.pages:
                    self.set_page(original_page)
            except Exception:
                pass

    async def _download_from_pdf_viewer(self, page, filepath: Path) -> Optional[str]:
        """
        Download PDF from Chrome's built-in PDF viewer.

        The PDF is already displayed in an iframe. We need to either:
        1. Use the download button in the PDF viewer toolbar
        2. Use keyboard shortcut (Ctrl+S)
        3. Access the PDF through the embed element

        Args:
            page: The page containing the PDF viewer
            filepath: Where to save the PDF

        Returns:
            Path to downloaded file or None if failed
        """
        try:
            logger.info("Attempting to download from PDF viewer...")

            # Method 1: Try to find and click the download button in PDF viewer
            # The PDF viewer toolbar has a download button
            # It's inside a shadow DOM, so we need special handling

            # First, check if there's an embed or object tag with the PDF
            pdf_element_info = await page.evaluate('''
                () => {
                    // Check for embed
                    const embed = document.querySelector('embed[type="application/pdf"]');
                    if (embed && embed.src) {
                        return { type: 'embed', src: embed.src };
                    }

                    // Check for iframe with PDF
                    const iframe = document.querySelector('iframe');
                    if (iframe) {
                        // Try to get the src
                        if (iframe.src && iframe.src !== 'about:blank') {
                            return { type: 'iframe', src: iframe.src };
                        }
                        // Check iframe's document for embed
                        try {
                            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                            const iframeEmbed = iframeDoc.querySelector('embed[type="application/pdf"]');
                            if (iframeEmbed && iframeEmbed.src) {
                                return { type: 'iframe_embed', src: iframeEmbed.src };
                            }
                        } catch (e) {
                            // Cross-origin iframe, can't access
                        }
                    }

                    // Check for object tag
                    const obj = document.querySelector('object[type="application/pdf"]');
                    if (obj && obj.data) {
                        return { type: 'object', src: obj.data };
                    }

                    return null;
                }
            ''')

            logger.info(f"PDF element info: {pdf_element_info}")

            # Method 2: Use Playwright's download handler with keyboard shortcut
            logger.info("Trying keyboard shortcut to trigger download...")
            try:
                async with page.expect_download(timeout=10000) as download_info:
                    # Focus on the page and press Ctrl+S (or Cmd+S on Mac)
                    await page.keyboard.press('Control+s')

                download = await download_info.value
                logger.info(f"Download triggered via keyboard: {download.suggested_filename}")
                await download.save_as(filepath)
                logger.info(f"PDF saved: {filepath}")
                return str(filepath)

            except Exception as kb_error:
                logger.debug(f"Keyboard shortcut download failed: {kb_error}")

            # Method 3: Try clicking the download button in the PDF viewer toolbar
            # Chrome's PDF viewer has a shadow DOM, we need to pierce it
            logger.info("Trying to find download button in PDF viewer...")
            try:
                # The download button is typically in the PDF viewer's toolbar
                # Try common selectors for PDF viewer download button
                download_button_selectors = [
                    '#download',  # Chrome PDF viewer
                    '[id="download"]',
                    'cr-icon-button[id="download"]',
                    'button[aria-label="Download"]',
                    'button[title="Download"]',
                    '[data-testid="download"]',
                ]

                for selector in download_button_selectors:
                    try:
                        button = await page.query_selector(selector)
                        if button:
                            logger.info(f"Found download button with selector: {selector}")
                            async with page.expect_download(timeout=10000) as download_info:
                                await button.click()
                            download = await download_info.value
                            await download.save_as(filepath)
                            logger.info(f"PDF saved via download button: {filepath}")
                            return str(filepath)
                    except Exception:
                        continue

            except Exception as btn_error:
                logger.debug(f"Download button click failed: {btn_error}")

            # Method 4: Try to get PDF from iframe and use JavaScript to trigger download
            logger.info("Trying JavaScript-based download from iframe...")
            try:
                # Get the iframe's content URL if available
                iframe_src = await page.evaluate('''
                    () => {
                        const iframe = document.querySelector('iframe');
                        if (iframe && iframe.src && iframe.src !== 'about:blank') {
                            return iframe.src;
                        }
                        // Try to get from iframe's location
                        try {
                            return iframe.contentWindow.location.href;
                        } catch (e) {
                            return null;
                        }
                    }
                ''')

                if iframe_src and iframe_src != 'about:blank':
                    logger.info(f"Found iframe src: {iframe_src}")
                    # This URL might still be valid if we haven't fetched it yet
                    # But likely it's already been shown...

            except Exception as js_error:
                logger.debug(f"JavaScript download failed: {js_error}")

            logger.warning("Could not download from PDF viewer")
            return None

        except Exception as e:
            logger.error(f"Error downloading from PDF viewer: {e}")
            return None

    async def click_view_document(self) -> bool:
        """
        Click the View Document button (legacy method)

        Returns:
            True if click successful
        """
        try:
            view_doc_selector = self.document_selectors.get(
                'view_document_button',
                "input[type='submit'][value='View Document']"
            )

            logger.info("Clicking View Document button...")

            await self.current_page.wait_for_selector(view_doc_selector, state='visible', timeout=10000)
            await self.current_page.click(view_doc_selector)

            # Wait for navigation/PDF to load
            await self.current_page.wait_for_load_state('networkidle', timeout=30000)
            await asyncio.sleep(2)

            logger.info("View Document clicked")
            return True

        except Exception as e:
            logger.error(f"Error clicking View Document: {e}")
            return False

    async def download_pdf(self, case_number: str, doc_number: str) -> Optional[str]:
        """
        Download the PDF with proper filename using direct HTTP request.

        This is the fallback method that extracts PDF URL from the current page
        after clicking View Document.

        Args:
            case_number: The case number for filename
            doc_number: The document number for filename

        Returns:
            Path to downloaded file or None if failed
        """
        try:
            logger.info(f"Extracting PDF URL from current page...")

            # Try to get PDF URL from iframe or embed
            pdf_url = await self._get_pdf_url()

            if not pdf_url:
                logger.error("Could not find PDF URL in page")
                return None

            logger.info(f"Found PDF URL: {pdf_url}")

            # Use the shared download method
            return await self.download_pdf_from_url(pdf_url, case_number, doc_number)

        except Exception as e:
            logger.error(f"Error downloading PDF: {e}")
            return None

    async def _get_pdf_url(self, max_retries: int = 5, retry_delay: float = 2.0) -> Optional[str]:
        """
        Extract PDF URL from the page (usually in an iframe).

        This follows the logic from cmecf-downloader Chrome extension's
        iframe extraction in setupDownloadListenerAndClick() in background.js.

        The Chrome extension waits for iframe to load and extracts the src attribute.
        We add retry logic since the iframe may take time to load.

        Args:
            max_retries: Maximum number of retries to find iframe
            retry_delay: Delay between retries in seconds

        Returns:
            PDF URL or None
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting to extract PDF URL (attempt {attempt + 1}/{max_retries})...")

                # Log page info for debugging
                current_url = self.current_page.url
                logger.info(f"Current page URL: {current_url}")

                # Use JavaScript to extract PDF URL (similar to Chrome extension)
                pdf_info = await self.current_page.evaluate('''
                    () => {
                        const result = {
                            iframe_src: null,
                            embed_src: null,
                            object_data: null,
                            page_url: window.location.href,
                            page_origin: window.location.origin,
                            has_iframe: false,
                            has_embed: false,
                            iframe_count: document.querySelectorAll('iframe').length,
                            body_preview: document.body ? document.body.innerHTML.substring(0, 500) : 'no body'
                        };

                        // Check for iframe with PDF (CMECF uses iframe to display PDFs)
                        const iframe = document.querySelector('iframe');
                        if (iframe) {
                            result.has_iframe = true;
                            if (iframe.src) {
                                result.iframe_src = iframe.src;
                                console.log('Found iframe with src:', iframe.src);
                            }
                        }

                        // Check for PDF embed tag
                        const embed = document.querySelector('embed[type="application/pdf"]');
                        if (embed) {
                            result.has_embed = true;
                            if (embed.src) {
                                result.embed_src = embed.src;
                            }
                        }

                        // Check for object tag with PDF
                        const objectTag = document.querySelector('object[type="application/pdf"]');
                        if (objectTag && objectTag.data) {
                            result.object_data = objectTag.data;
                        }

                        return result;
                    }
                ''')

                logger.debug(f"PDF extraction info: iframe_count={pdf_info.get('iframe_count')}, "
                            f"has_iframe={pdf_info.get('has_iframe')}, "
                            f"has_embed={pdf_info.get('has_embed')}")

                # Try iframe src first
                iframe_src = pdf_info.get('iframe_src')
                if iframe_src:
                    # Convert relative URL to absolute
                    if iframe_src.startswith('/'):
                        pdf_url = pdf_info['page_origin'] + iframe_src
                    else:
                        pdf_url = iframe_src
                    logger.info(f"Found PDF URL in iframe: {pdf_url}")
                    return pdf_url

                # Try embed src
                embed_src = pdf_info.get('embed_src')
                if embed_src:
                    if embed_src.startswith('/'):
                        pdf_url = pdf_info['page_origin'] + embed_src
                    else:
                        pdf_url = embed_src
                    logger.info(f"Found PDF URL in embed: {pdf_url}")
                    return pdf_url

                # Try object data
                object_data = pdf_info.get('object_data')
                if object_data:
                    if object_data.startswith('/'):
                        pdf_url = pdf_info['page_origin'] + object_data
                    else:
                        pdf_url = object_data
                    logger.info(f"Found PDF URL in object tag: {pdf_url}")
                    return pdf_url

                # Check if current URL is already a PDF URL
                if '.pdf' in current_url or 'show_temp.pl' in current_url:
                    logger.info(f"Current URL appears to be PDF: {current_url}")
                    return current_url

                # If /doc1/ in URL but no iframe yet, page might still be loading
                if '/doc1/' in current_url:
                    logger.info(f"On /doc1/ page but no iframe found yet, waiting...")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        # Last attempt - try current URL as PDF
                        logger.info(f"Using current /doc1/ URL as PDF URL: {current_url}")
                        return current_url

                # No PDF found, wait and retry
                if attempt < max_retries - 1:
                    logger.info(f"No PDF URL found, waiting {retry_delay}s before retry...")
                    logger.debug(f"Page body preview: {pdf_info.get('body_preview', 'N/A')[:200]}")
                    await asyncio.sleep(retry_delay)

            except Exception as e:
                logger.error(f"Error in PDF URL extraction attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)

        logger.warning("Could not find PDF URL in page after all retries")
        return None

    async def download_document(self, case_number: str, doc_number: str) -> Dict[str, Any]:
        """
        Complete document download workflow.

        Tries multiple approaches in order:
        1. Click View Document and handle popup/download (handles new windows)
        2. Form submission approach (programmatic POST)
        3. Click and wait approach (fallback)

        Args:
            case_number: Case number for filename
            doc_number: Document number for filename

        Returns:
            Dict with status and file info
        """
        try:
            # Check if on error page
            if await self.is_on_error_page():
                return {
                    'status': 'FAILED',
                    'error': 'Landed on error page (Incomplete request)'
                }

            # Verify we're on document detail page
            if not await self.is_on_document_detail_page():
                return {
                    'status': 'FAILED',
                    'error': 'Not on document detail page'
                }

            # Method 1: Click and handle popup/download (primary method)
            # This handles cases where View Document opens a popup window
            logger.info("Attempting click-and-handle-popup approach...")
            filepath = await self.click_view_document_and_download(case_number, doc_number)

            if filepath:
                return {
                    'status': 'SUCCESS',
                    'filename': f"{case_number}_{doc_number}.pdf",
                    'filepath': filepath
                }

            logger.warning("Click-and-handle-popup approach failed, trying form submission...")

            # Method 2: Form submission approach
            logger.info("Attempting form submission approach...")
            form_info = await self.get_view_document_form_data()

            if form_info:
                pdf_url = await self.submit_form_and_get_pdf_url(form_info)

                if pdf_url:
                    filepath = await self.download_pdf_from_url(pdf_url, case_number, doc_number)

                    if filepath:
                        return {
                            'status': 'SUCCESS',
                            'filename': f"{case_number}_{doc_number}.pdf",
                            'filepath': filepath
                        }
                    else:
                        logger.warning("Form submission got PDF URL but download failed...")
                else:
                    logger.warning("Form submission failed to get PDF URL...")
            else:
                logger.warning("Could not get form data...")

            return {
                'status': 'FAILED',
                'error': 'Failed to download PDF (all methods failed)'
            }

        except Exception as e:
            logger.error(f"Error in download_document: {e}")
            return {
                'status': 'FAILED',
                'error': str(e)
            }

    async def go_back(self):
        """Navigate back one page"""
        try:
            await self.current_page.go_back()
            await self.current_page.wait_for_load_state('networkidle', timeout=10000)
        except Exception as e:
            logger.error(f"Error going back: {e}")
