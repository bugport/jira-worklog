"""Jira authentication using Personal Access Token."""

import base64
import urllib3
from typing import Optional
from jira import JIRA
from jira.exceptions import JIRAError
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .settings import Settings, get_settings

console = Console()


class JiraAuth:
    """Jira authentication handler."""
    
    def __init__(self, settings: Optional[Settings] = None):
        """Initialize Jira authentication.
        
        Args:
            settings: Application settings (defaults to loading from env)
        """
        self.settings = settings or get_settings()
        self._client: Optional[JIRA] = None
    
    @property
    def client(self) -> JIRA:
        """Get or create Jira client instance.
        
        Returns:
            JIRA client instance
            
        Raises:
            ValueError: If credentials are missing
        """
        if self._client is None:
            if not all([self.settings.jira_server, self.settings.jira_email, self.settings.jira_api_token]):
                raise ValueError(
                    "Missing required Jira credentials. "
                    "Please set JIRA_SERVER, JIRA_EMAIL, and JIRA_API_TOKEN in .env file"
                )
            
            try:
                # Configure SSL verification and API path based on settings
                options = {}
                if not self.settings.jira_verify_ssl:
                    options['verify'] = False
                    # Suppress SSL warnings when verification is disabled
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                
                # Configure custom API path if specified
                # Note: JIRA library automatically adds '/rest' prefix, so rest_path should be the path after '/rest'
                # Example: If API is at /rest/api/latest, rest_path should be /api/latest
                if self.settings.jira_api_path:
                    api_path = self.settings.jira_api_path.rstrip('/')
                    # Remove leading '/rest' if present to avoid duplicate
                    if api_path.startswith('/rest'):
                        api_path = api_path[5:]  # Remove '/rest' prefix
                    # Ensure path starts with '/' for proper URL construction
                    if not api_path.startswith('/'):
                        api_path = '/' + api_path
                    options['rest_path'] = api_path
                
                self._client = JIRA(
                    server=self.settings.jira_url,
                    basic_auth=(self.settings.jira_email, self.settings.jira_api_token),
                    options=options if options else None
                )
            except JIRAError as e:
                raise ValueError(f"Failed to connect to Jira: {str(e)}")
        
        return self._client
    
    def test_connection(self) -> bool:
        """Test connection to Jira server.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            client = self.client
            user_info = client.current_user()
            
            console.print(Panel(
                f"[green]✓[/green] Connected to Jira successfully!\n\n"
                f"Server: {self.settings.jira_url}\n"
                f"User: {user_info.get('displayName', self.settings.jira_email)}\n"
                f"Email: {user_info.get('emailAddress', self.settings.jira_email)}",
                title="Connection Test",
                border_style="green"
            ))
            return True
            
        except Exception as e:
            console.print(Panel(
                f"[red]✗[/red] Connection failed!\n\n"
                f"Error: {str(e)}\n\n"
                f"Please check:\n"
                f"• JIRA_SERVER is correct (no trailing slash)\n"
                f"• JIRA_EMAIL is correct\n"
                f"• JIRA_API_TOKEN is valid\n\n"
                f"Get your API token from:\n"
                f"https://id.atlassian.com/manage-profile/security/api-tokens",
                title="Connection Error",
                border_style="red"
            ))
            return False
    
    def close(self):
        """Close Jira client connection."""
        if self._client:
            self._client.close()
            self._client = None

