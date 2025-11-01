"""Application settings management using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Jira Configuration
    jira_server: str = os.getenv('JIRA_SERVER', '')
    jira_email: str = os.getenv('JIRA_EMAIL', '')
    jira_api_token: str = os.getenv('JIRA_API_TOKEN', '')
    jira_project: Optional[str] = os.getenv('JIRA_PROJECT', None)
    jira_verify_ssl: bool = os.getenv('JIRA_VERIFY_SSL', 'true').lower() in ('true', '1', 'yes', 'on')
    jira_api_path: Optional[str] = os.getenv('JIRA_API_PATH', None)  # e.g., '/rest/api/latest'
    jira_api_version: Optional[str] = os.getenv('JIRA_API_VERSION', None)  # e.g., '1.0', '2', '3', 'latest'
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="JIRA_"
    )
    
    @property
    def jira_url(self) -> str:
        """Get Jira server URL without trailing slash."""
        return self.jira_server.rstrip('/')


def get_settings() -> Settings:
    """Get application settings instance."""
    return Settings()

