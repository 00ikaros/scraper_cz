"""
Configuration settings loaded from environment variables
"""
from pydantic_settings import BaseSettings
from typing import Literal
import os
from pathlib import Path


class Settings(BaseSettings):
    """Application settings"""

    # Bloomberg Law Credentials
    bloomberg_username: str
    bloomberg_password: str

    # CMECF (PACER) Credentials
    cmecf_username: str = ""
    cmecf_password: str = ""
    cmecf_client_code: str = ""
    cmecf_base_url: str = "https://ecf.nvb.uscourts.gov"
    cmecf_docket_url: str = "https://ecf.nvb.uscourts.gov/cgi-bin/DktRpt.pl"

    # Application Settings
    app_host: str = "localhost"
    app_port: int = 8000
    frontend_port: int = 3000
    
    # Scraping Mode
    scraping_mode: Literal["FULLY_INTERACTIVE", "SEMI_AUTOMATED", "FULLY_AUTOMATED"] = "FULLY_INTERACTIVE"
    
    # Browser Settings
    headless_mode: bool = False
    browser_timeout: int = 60000  # milliseconds
    page_load_timeout: int = 30000  # milliseconds
    
    # File Paths - downloads are stored outside backend, with subfolders per source
    downloads_base_dir: str = "../downloads"
    bloomberg_downloads_dir: str = "../downloads/BLOOMBERG"
    pacer_downloads_dir: str = "../downloads/PACER"
    logs_dir: str = "../logs"
    screenshots_dir: str = "../screenshots"
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create directories if they don't exist
        self._create_directories()
    
    def _create_directories(self):
        """Create necessary directories"""
        for directory in [
            self.downloads_base_dir,
            self.bloomberg_downloads_dir,
            self.pacer_downloads_dir,
            self.logs_dir,
            self.screenshots_dir
        ]:
            Path(directory).mkdir(parents=True, exist_ok=True)
    
    @property
    def bloomberg_login_url(self) -> str:
        return "https://www.bloomberglaw.com/home"
    
    @property
    def scraping_config(self) -> dict:
        """Return scraping configuration based on mode"""
        configs = {
            'FULLY_INTERACTIVE': {
                'pause_for_court': True,
                'pause_for_transcript': True,
                'auto_skip_no_match': False
            },
            'SEMI_AUTOMATED': {
                'pause_for_court': True,
                'pause_for_transcript': False,  # Auto-download if pattern matches
                'auto_skip_no_match': True
            },
            'FULLY_AUTOMATED': {
                'pause_for_court': False,  # Must provide exact court name
                'pause_for_transcript': False,
                'auto_skip_no_match': True
            }
        }
        return configs.get(self.scraping_mode, configs['FULLY_INTERACTIVE'])


# Global settings instance
settings = Settings()