"""
Utility functions and helpers
"""
from .logger import setup_logger, get_logger
from .helpers import (
    sanitize_filename,
    extract_docket_number,
    fuzzy_match,
    parse_date,
    take_screenshot,
    wait_for_stable_count
)

__all__ = [
    'setup_logger',
    'get_logger',
    'sanitize_filename',
    'extract_docket_number',
    'fuzzy_match',
    'parse_date',
    'take_screenshot',
    'wait_for_stable_count'
]