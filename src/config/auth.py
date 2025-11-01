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
            
        Raises:
            requests.exceptions.HTTPError: If HTTP error occurs (4xx, 5xx)
        """
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, **kwargs)
        
        # Handle 401 errors with detailed message
        if response.status_code == 401:
            error_msg = "Authentication failed (401 Unauthorized)"
            try:
                error_data = response.json()
                if error_data.get('errorMessages'):
                    error_msg = ', '.join(error_data['errorMessages'])
                elif error_data.get('errors'):
                    error_msg = str(error_data['errors'])
            except:
                if response.text:
                    error_msg += f": {response.text[:200]}"
            
            # Create a more informative exception
            http_error = requests.exceptions.HTTPError(
                f"401 Client Error: Unauthorized for url: {url}\n{error_msg}",
                response=response
            )
            raise http_error
        
        # Raise exception for other bad status codes
        response.raise_for_status()
        return response
    
    def test_connection(self) -> bool:
        """Test connection to Jira server.
        
        Uses /rest/auth/1/session endpoint per JIRA REST API 8.5.0 docs
        to verify authentication, then optionally fetches user details.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # First, test authentication using /rest/auth/1/session
            # This is the recommended endpoint for authentication verification
            # according to JIRA REST API 8.5.0 documentation
            auth_url = f"{self.settings.jira_url}/rest/auth/1/session"
            response = self.session.get(auth_url)
            
            if response.status_code == 401:
                # Authentication failed - show detailed error
                error_msg = "Authentication failed (401 Unauthorized)"
                try:
                    error_data = response.json()
                    if error_data.get('errorMessages'):
                        error_msg += f"\n\nError: {', '.join(error_data['errorMessages'])}"
                except:
                    error_msg += f"\n\nResponse: {response.text[:200]}"
                
                console.print(Panel(
                    f"[red]✗[/red] Authentication failed!\n\n"
                    f"{error_msg}\n\n"
                    f"Please check:\n"
                    f"• JIRA_SERVER is correct (no trailing slash): {self.settings.jira_url}\n"
                    f"• JIRA_EMAIL is correct: {self.settings.jira_email}\n"
                    f"• JIRA_API_TOKEN is valid (not expired)\n"
                    f"• For API token authentication, use email as username\n"
                    f"• Ensure Basic Auth is enabled on your JIRA instance\n\n"
                    f"Get your API token from:\n"
                    f"https://id.atlassian.com/manage-profile/security/api-tokens",
                    title="Authentication Error (401)",
                    border_style="red"
                ))
                return False
            
            response.raise_for_status()
            session_info = response.json()
            
            # Get user details using /rest/api/{version}/myself
            # Try to get full user info with displayName and emailAddress
            try:
                user_response = self._make_request('GET', '/myself')
                user_info = user_response.json()
                display_name = user_info.get('displayName', session_info.get('name', self.settings.jira_email))
                email = user_info.get('emailAddress', self.settings.jira_email)
            except:
                # Fallback to session info if /myself fails
                display_name = session_info.get('name', self.settings.jira_email)
                email = self.settings.jira_email
            
            console.print(Panel(
                f"[green]✓[/green] Connected to Jira successfully!\n\n"
                f"Server: {self.settings.jira_url}\n"
                f"API Base: {self.base_url}\n"
                f"User: {display_name}\n"
                f"Email: {email}\n"
                f"Username: {session_info.get('name', 'N/A')}",
                title="Connection Test",
                border_style="green"
            ))
            return True
            
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if hasattr(e, 'response') and e.response else 'Unknown'
            error_msg = str(e)
            
            # Try to get error details from response
            if hasattr(e, 'response') and e.response:
                try:
                    error_data = e.response.json()
                    if error_data.get('errorMessages'):
                        error_msg = ', '.join(error_data['errorMessages'])
                    elif error_data.get('errors'):
                        error_msg = str(error_data['errors'])
                except:
                    error_msg = e.response.text[:200] if e.response.text else error_msg
            
            console.print(Panel(
                f"[red]✗[/red] Connection failed! (HTTP {status_code})\n\n"
                f"Error: {error_msg}\n\n"
                f"Please check:\n"
                f"• JIRA_SERVER is correct (no trailing slash): {self.settings.jira_url}\n"
                f"• JIRA_EMAIL is correct: {self.settings.jira_email}\n"
                f"• JIRA_API_TOKEN is valid (not expired)\n"
                f"• JIRA_API_VERSION is correct (if specified)\n"
                f"• Network connectivity and firewall rules\n"
                f"• JIRA_VERIFY_SSL setting if using self-signed certificates\n\n"
                f"Get your API token from:\n"
                f"https://id.atlassian.com/manage-profile/security/api-tokens",
                title="Connection Error",
                border_style="red"
            ))
            return False
        except requests.exceptions.RequestException as e:
            console.print(Panel(
                f"[red]✗[/red] Connection failed!\n\n"
                f"Error: {str(e)}\n\n"
                f"Please check:\n"
                f"• JIRA_SERVER is correct (no trailing slash): {self.settings.jira_url}\n"
                f"• JIRA_EMAIL is correct: {self.settings.jira_email}\n"
                f"• JIRA_API_TOKEN is valid\n"
                f"• Network connectivity\n"
                f"• JIRA_VERIFY_SSL setting if using self-signed certificates\n\n"
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
