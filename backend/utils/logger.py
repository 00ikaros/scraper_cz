"""
Logging configuration using loguru
"""
from loguru import logger
import sys
from pathlib import Path
from config.settings import settings


def setup_logger():
    """
    Configure loguru logger with file and console output
    """
    # Remove default handler
    logger.remove()
    
    # Console handler with color
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=settings.log_level,
        colorize=True
    )
    
    # File handler for all logs
    log_path = Path(settings.logs_dir) / "scraper_{time:YYYY-MM-DD}.log"
    logger.add(
        log_path,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="00:00",  # Rotate at midnight
        retention="30 days",  # Keep logs for 30 days
        compression="zip"  # Compress old logs
    )
    
    # Separate file for errors only
    error_log_path = Path(settings.logs_dir) / "errors_{time:YYYY-MM-DD}.log"
    logger.add(
        error_log_path,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}\n{exception}",
        level="ERROR",
        rotation="00:00",
        retention="90 days",  # Keep error logs longer
        compression="zip"
    )
    
    logger.info(f"Logger initialized with level: {settings.log_level}")
    logger.info(f"Logs directory: {settings.logs_dir}")
    
    return logger


def get_logger():
    """Get the configured logger instance"""
    return logger


# Initialize logger on import
setup_logger()