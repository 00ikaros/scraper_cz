"""
Helper utility functions
"""
import re
import asyncio
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime
from difflib import SequenceMatcher, get_close_matches
from loguru import logger


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """
    Sanitize filename by removing invalid characters
    
    Args:
        filename: Original filename
        max_length: Maximum filename length
    
    Returns:
        Sanitized filename
    """
    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
    
    # Replace spaces with underscores
    sanitized = sanitized.replace(' ', '_')
    
    # Remove multiple underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    
    # Truncate if too long
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized.strip('_')


def extract_docket_number(title: str) -> Optional[str]:
    """
    Extract docket number from document title
    
    Args:
        title: Document title
    
    Returns:
        Docket number or None if not found
    
    Examples:
        "BELCORP RESOURCES, INC., Docket No. 2:12-bk-16650" -> "2:12-bk-16650"
        "Case No. 1:21-cv-12345" -> "1:21-cv-12345"
    """
    # Pattern for docket numbers
    patterns = [
        r'Docket No\.\s+([^\s,)]+)',
        r'Case No\.\s+([^\s,)]+)',
        r'No\.\s+(\d+:\d+-[a-z]+-\d+)',
        r'(\d+:\d+-[a-z]+-\d+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


def fuzzy_match(query: str, options: List[str], threshold: float = 0.6) -> Tuple[List[str], List[str]]:
    """
    Perform fuzzy matching of query against options
    
    Args:
        query: Search query
        options: List of options to match against
        threshold: Matching threshold (0.0 to 1.0)
    
    Returns:
        Tuple of (exact_matches, fuzzy_matches)
    """
    query_lower = query.lower()
    
    # Exact matches (substring match)
    exact_matches = [
        opt for opt in options 
        if query_lower in opt.lower()
    ]
    
    # Fuzzy matches using difflib
    fuzzy_matches = get_close_matches(
        query,
        options,
        n=10,  # Return top 10 matches
        cutoff=threshold
    )
    
    # Remove duplicates (items in both lists)
    fuzzy_matches = [
        match for match in fuzzy_matches 
        if match not in exact_matches
    ]
    
    return exact_matches, fuzzy_matches


def similarity_ratio(str1: str, str2: str) -> float:
    """
    Calculate similarity ratio between two strings
    
    Args:
        str1: First string
        str2: Second string
    
    Returns:
        Similarity ratio (0.0 to 1.0)
    """
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def parse_date(date_str: str) -> Optional[datetime]:
    """
    Parse date string in various formats
    
    Args:
        date_str: Date string
    
    Returns:
        datetime object or None if parsing fails
    """
    formats = [
        "%b. %d, %Y",  # Sep. 19, 2012
        "%B %d, %Y",   # September 19, 2012
        "%m/%d/%Y",    # 09/19/2012
        "%Y-%m-%d",    # 2012-09-19
        "%d-%m-%Y",    # 19-09-2012
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    logger.warning(f"Could not parse date: {date_str}")
    return None


async def take_screenshot(page, filename: str, full_page: bool = False) -> str:
    """
    Take screenshot of current page
    
    Args:
        page: Playwright page object
        filename: Filename for screenshot (without extension)
        full_page: Whether to capture full page or just viewport
    
    Returns:
        Path to saved screenshot
    """
    from config.settings import settings
    
    # Ensure screenshots directory exists
    screenshots_dir = Path(settings.screenshots_dir)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = sanitize_filename(filename)
    screenshot_path = screenshots_dir / f"{safe_filename}_{timestamp}.png"
    
    try:
        await page.screenshot(path=str(screenshot_path), full_page=full_page)
        logger.info(f"Screenshot saved: {screenshot_path}")
        return str(screenshot_path)
    except Exception as e:
        logger.error(f"Failed to take screenshot: {e}")
        return ""


async def wait_for_stable_count(page, selector: str, stable_checks: int = 3, check_interval: float = 0.3, timeout: float = 10.0) -> int:
    """
    Wait for element count to stabilize (useful for dynamic loading)
    
    Args:
        page: Playwright page object
        selector: CSS selector
        stable_checks: Number of consecutive stable checks required
        check_interval: Time between checks in seconds
        timeout: Maximum time to wait in seconds
    
    Returns:
        Final stable count
    
    Raises:
        TimeoutError: If count doesn't stabilize within timeout
    """
    start_time = asyncio.get_event_loop().time()
    previous_count = 0
    stable_count = 0
    
    while stable_count < stable_checks:
        # Check for timeout
        if asyncio.get_event_loop().time() - start_time > timeout:
            raise TimeoutError(f"Element count did not stabilize within {timeout}s")
        
        # Get current count
        try:
            current_count = await page.locator(selector).count()
        except Exception as e:
            logger.warning(f"Error getting element count: {e}")
            current_count = 0
        
        # Check if count is stable
        if current_count == previous_count:
            stable_count += 1
        else:
            stable_count = 0
        
        previous_count = current_count
        
        # Wait before next check
        await asyncio.sleep(check_interval)
    
    logger.debug(f"Element count stabilized at {previous_count} for selector: {selector}")
    return previous_count


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format
    
    Args:
        size_bytes: Size in bytes
    
    Returns:
        Formatted size string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def format_duration(seconds: float) -> str:
    """
    Format duration in human-readable format
    
    Args:
        seconds: Duration in seconds
    
    Returns:
        Formatted duration string (e.g., "2m 30s")
    """
    if seconds < 60:
        return f"{seconds:.0f}s"
    
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    
    if minutes < 60:
        return f"{minutes}m {remaining_seconds}s"
    
    hours = int(minutes // 60)
    remaining_minutes = int(minutes % 60)
    
    return f"{hours}h {remaining_minutes}m {remaining_seconds}s"


def validate_url(url: str) -> bool:
    """
    Validate if string is a valid URL
    
    Args:
        url: URL string to validate
    
    Returns:
        True if valid URL, False otherwise
    """
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return url_pattern.match(url) is not None


def extract_text_preview(text: str, max_length: int = 100) -> str:
    """
    Extract preview of text with ellipsis if needed
    
    Args:
        text: Full text
        max_length: Maximum preview length
    
    Returns:
        Text preview
    """
    text = text.strip()
    
    if len(text) <= max_length:
        return text
    
    # Try to break at word boundary
    preview = text[:max_length]
    last_space = preview.rfind(' ')
    
    if last_space > max_length * 0.8:  # If space is near the end
        preview = preview[:last_space]
    
    return preview + "..."


def generate_job_id() -> str:
    """
    Generate unique job ID with timestamp
    
    Returns:
        Unique job ID
    """
    import uuid
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    return f"job_{timestamp}_{unique_id}"


def is_transcript_pattern(description: str, patterns: List[str]) -> Tuple[bool, Optional[str]]:
    """
    Check if description matches any transcript pattern
    
    Args:
        description: Description text
        patterns: List of regex patterns to match
    
    Returns:
        Tuple of (matches, matched_pattern)
    """
    description = description.strip()
    
    for pattern in patterns:
        if re.search(pattern, description, re.IGNORECASE):
            return True, pattern
    
    return False, None


async def wait_for_navigation(page, timeout: float = 30000):
    """
    Wait for page navigation to complete
    
    Args:
        page: Playwright page object
        timeout: Timeout in milliseconds
    """
    try:
        await page.wait_for_load_state('networkidle', timeout=timeout)
    except Exception as e:
        logger.warning(f"Navigation wait timeout: {e}")
        # Try alternative wait
        await page.wait_for_load_state('domcontentloaded', timeout=timeout)


def batch_list(items: List, batch_size: int) -> List[List]:
    """
    Split list into batches
    
    Args:
        items: List to batch
        batch_size: Size of each batch
    
    Returns:
        List of batches
    """
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]


def merge_dicts(*dicts) -> dict:
    """
    Merge multiple dictionaries
    
    Args:
        *dicts: Variable number of dictionaries
    
    Returns:
        Merged dictionary
    """
    result = {}
    for d in dicts:
        result.update(d)
    return result