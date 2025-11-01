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
                
                # Configure API version using the correct parameter
                # According to JIRA library docs, use 'rest_api_version' parameter, not 'rest_path'
                # This properly sets the API version (e.g., '1.0', '2', '3', 'latest')
                if self.settings.jira_api_version:
                    # Use rest_api_version parameter - this is the correct way per library docs
                    version = self.settings.jira_api_version.strip()
                    options['rest_api_version'] = version
                elif self.settings.jira_api_path:
                    # If API path is specified instead of version, extract version from path
                    api_path = self.settings.jira_api_path.rstrip('/')
                    # Extract version from path like /rest/api/1.0 or /rest/api/latest
                    if '/api/' in api_path:
                        version = api_path.split('/api/')[-1]
                        options['rest_api_version'] = version
                    else:
                        # Fallback to rest_path if version cannot be extracted
                        if api_path.startswith('/rest'):
                            api_path = api_path[5:]
                        if api_path.startswith('/'):
                            api_path = api_path[1:]
                        options['rest_path'] = api_path
                
                # Initialize JIRA client with rest_api_version parameter
                # This is the correct way to specify API version per library documentation
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
    
    def check_rest_spec_compatibility(self) -> dict:
        """Check REST API specification compatibility.
        
        Returns:
            Dictionary with compatibility information including:
            - api_version: Detected API version
            - server_version: JIRA server version
            - base_url: Base URL used
            - api_path: API path used
            - compatible: Boolean indicating if connection is successful
            - error: Error message if any
        """
        result = {
            'api_version': None,
            'server_version': None,
            'base_url': self.settings.jira_url,
            'api_path': None,
            'compatible': False,
            'error': None
        }
        
        try:
            client = self.client
            
            # Get API version from client options
            if hasattr(client, '_options'):
                if 'rest_api_version' in client._options:
                    version = client._options.get('rest_api_version', '')
                    result['api_version'] = version
                    result['api_path'] = f'/api/{version}'
                elif 'rest_path' in client._options:
                    # Fallback for rest_path if rest_api_version is not available
                    rest_path = client._options.get('rest_path', '')
                    result['api_path'] = f'/{rest_path}' if rest_path else None
                    if 'api/' in rest_path:
                        version_part = rest_path.split('api/')[-1]
                        result['api_version'] = version_part
            elif self.settings.jira_api_version:
                version = self.settings.jira_api_version.strip()
                result['api_version'] = version
                result['api_path'] = f'/api/{version}'
            elif self.settings.jira_api_path:
                api_path = self.settings.jira_api_path.rstrip('/')
                if api_path.startswith('/rest'):
                    api_path = api_path[5:]
                result['api_path'] = f'/{api_path}' if not api_path.startswith('/') else api_path
                if '/api/' in api_path:
                    version_part = api_path.split('/api/')[-1]
                    result['api_version'] = version_part
            
            # Try to get server info to check compatibility
            try:
                server_info = client.server_info()
                
                result['compatible'] = True
                result['server_version'] = server_info.get('version', 'Unknown')
                result['baseUrl'] = server_info.get('baseUrl', self.settings.jira_url)
                
                # Extract API version from options if not already set
                if not result['api_version'] and hasattr(client, '_options'):
                    if 'rest_api_version' in client._options:
                        result['api_version'] = client._options.get('rest_api_version')
                
            except Exception as e:
                result['error'] = str(e)
                result['compatible'] = False
                
        except Exception as e:
            result['error'] = str(e)
            result['compatible'] = False
        
        return result
    
    def close(self):
        """Close Jira client connection."""
        if self._client:
            self._client.close()
            self._client = None

