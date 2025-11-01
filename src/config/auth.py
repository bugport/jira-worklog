"""Jira authentication using Personal Access Token with requests library."""

import base64
import urllib3
from typing import Optional
import requests
from requests.auth import HTTPBasicAuth
from rich.console import Console
from rich.panel import Panel

from .settings import Settings, get_settings

console = Console()


class JiraAuth:
    """Jira authentication handler using requests library."""
    
    def __init__(self, settings: Optional[Settings] = None):
        """Initialize Jira authentication.
        
        Args:
            settings: Application settings (defaults to loading from env)
        """
        self.settings = settings or get_settings()
        self._session: Optional[requests.Session] = None
    
    @property
    def session(self) -> requests.Session:
        """Get or create requests session with authentication.
        
        Returns:
            requests.Session with JIRA authentication configured
        """
        if self._session is None:
            if not all([self.settings.jira_server, self.settings.jira_email, self.settings.jira_api_token]):
                raise ValueError(
                    "Missing required Jira credentials. "
                    "Please set JIRA_SERVER, JIRA_EMAIL, and JIRA_API_TOKEN in .env file"
                )
            
            # Create session with authentication
            self._session = requests.Session()
            self._session.auth = HTTPBasicAuth(self.settings.jira_email, self.settings.jira_api_token)
            
            # Configure SSL verification
            if not self.settings.jira_verify_ssl:
                self._session.verify = False
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # Set default headers
            self._session.headers.update({
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            })
        
        return self._session
    
    @property
    def base_url(self) -> str:
        """Get base JIRA API URL.
        
        According to JIRA REST API docs, 'latest' is the symbolic version
        that resolves to the most recent version supported by the JIRA instance.
        This is the recommended default for compatibility with JIRA 8.5.0+.
        """
        base = self.settings.jira_url.rstrip('/')
        api_version = 'latest'  # Default to 'latest' per JIRA REST API best practices
        
        if self.settings.jira_api_version:
            api_version = self.settings.jira_api_version.strip()
        elif self.settings.jira_api_path:
            # Extract version from path
            api_path = self.settings.jira_api_path.rstrip('/')
            if '/api/' in api_path:
                api_version = api_path.split('/api/')[-1]
        
        return f"{base}/rest/api/{api_version}"
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make HTTP request to JIRA API.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., '/issue', '/search')
            **kwargs: Additional arguments to pass to requests
            
        Returns:
            requests.Response object
        """
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, **kwargs)
        
        # Raise exception for bad status codes
        response.raise_for_status()
        return response
    
    def test_connection(self) -> bool:
        """Test connection to Jira server.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Test connection by getting current user info
            response = self._make_request('GET', '/myself')
            user_info = response.json()
            
            console.print(Panel(
                f"[green]✓[/green] Connected to Jira successfully!\n\n"
                f"Server: {self.settings.jira_url}\n"
                f"API Base: {self.base_url}\n"
                f"User: {user_info.get('displayName', self.settings.jira_email)}\n"
                f"Email: {user_info.get('emailAddress', self.settings.jira_email)}",
                title="Connection Test",
                border_style="green"
            ))
            return True
            
        except requests.exceptions.RequestException as e:
            console.print(Panel(
                f"[red]✗[/red] Connection failed!\n\n"
                f"Error: {str(e)}\n\n"
                f"Please check:\n"
                f"• JIRA_SERVER is correct (no trailing slash)\n"
                f"• JIRA_EMAIL is correct\n"
                f"• JIRA_API_TOKEN is valid\n"
                f"• JIRA_API_VERSION is correct (if specified)\n\n"
                f"Get your API token from:\n"
                f"https://id.atlassian.com/manage-profile/security/api-tokens",
                title="Connection Error",
                border_style="red"
            ))
            return False
        except Exception as e:
            console.print(Panel(
                f"[red]✗[/red] Connection failed!\n\n"
                f"Error: {str(e)}\n\n"
                f"Please check your configuration.",
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
            # Get API version from settings
            if self.settings.jira_api_version:
                result['api_version'] = self.settings.jira_api_version.strip()
                result['api_path'] = f'/rest/api/{result["api_version"]}'
            elif self.settings.jira_api_path:
                api_path = self.settings.jira_api_path.rstrip('/')
                if api_path.startswith('/rest'):
                    api_path = api_path[5:]
                result['api_path'] = f'/{api_path}' if not api_path.startswith('/') else api_path
                if '/api/' in api_path:
                    version_part = api_path.split('/api/')[-1]
                    result['api_version'] = version_part
            else:
                result['api_version'] = 'latest'  # Default to 'latest' per JIRA REST API docs
                result['api_path'] = '/rest/api/latest'
            
            # Try to get server info to check compatibility
            try:
                response = self._make_request('GET', '/serverInfo')
                server_info = response.json()
                
                result['compatible'] = True
                result['server_version'] = server_info.get('version', 'Unknown')
                result['baseUrl'] = server_info.get('baseUrl', self.settings.jira_url)
                
            except requests.exceptions.RequestException as e:
                result['error'] = str(e)
                result['compatible'] = False
                
        except Exception as e:
            result['error'] = str(e)
            result['compatible'] = False
        
        return result
    
    def close(self):
        """Close Jira session connection."""
        if self._session:
            self._session.close()
            self._session = None
