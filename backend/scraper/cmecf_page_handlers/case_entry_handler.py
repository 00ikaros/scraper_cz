"""
CMECF Case Entry Handler
Handles entering case numbers and submitting the form
"""
from playwright.async_api import Page
from typing import Dict, Any
from loguru import logger
import asyncio


class CMECFCaseEntryHandler:
    """Handles case number entry and form submission"""

    def __init__(self, page: Page, selectors: Dict[str, Any]):
        self.page = page
        self.selectors = selectors
        self.case_entry_selectors = selectors.get('case_entry', {})
        self.wait_times = selectors.get('wait_times', {})

    async def is_on_case_entry_page(self) -> bool:
        """
        Check if we're on the case entry page

        Returns:
            True if case number input is visible
        """
        try:
            case_input_selector = self.case_entry_selectors.get(
                'case_number_input',
                '#case_number_text_area_0'
            )
            input_element = await self.page.query_selector(case_input_selector)
            return input_element is not None
        except Exception:
            return False

    async def clear_case_number_field(self):
        """Clear the case number input field"""
        try:
            case_input_selector = self.case_entry_selectors.get(
                'case_number_input',
                '#case_number_text_area_0'
            )

            # Clear the case number input
            await self.page.fill(case_input_selector, '')

            # Also clear the hidden field that stores case IDs
            all_case_ids_selector = self.case_entry_selectors.get(
                'all_case_ids',
                '#all_case_ids'
            )

            try:
                await self.page.evaluate(f'''
                    const el = document.querySelector("{all_case_ids_selector}");
                    if (el) el.value = "";
                ''')
            except Exception:
                pass  # Hidden field may not exist

            logger.debug("Cleared case number field")

        except Exception as e:
            logger.error(f"Error clearing case number field: {e}")
            raise

    async def enter_case_number(self, case_number: str):
        """
        Enter a case number into the input field

        Args:
            case_number: The case number to enter (e.g., "10-23098-bam")
        """
        try:
            case_input_selector = self.case_entry_selectors.get(
                'case_number_input',
                '#case_number_text_area_0'
            )

            logger.info(f"Entering case number: {case_number}")

            # Wait for input field
            await self.page.wait_for_selector(case_input_selector, state='visible', timeout=10000)

            # Type the case number
            await self.page.fill(case_input_selector, case_number)

            # Trigger events that CMECF might be listening for
            await self.page.evaluate(f'''
                const input = document.querySelector("{case_input_selector}");
                if (input) {{
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    input.dispatchEvent(new KeyboardEvent('keyup', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                }}
            ''')

            # Wait a moment for any autocomplete/validation
            await asyncio.sleep(1)

            logger.debug(f"Case number entered: {case_number}")

        except Exception as e:
            logger.error(f"Error entering case number: {e}")
            raise

    async def click_run_report(self):
        """Click the Run Report button to submit the form"""
        try:
            run_report_selector = self.case_entry_selectors.get(
                'run_report_button',
                "input[value='Run Report']"
            )

            logger.info("Clicking Run Report button...")

            # Wait for button and click
            await self.page.wait_for_selector(run_report_selector, state='visible', timeout=10000)
            await self.page.click(run_report_selector)

            # Wait for navigation
            await self.page.wait_for_load_state('networkidle', timeout=30000)

            logger.info("Run Report submitted, waiting for results page...")

        except Exception as e:
            logger.error(f"Error clicking Run Report: {e}")
            raise

    async def submit_case_number(self, case_number: str) -> bool:
        """
        Clear field, enter case number, and submit

        Args:
            case_number: The case number to search

        Returns:
            True if submission successful
        """
        try:
            # Clear field first
            await self.clear_case_number_field()

            # Enter case number
            await self.enter_case_number(case_number)

            # Click Run Report
            await self.click_run_report()

            # Wait for results page to load
            page_load_wait = self.wait_times.get('page_load', 10000)
            await asyncio.sleep(page_load_wait / 1000)  # Convert to seconds

            return True

        except Exception as e:
            logger.error(f"Error submitting case number {case_number}: {e}")
            return False
