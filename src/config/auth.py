"""Jira authentication using Personal Access Token with requests library."""

import base64
import json
import urllib3
from typing import Optional, Dict, Any
import requests
from requests.auth import HTTPBasicAuth
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from .settings import Settings, get_settings

console = Console()


def extract_jira_error_payload(response: requests.Response) -> Dict[str, Any]:
    """Extract error payload from JIRA REST API response.
    
    JIRA REST API returns errors in the following format:
    {
        "errorMessages": ["Error message 1", "Error message 2"],
        "errors": {
            "field1": "Field-specific error",
            "field2": "Another field error"
        }
    }
    
    Args:
        response: requests.Response object with error status
        
    Returns:
        Dictionary with error information:
        - raw: Raw JSON payload
        - errorMessages: List of error messages
        - errors: Dictionary of field-specific errors
        - formatted: Formatted string representation
        - json_pretty: Pretty-printed JSON string
    """
    result = {
        'raw': None,
        'errorMessages': [],
        'errors': {},
        'formatted': '',
        'json_pretty': ''
    }
    
    try:
        error_data = response.json()
        result['raw'] = error_data
        result['errorMessages'] = error_data.get('errorMessages', [])
        result['errors'] = error_data.get('errors', {})
        
        # Format error messages
        formatted_parts = []
        
        if result['errorMessages']:
            formatted_parts.append("Error Messages:")
            for msg in result['errorMessages']:
                formatted_parts.append(f"  • {msg}")
        
        if result['errors']:
            if formatted_parts:
                formatted_parts.append("")
            formatted_parts.append("Field Errors:")
            for field, error in result['errors'].items():
                formatted_parts.append(f"  • {field}: {error}")
        
        result['formatted'] = '\n'.join(formatted_parts) if formatted_parts else "No error details available"
        
        # Pretty print JSON
        result['json_pretty'] = json.dumps(error_data, indent=2)
        
    except (ValueError, json.JSONDecodeError):
        # Not JSON, use raw text
        result['raw'] = {'text': response.text}
        result['formatted'] = f"Raw response: {response.text[:500]}"
        result['json_pretty'] = response.text[:500]
    except Exception:
        result['formatted'] = "Unable to parse error response"
        result['json_pretty'] = response.text[:500] if response.text else "Empty response"
    
    return result


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
        
        # Handle 401 errors with detailed message and full error payload
        if response.status_code == 401:
            error_payload = extract_jira_error_payload(response)
            error_msg = error_payload['formatted'] or "Authentication failed (401 Unauthorized)"
            
            # Create a more informative exception with full payload
            http_error = requests.exceptions.HTTPError(
                f"401 Client Error: Unauthorized for url: {url}\n\n{error_payload['json_pretty']}",
                response=response
            )
            # Attach error payload to exception for easier access
            http_error.error_payload = error_payload
            raise http_error
        
        # Handle other error status codes with full error payload
        if not response.ok:
            error_payload = extract_jira_error_payload(response)
            # Store error payload in response for later access
            response.error_payload = error_payload
        
        # Raise exception for other bad status codes
        response.raise_for_status()
        return response
    
    def test_connection(self) -> bool:
        """Test connection to Jira server.
        
        Uses /rest/api/{version}/myself endpoint per JIRA REST API 8.5.0 docs.
        This is the standard endpoint for getting current user information and
        verifying authentication.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Use /rest/api/{version}/myself - this is the standard endpoint
            # for getting current user info and verifying authentication
            # per JIRA REST API 8.5.0 documentation
            try:
                user_response = self._make_request('GET', '/myself')
                user_info = user_response.json()
                
                display_name = user_info.get('displayName', user_info.get('name', self.settings.jira_email))
                email = user_info.get('emailAddress', self.settings.jira_email)
                username = user_info.get('name', user_info.get('key', 'N/A'))
                
                console.print(Panel(
                    f"[green]✓[/green] Connected to Jira successfully!\n\n"
                    f"Server: {self.settings.jira_url}\n"
                    f"API Base: {self.base_url}\n"
                    f"Display Name: {display_name}\n"
                    f"Email: {email}\n"
                    f"Username: {username}\n"
                    f"Account ID: {user_info.get('accountId', 'N/A')}",
                    title="Connection Test",
                    border_style="green"
                ))
                return True
                
            except requests.exceptions.HTTPError as e:
                if e.response and e.response.status_code == 401:
                    # Get error payload from exception or extract it
                    error_payload = getattr(e, 'error_payload', None) or extract_jira_error_payload(e.response)
                    
                    # Try to get more diagnostic info
                    debug_info = []
                    debug_info.append(f"URL: {self.base_url}/myself")
                    debug_info.append(f"Using Basic Auth with email: {self.settings.jira_email}")
                    debug_info.append(f"API Token: {'*' * (len(self.settings.jira_api_token) - 4) + self.settings.jira_api_token[-4:] if len(self.settings.jira_api_token) > 4 else '***'}")
                    
                    # Build error message with full payload
                    error_content = [
                        "[red]✗[/red] Authentication failed!\n",
                        f"[yellow]Error Details:[/yellow]\n{error_payload['formatted']}\n",
                        f"[yellow]Debug Information:[/yellow]\n",
                        *[f"• {info}" for info in debug_info],
                        "\n[yellow]Full Error Payload (JSON):[/yellow]",
                        f"```json\n{error_payload['json_pretty']}\n```",
                        "\n[yellow]Common Issues:[/yellow]",
                        f"• JIRA_SERVER: Ensure URL is correct (no trailing slash): {self.settings.jira_url}",
                        f"• JIRA_EMAIL: Use your email address or username",
                        f"• JIRA_API_TOKEN: Ensure token is valid and not expired",
                        f"• For Jira Cloud: API tokens must be used (passwords deprecated)",
                        f"• For Jira Server/Data Center: Check if Basic Auth is enabled",
                        f"• Some Jira instances require username instead of email",
                        f"• Verify SSL certificate if using self-signed certs",
                        "\nGet your API token from:",
                        "https://id.atlassian.com/manage-profile/security/api-tokens"
                    ]
                    
                    console.print(Panel(
                        "\n".join(error_content),
                        title="Authentication Error (401)",
                        border_style="red"
                    ))
                    
                    # Print formatted JSON payload separately
                    console.print("\n[bold yellow]Full Error Payload:[/bold yellow]")
                    console.print(Syntax(error_payload['json_pretty'], "json", theme="monokai", line_numbers=False))
                    return False
                else:
                    # Re-raise other HTTP errors to be handled below
                    raise
                    
        except requests.exceptions.HTTPError as e:
            # Handle HTTP errors that weren't caught above
            status_code = e.response.status_code if hasattr(e, 'response') and e.response else 'Unknown'
            
            # Get error payload
            error_payload = getattr(e, 'error_payload', None)
            if not error_payload and hasattr(e, 'response') and e.response:
                error_payload = extract_jira_error_payload(e.response)
            
            # Build error message with full payload
            error_content = [
                f"[red]✗[/red] Connection failed! (HTTP {status_code})\n",
                f"[yellow]Error Details:[/yellow]\n{error_payload['formatted']}\n" if error_payload else f"Error: {str(e)}\n"
            ]
            
            if error_payload:
                error_content.extend([
                    f"[yellow]Full Error Payload (JSON):[/yellow]",
                    f"```json\n{error_payload['json_pretty']}\n```"
                ])
            
            error_content.extend([
                "",
                "[yellow]Please check:[/yellow]",
                f"• JIRA_SERVER is correct (no trailing slash): {self.settings.jira_url}",
                f"• JIRA_EMAIL is correct: {self.settings.jira_email}",
                f"• JIRA_API_TOKEN is valid (not expired)",
                f"• JIRA_API_VERSION is correct (if specified): {self.settings.jira_api_version or 'latest (default)'}",
                f"• Network connectivity and firewall rules",
                f"• JIRA_VERIFY_SSL setting if using self-signed certificates",
                "",
                "Get your API token from:",
                "https://id.atlassian.com/manage-profile/security/api-tokens"
            ])
            
            console.print(Panel(
                "\n".join(error_content),
                title="Connection Error",
                border_style="red"
            ))
            
            # Print formatted JSON payload separately if available
            if error_payload:
                console.print("\n[bold yellow]Full Error Payload:[/bold yellow]")
                console.print(Syntax(error_payload['json_pretty'], "json", theme="monokai", line_numbers=False))
            
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
