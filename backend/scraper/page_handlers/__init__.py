"""
Page-specific handlers for Bloomberg Law scraping
"""
from .page1_login_search import Page1Handler
from .page2_results import Page2Handler
from .page3_docket import Page3Handler

__all__ = ['Page1Handler', 'Page2Handler', 'Page3Handler']