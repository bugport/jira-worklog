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
                # IMPORTANT: rest_path should NOT start with '/' to avoid '/rest//api' duplication
                # The library may append version numbers after rest_path, so we need to construct it carefully
                # Example: If API is at /rest/api/latest, rest_path should be 'api/latest' (without leading /)
                if self.settings.jira_api_version:
                    # If API version is specified, use it to construct the path
                    version = self.settings.jira_api_version.strip()
                    # rest_path should NOT start with '/' - library adds '/rest' and '/' automatically
                    options['rest_path'] = f'api/{version}'
                elif self.settings.jira_api_path:
                    api_path = self.settings.jira_api_path.rstrip('/')
                    # Remove leading '/rest' if present to avoid duplicate
                    if api_path.startswith('/rest'):
                        api_path = api_path[5:]  # Remove '/rest' prefix
                    # Remove leading '/' to avoid '/rest//api' duplication
                    if api_path.startswith('/'):
                        api_path = api_path[1:]
                    # Ensure path doesn't start with '/' (library adds it)
                    options['rest_path'] = api_path
                
                self._client = JIRA(
                    server=self.settings.jira_url,
                    basic_auth=(self.settings.jira_email, self.settings.jira_api_token),
                    options=options if options else None
                )
                
                # If API version is specified and library is appending wrong version,
                # patch the _get_url method to use correct path
                if self.settings.jira_api_version:
                    version = self.settings.jira_api_version.strip()
                    
                    # Patch _get_url to replace default API version with configured version
                    if hasattr(self._client, '_get_url'):
                        original_get_url = self._client._get_url
                        
                        def patched_get_url(path='', params=None, base=None):
                            # Replace any occurrence of /2/ or /2/ in path with configured version
                            if path:
                                # Replace /2/ with /{version}/
                                path = path.replace('/2/', f'/{version}/')
                                # Replace leading '2/' with '{version}/'
                                if path.startswith('2/'):
                                    path = path.replace('2/', f'{version}/', 1)
                                # Replace trailing '/2' (before query params)
                                if path.endswith('/2'):
                                    path = path[:-2] + f'/{version}'
                                # Handle '2/serverInfo' pattern
                                if '/2/' not in path and path.count(version) == 0:
                                    if path.startswith('2/'):
                                        path = f'{version}/' + path[2:]
                            return original_get_url(path, params, base)
                        
                        self._client._get_url = patched_get_url
                    
                    # Also patch _options to ensure rest_path is correctly set
                    if hasattr(self._client, '_options'):
                        # Make sure rest_path uses the configured version
                        if 'rest_path' in self._client._options:
                            current_rest_path = self._client._options['rest_path']
                            if '/2/' in current_rest_path or current_rest_path.endswith('/2'):
                                self._client._options['rest_path'] = current_rest_path.replace('/2/', f'/{version}/').replace('/2', f'/{version}')
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
            
            # Get API path from client if available
            if hasattr(client, '_options') and 'rest_path' in client._options:
                rest_path = client._options.get('rest_path', '')
                # rest_path doesn't include leading /, so we add it for display
                result['api_path'] = f'/{rest_path}' if rest_path else None
            elif self.settings.jira_api_version:
                version = self.settings.jira_api_version.strip()
                result['api_path'] = f'/api/{version}'
            elif self.settings.jira_api_path:
                api_path = self.settings.jira_api_path.rstrip('/')
                if api_path.startswith('/rest'):
                    api_path = api_path[5:]
                result['api_path'] = f'/{api_path}' if not api_path.startswith('/') else api_path
            
            # Try to get server info to check compatibility
            try:
                server_info = client.server_info()
                
                result['compatible'] = True
                result['server_version'] = server_info.get('version', 'Unknown')
                result['baseUrl'] = server_info.get('baseUrl', self.settings.jira_url)
                
                # Extract API version from the actual URL used
                if hasattr(client, '_options') and 'rest_path' in client._options:
                    rest_path = client._options.get('rest_path', '')
                    # rest_path is like 'api/1.0' or 'api/latest' (without leading /)
                    # Extract version from path
                    if 'api/' in rest_path:
                        version_part = rest_path.split('api/')[-1]
                        result['api_version'] = version_part
                    elif '/' in rest_path:
                        # If no 'api/' prefix, take the last part
                        version_part = rest_path.split('/')[-1]
                        result['api_version'] = version_part
                
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

