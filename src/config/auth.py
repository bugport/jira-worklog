"""Jira authentication using Personal Access Token with requests library."""

import json
import re
import urllib3
import time
import threading
from typing import Optional, Dict, Any
import requests
from requests.auth import HTTPBasicAuth
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from .settings import Settings, get_settings

console = Console()


class RateLimiter:
    """Rate limiter to throttle requests per second.
    
    Thread-safe rate limiter that ensures requests don't exceed
    a specified rate (requests per second).
    """
    
    def __init__(self, rate: float = 5.0):
        """Initialize rate limiter.
        
        Args:
            rate: Maximum requests per second (default: 5.0)
        """
        self.rate = rate
        self.min_interval = 1.0 / rate  # Minimum time between requests
        self.last_request_time = 0.0
        self.lock = threading.Lock()
    
    def wait(self):
        """Wait if necessary to maintain the rate limit.
        
        This method should be called before making each request.
        """
        with self.lock:
            current_time = time.time()
            elapsed = current_time - self.last_request_time
            
            if elapsed < self.min_interval:
                # Need to wait to maintain rate limit
                wait_time = self.min_interval - elapsed
                time.sleep(wait_time)
            
            self.last_request_time = time.time()


def extract_jira_error_payload(response: requests.Response, request_payload: Optional[Dict[str, Any]] = None, request_method: Optional[str] = None, request_url: Optional[str] = None) -> Dict[str, Any]:
    """Extract error payload from JIRA REST API response.
    
    JIRA REST API can return errors in JSON format:
    {
        "errorMessages": ["Error message 1", "Error message 2"],
        "errors": {
            "field1": "Field-specific error",
            "field2": "Another field error"
        }
    }
    
    However, some JIRA instances (especially Server) may return HTML responses
    when authentication fails or when JSON error responses are not enabled.
    
    Args:
        response: requests.Response object with error status
        request_payload: Optional request payload (data sent to API)
        request_method: Optional HTTP method (GET, POST, PUT, DELETE)
        request_url: Optional request URL
        
    Returns:
        Dictionary with error information:
        - raw: Raw payload (JSON dict or text)
        - errorMessages: List of error messages (empty if HTML response)
        - errors: Dictionary of field-specific errors (empty if HTML response)
        - formatted: Formatted string representation
        - json_pretty: Pretty-printed JSON string or HTML response preview
        - is_html: Boolean indicating if response is HTML
        - content_type: Response content type
        - request_payload: Request payload that was sent (if provided)
        - request_method: HTTP method used (if provided)
        - request_url: URL that was requested (if provided)
    """
    result = {
        'raw': None,
        'errorMessages': [],
        'errors': {},
        'formatted': '',
        'json_pretty': '',
        'is_html': False,
        'content_type': response.headers.get('Content-Type', 'unknown'),
        'request_payload': request_payload,
        'request_method': request_method,
        'request_url': request_url
    }
    
    # Check content type
    content_type = response.headers.get('Content-Type', '').lower()
    is_html = 'text/html' in content_type or response.text.strip().startswith('<')
    
    result['is_html'] = is_html
    
    try:
        # Try to parse as JSON first
        if response.text and not is_html:
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
            
            # Add request payload info if available
            if request_payload:
                formatted_parts.append("")
                formatted_parts.append("Request Payload Sent:")
                formatted_parts.append(f"  Method: {request_method or 'Unknown'}")
                if request_url:
                    formatted_parts.append(f"  URL: {request_url}")
                formatted_parts.append(f"  Payload: {json.dumps(request_payload, indent=2)}")
            
            result['formatted'] = '\n'.join(formatted_parts) if formatted_parts else "No error details available"
            result['json_pretty'] = json.dumps(error_data, indent=2)
        else:
            # HTML response or empty
            raise ValueError("Response is HTML or empty, not JSON")
            
    except (ValueError, json.JSONDecodeError):
        # Not JSON - likely HTML or plain text
        result['raw'] = {'text': response.text, 'is_html': is_html}
        
        if is_html:
            # Try to extract useful information from HTML
            html_text = response.text
            
            # Extract title if present
            title_match = re.search(r'<title>(.*?)</title>', html_text, re.IGNORECASE)
            title = title_match.group(1) if title_match else None
            
            # Extract common error messages from HTML
            error_messages = []
            
            # Look for common error patterns in HTML
            patterns = [
                r'<h1[^>]*>(.*?)</h1>',
                r'<h2[^>]*>(.*?)</h2>',
                r'class="[^"]*error[^"]*"[^>]*>(.*?)</',
                r'id="[^"]*error[^"]*"[^>]*>(.*?)</',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, html_text, re.IGNORECASE)
                for match in matches:
                    cleaned = re.sub(r'<[^>]+>', '', match).strip()
                    if cleaned and len(cleaned) < 200:
                        error_messages.append(cleaned)
            
            # Build formatted message
            formatted_parts = []
            formatted_parts.append("[yellow]Warning:[/yellow] JIRA returned an HTML response instead of JSON")
            formatted_parts.append(f"Content-Type: {content_type}")
            formatted_parts.append(f"Status Code: {response.status_code}")
            
            if title:
                formatted_parts.append(f"Title: {title}")
            
            if error_messages:
                formatted_parts.append("")
                formatted_parts.append("Extracted from HTML:")
                for msg in error_messages[:5]:  # Limit to 5 messages
                    formatted_parts.append(f"  • {msg}")
            else:
                # Show first 500 chars of HTML as preview
                preview = html_text[:500].replace('\n', ' ').strip()
                formatted_parts.append("")
                formatted_parts.append(f"HTML Preview: {preview}...")
            
            # Add request payload info if available
            if request_payload:
                formatted_parts.append("")
                formatted_parts.append("Request Payload Sent:")
                formatted_parts.append(f"  Method: {request_method or 'Unknown'}")
                if request_url:
                    formatted_parts.append(f"  URL: {request_url}")
                formatted_parts.append(f"  Payload: {json.dumps(request_payload, indent=2)}")
            
            result['formatted'] = '\n'.join(formatted_parts)
            result['json_pretty'] = f"HTML Response (first 1000 chars):\n{html_text[:1000]}"
            result['errorMessages'] = error_messages if error_messages else [f"HTML Response: {title or 'Unknown error'}"]
        else:
            # Plain text response
            formatted_parts = [f"Plain text response: {response.text[:500]}"]
            
            # Add request payload info if available
            if request_payload:
                formatted_parts.append("")
                formatted_parts.append("Request Payload Sent:")
                formatted_parts.append(f"  Method: {request_method or 'Unknown'}")
                if request_url:
                    formatted_parts.append(f"  URL: {request_url}")
                formatted_parts.append(f"  Payload: {json.dumps(request_payload, indent=2)}")
            
            result['formatted'] = '\n'.join(formatted_parts)
            result['json_pretty'] = response.text[:500]
            
    except Exception as e:
        formatted_parts = [f"Unable to parse error response: {str(e)}"]
        
        # Add request payload info if available
        if request_payload:
            formatted_parts.append("")
            formatted_parts.append("Request Payload Sent:")
            formatted_parts.append(f"  Method: {request_method or 'Unknown'}")
            if request_url:
                formatted_parts.append(f"  URL: {request_url}")
            formatted_parts.append(f"  Payload: {json.dumps(request_payload, indent=2)}")
        
        result['formatted'] = '\n'.join(formatted_parts)
        result['json_pretty'] = response.text[:500] if response.text else "Empty response"
    
    return result


def get_server_info_without_auth(jira_url: str, api_version: str = 'latest') -> Optional[Dict[str, Any]]:
    """Get JIRA server information without authentication.
    
    The /rest/api/{version}/serverInfo endpoint typically allows anonymous access
    by default, making it useful for checking server version without credentials.
    
    Args:
        jira_url: JIRA server URL (e.g., 'https://your-jira.com')
        api_version: API version to use (default: 'latest')
        
    Returns:
        Dictionary with server information or None if failed
        Contains: version, baseUrl, serverTitle, buildNumber, etc.
    """
    try:
        base_url = jira_url.rstrip('/')
        url = f"{base_url}/rest/api/{api_version}/serverInfo"
        
        # Create a session without authentication
        session = requests.Session()
        session.headers.update({
            'Accept': 'application/json',
            'X-Atlassian-Token': 'no-check'
        })
        
        # Make request without authentication
        response = session.get(url, timeout=10)
        
        if response.status_code == 200:
            result = safe_parse_response(response)
            if not result.get('is_html'):
                return result
            else:
                # HTML response - server may require authentication
                return None
        else:
            # Not 200 - may require authentication
            return None
            
    except Exception:
        # Failed - may require authentication or server unreachable
        return None


def safe_parse_response(response: requests.Response) -> Dict[str, Any]:
    """Safely parse response as JSON, handling HTML responses gracefully.
    
    JIRA sometimes returns HTML even on success codes (e.g., 201 Created).
    This function detects HTML responses and returns appropriate data.
    
    Args:
        response: requests.Response object
        
    Returns:
        Dictionary with parsed data or HTML response info
        
    Raises:
        ValueError: If response cannot be parsed and is not HTML
    """
    content_type = response.headers.get('Content-Type', '').lower()
    is_html = 'text/html' in content_type or (response.text and response.text.strip().startswith('<'))
    
    if is_html:
        # Return HTML response info
        return {
            'is_html': True,
            'content_type': content_type,
            'status_code': response.status_code,
            'text': response.text,
            'html_preview': response.text[:500] if response.text else '',
            'message': 'Response is HTML, not JSON'
        }
    
    # Try to parse as JSON
    try:
        if response.text:
            return response.json()
        else:
            return {'message': 'Empty response', 'status_code': response.status_code}
    except (ValueError, json.JSONDecodeError) as e:
        # Not JSON and not HTML - return raw text info
        return {
            'is_html': False,
            'content_type': content_type,
            'status_code': response.status_code,
            'text': response.text[:500] if response.text else '',
            'error': f'Failed to parse as JSON: {str(e)}'
        }


class JiraAuth:
    """Jira authentication handler using requests library."""
    
    def __init__(self, settings: Optional[Settings] = None):
        """Initialize Jira authentication.
        
        Args:
            settings: Application settings (defaults to loading from env)
        """
        self.settings = settings or get_settings()
        self._session: Optional[requests.Session] = None
        self._rate_limiter: Optional[RateLimiter] = None
    
    @property
    def session(self) -> requests.Session:
        """Get or create requests session with authentication.
        
        Supports two authentication methods:
        - Bearer Token: Uses Authorization: Bearer <token> header (no username needed)
        - Basic Auth: Uses Authorization: Basic base64(email:token) (requires email + token)
        
        Returns:
            requests.Session with JIRA authentication configured
        """
        if self._session is None:
            # Validate required credentials based on authentication method
            if self.settings.jira_use_bearer_token:
                # Bearer token auth - only need server and token
                if not all([self.settings.jira_server, self.settings.jira_api_token]):
                    raise ValueError(
                        "Missing required Jira credentials for Bearer token authentication. "
                        "Please set JIRA_SERVER and JIRA_API_TOKEN in .env file. "
                        "JIRA_EMAIL is not required for Bearer token authentication."
                    )
            else:
                # Basic Auth - need server, email, and token
                if not all([self.settings.jira_server, self.settings.jira_email, self.settings.jira_api_token]):
                    raise ValueError(
                        "Missing required Jira credentials for Basic Auth. "
                        "Please set JIRA_SERVER, JIRA_EMAIL, and JIRA_API_TOKEN in .env file. "
                        "Or set JIRA_USE_BEARER_TOKEN=true to use Bearer token authentication (no email needed)."
                    )
            
            # Create session
            self._session = requests.Session()
            
            # Configure authentication based on method
            if self.settings.jira_use_bearer_token:
                # Use Bearer token authentication (Authorization: Bearer <token>)
                self._session.headers.update({
                    'Authorization': f'Bearer {self.settings.jira_api_token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-Atlassian-Token': 'no-check'
                })
            else:
                # Use Basic Auth (Authorization: Basic base64(email:token))
                self._session.auth = HTTPBasicAuth(self.settings.jira_email, self.settings.jira_api_token)
                self._session.headers.update({
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-Atlassian-Token': 'no-check'
                })
            
            # Configure SSL verification
            if not self.settings.jira_verify_ssl:
                self._session.verify = False
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # Initialize rate limiter (configurable via JIRA_RATE_LIMIT, default: 5.0 RPS)
            if self._rate_limiter is None:
                self._rate_limiter = RateLimiter(rate=self.settings.jira_rate_limit)
        
        return self._session
    
    @property
    def rate_limiter(self) -> RateLimiter:
        """Get rate limiter instance.
        
        Returns:
            RateLimiter configured from JIRA_RATE_LIMIT setting (default: 5.0 requests per second)
        """
        if self._rate_limiter is None:
            self._rate_limiter = RateLimiter(rate=self.settings.jira_rate_limit)
        return self._rate_limiter
    
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
        """Make HTTP request to JIRA API with rate limiting.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., '/issue', '/search')
            **kwargs: Additional arguments to pass to requests (may include 'json', 'data', etc.)
            
        Returns:
            requests.Response object
            
        Raises:
            requests.exceptions.HTTPError: If HTTP error occurs (4xx, 5xx)
        """
        # Apply rate limiting before making request (default: 5 requests per second)
        self.rate_limiter.wait()
        
        url = f"{self.base_url}{endpoint}"
        
        # Extract request payload from kwargs for error reporting
        request_payload = None
        if 'json' in kwargs:
            request_payload = kwargs['json']
        elif 'data' in kwargs:
            # Try to parse data as JSON if it's a string
            data = kwargs['data']
            if isinstance(data, str):
                try:
                    request_payload = json.loads(data)
                except (ValueError, json.JSONDecodeError):
                    request_payload = {'data': data[:500]}  # Truncate long data
            else:
                request_payload = data
        
        response = self.session.request(method, url, **kwargs)
        
        # Check if response is HTML even on success codes (common JIRA issue)
        content_type = response.headers.get('Content-Type', '').lower()
        is_html = 'text/html' in content_type or (response.text and response.text.strip().startswith('<'))
        
        if is_html and response.status_code >= 200 and response.status_code < 300:
            # HTML response on success code - this is unusual but JIRA sometimes does this
            # Extract useful info and warn, but don't fail the request
            html_info = extract_jira_error_payload(response, request_payload, method, url)
            response.html_info = html_info  # Store for later access
            response.is_html_response = True
            
            # Try to extract useful info from HTML (e.g., success message, worklog ID)
            html_text = response.text
            extracted_info = []
            
            # Look for common success patterns in HTML
            success_patterns = [
                r'worklog[^\s]*\s*(\d+)',  # Worklog ID
                r'id["\']?\s*:\s*["\']?(\d+)',  # ID in various formats
                r'success["\']?\s*:?\s*true',  # Success flag
                r'created["\']?\s*:?\s*true',  # Created flag
            ]
            
            for pattern in success_patterns:
                matches = re.findall(pattern, html_text, re.IGNORECASE)
                if matches:
                    extracted_info.extend(matches[:3])  # Limit to first 3 matches
            
            console.print(Panel(
                f"[yellow]⚠ Warning:[/yellow] JIRA returned HTML instead of JSON (HTTP {response.status_code})\n\n"
                f"[yellow]Request Details:[/yellow]\n"
                f"  Method: {method}\n"
                f"  URL: {url}\n"
                f"  Status Code: {response.status_code} (Success)\n"
                f"  Content-Type: {content_type}\n"
                + (f"  Extracted Info: {', '.join(extracted_info)}\n" if extracted_info else "") +
                f"\n[yellow]This may indicate:[/yellow]\n"
                f"• JIRA Server is returning HTML responses instead of JSON\n"
                f"• API endpoint redirect to HTML page\n"
                f"• JSON error responses not enabled in JIRA Server\n"
                f"• Response may contain success message in HTML format\n\n"
                f"[yellow]Note:[/yellow] Request may have succeeded despite HTML response.\n"
                f"Check JIRA to verify the work was created.\n\n"
                f"[yellow]HTML Preview (first 500 chars):[/yellow]\n"
                f"{response.text[:500]}...",
                title="HTML Response Warning (Success Code)",
                border_style="yellow"
            ))
        elif is_html:
            # HTML response on error code - already handled below
            pass
        
        # Handle 401 errors with detailed message and full error payload
        if response.status_code == 401:
            error_payload = extract_jira_error_payload(response, request_payload, method, url)
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
            error_payload = extract_jira_error_payload(response, request_payload, method, url)
            # Store error payload in response for later access
            response.error_payload = error_payload
        
        # Raise exception for other bad status codes
        response.raise_for_status()
        return response
    
    def test_connection(self) -> bool:
        """Test connection to Jira server.
        
        Uses both /rest/api/{version}/myself and /rest/api/{version}/serverInfo
        endpoints per JIRA REST API 8.5.0 documentation:
        - /myself: Gets current user information (verifies authentication)
        - /serverInfo: Gets server information (verifies connectivity and version)
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Use /rest/api/{version}/myself - standard endpoint for user info
            # per JIRA REST API 8.5.0 documentation
            try:
                user_response = self._make_request('GET', '/myself')
                
                # Handle HTML responses gracefully
                user_result = safe_parse_response(user_response)
                user_info = None
                if user_result.get('is_html'):
                    console.print(Panel(
                        f"[yellow]⚠ Warning:[/yellow] Received HTML response from /myself endpoint\n\n"
                        f"This indicates JIRA may not be configured for JSON responses.\n"
                        f"Endpoint tested: {self.base_url}/myself\n"
                        f"Status Code: {user_response.status_code}\n"
                        f"Content-Type: {user_result.get('content_type', 'unknown')}\n\n"
                        f"HTML Preview: {user_result.get('html_preview', 'N/A')}",
                        title="HTML Response Warning",
                        border_style="yellow"
                    ))
                    # Still try to get server info
                else:
                    user_info = user_result
                
                # Also get server info using /serverInfo endpoint
                # per JIRA REST API 8.5.0 documentation for connectivity testing
                server_info = None
                try:
                    server_response = self._make_request('GET', '/serverInfo')
                    server_result = safe_parse_response(server_response)
                    
                    if not server_result.get('is_html'):
                        server_info = server_result
                except Exception as e:
                    # Server info not critical for test - just log it
                    console.print(f"[dim]Note: Could not get server info: {str(e)}[/dim]")
                
                # Build success message
                info_lines = []
                
                if user_info and not user_result.get('is_html'):
                    display_name = user_info.get('displayName', user_info.get('name', 'N/A'))
                    email = user_info.get('emailAddress', self.settings.jira_email if not self.settings.jira_use_bearer_token else 'N/A')
                    username = user_info.get('name', user_info.get('key', 'N/A'))
                    account_id = user_info.get('accountId', 'N/A')
                    
                    info_lines.extend([
                        f"[green]✓[/green] Connected to Jira successfully!\n",
                        f"[yellow]User Information:[/yellow]",
                        f"  Display Name: {display_name}",
                        f"  Email: {email}",
                        f"  Username: {username}",
                        f"  Account ID: {account_id}"
                    ])
                elif user_result.get('is_html'):
                    info_lines.extend([
                        f"[yellow]⚠[/yellow] Connection partially successful (HTML response received)\n",
                        f"[yellow]User Information:[/yellow]",
                        f"  Status: HTML response received (cannot parse user info)",
                        f"  Authentication: May be working (status {user_response.status_code})"
                    ])
                else:
                    info_lines.extend([
                        f"[green]✓[/green] Connected to Jira successfully!\n",
                        f"[yellow]User Information:[/yellow]",
                        f"  Status: Response received but format unknown"
                    ])
                
                if server_info:
                    server_version = server_info.get('version', 'Unknown')
                    server_title = server_info.get('serverTitle', 'Unknown')
                    build_number = server_info.get('buildNumber', 'Unknown')
                    
                    info_lines.extend([
                        "",
                        f"[yellow]Server Information:[/yellow]",
                        f"  Version: {server_version}",
                        f"  Title: {server_title}",
                        f"  Build Number: {build_number}"
                    ])
                
                info_lines.extend([
                    "",
                    f"[yellow]Connection Details:[/yellow]",
                    f"  Server URL: {self.settings.jira_url}",
                    f"  API Base URL: {self.base_url}",
                    f"  Endpoints Tested:",
                    f"    • {self.base_url}/myself (User Info)",
                    f"    • {self.base_url}/serverInfo (Server Info)"
                ])
                
                console.print(Panel(
                    "\n".join(info_lines),
                    title="Connection Test Success",
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
                    if self.settings.jira_use_bearer_token:
                        debug_info.append(f"Using Bearer Token authentication (no username)")
                        debug_info.append(f"API Token: {'*' * (len(self.settings.jira_api_token) - 4) + self.settings.jira_api_token[-4:] if len(self.settings.jira_api_token) > 4 else '***'}")
                    else:
                        debug_info.append(f"Using Basic Auth with email: {self.settings.jira_email}")
                        debug_info.append(f"API Token: {'*' * (len(self.settings.jira_api_token) - 4) + self.settings.jira_api_token[-4:] if len(self.settings.jira_api_token) > 4 else '***'}")
                    
                    # Build error message with full payload
                    error_content = [
                        "[red]✗[/red] Authentication failed!\n",
                        f"[yellow]Error Details:[/yellow]\n{error_payload['formatted']}\n",
                        f"[yellow]Debug Information:[/yellow]\n",
                        *[f"• {info}" for info in debug_info]
                    ]
                    
                    # Add HTML response warning if applicable
                    if error_payload.get('is_html'):
                        error_content.extend([
                            "\n[yellow]⚠ HTML Response Detected:[/yellow]",
                            "JIRA returned an HTML response instead of JSON.",
                            "This may indicate:",
                            "• JSON error responses are not enabled on JIRA Server",
                            "• Authentication endpoint returned HTML error page",
                            "",
                            "[yellow]To enable JSON error responses on JIRA Server:[/yellow]",
                            "1. Edit jira-config.properties file",
                            "2. Add: jira.webapi.enableJsonErrorResponse=true",
                            "3. Restart JIRA"
                        ])
                    
                    error_content.extend([
                        "\n[yellow]Full Error Payload (Response):[/yellow]",
                        f"```json\n{error_payload['json_pretty']}\n```",
                        "\n[yellow]Common Issues:[/yellow]",
                        f"• JIRA_SERVER: Ensure URL is correct (no trailing slash): {self.settings.jira_url}",
                        f"• JIRA_API_TOKEN: Ensure token is valid and not expired",
                    ])
                    
                    if self.settings.jira_use_bearer_token:
                        error_content.extend([
                            f"• Bearer Token: Using Bearer token authentication (no username needed)",
                            f"• Verify token is valid for Bearer token authentication"
                        ])
                    else:
                        error_content.extend([
                            f"• JIRA_EMAIL: Use your email address or username",
                            f"• For Jira Cloud: API tokens must be used (passwords deprecated)",
                            f"• For Jira Server/Data Center: Check if Basic Auth is enabled",
                            f"• Some Jira instances require username instead of email"
                        ])
                    
                    error_content.extend([
                        f"• Verify SSL certificate if using self-signed certs",
                        "",
                        "Get your API token from:",
                        "https://id.atlassian.com/manage-profile/security/api-tokens"
                    ])
                    
                    console.print(Panel(
                        "\n".join(error_content),
                        title="Authentication Error (401)",
                        border_style="red"
                    ))
                    
                    # Print request payload separately if available
                    if error_payload.get('request_payload'):
                        console.print("\n[bold yellow]Request Payload Sent:[/bold yellow]")
                        console.print(f"  Method: {error_payload.get('request_method', 'Unknown')}")
                        console.print(f"  URL: {error_payload.get('request_url', 'Unknown')}")
                        console.print(Syntax(json.dumps(error_payload['request_payload'], indent=2), "json", theme="monokai", line_numbers=False))
                    
                    # Print formatted JSON payload separately
                    console.print("\n[bold yellow]Full Error Payload (Response):[/bold yellow]")
                    console.print(Syntax(error_payload['json_pretty'], "json", theme="monokai", line_numbers=False))
                    return False
                else:
                    # Re-raise other HTTP errors to be handled below
                    raise
                    
        except requests.exceptions.HTTPError as e:
            # Handle HTTP errors that weren't caught above
            # Determine status code - could be connection error without response
            status_code = 'Unknown'
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
            elif hasattr(e, 'response') and e.response is None:
                # Connection error - no response received
                status_code = 'No Response (Connection Error)'
            
            # Get error payload - only if we have a response
            error_payload = getattr(e, 'error_payload', None)
            if not error_payload and hasattr(e, 'response') and e.response is not None:
                error_payload = extract_jira_error_payload(e.response)
            
            # Build error message with full payload
            error_msg = str(e)
            if error_payload and error_payload.get('formatted'):
                error_msg = error_payload['formatted']
            elif hasattr(e, 'response') and e.response is None:
                error_msg = "Connection error - no response received from server.\nThis may indicate:\n  • Network connectivity issues\n  • Firewall blocking the connection\n  • Server is down or unreachable\n  • SSL/TLS certificate problems"
            
            error_content = [
                f"[red]✗[/red] Connection failed! (HTTP {status_code})\n",
                f"[yellow]Error Details:[/yellow]\n{error_msg}\n"
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
                f"• JIRA_API_TOKEN is valid (not expired)",
                f"• JIRA_API_VERSION is correct (if specified): {self.settings.jira_api_version or 'latest (default)'}",
                f"• Network connectivity and firewall rules",
                f"• JIRA_VERIFY_SSL setting if using self-signed certificates",
            ])
            if self.settings.jira_use_bearer_token:
                error_content.append(f"• Using Bearer Token authentication (no username required)")
            else:
                error_content.append(f"• JIRA_EMAIL is correct: {self.settings.jira_email}")
            error_content.extend([
                "",
                "Get your API token from:",
                "https://id.atlassian.com/manage-profile/security/api-tokens"
            ])
            
            console.print(Panel(
                "\n".join(error_content),
                title="Connection Error",
                border_style="red"
            ))
            
            # Print formatted JSON payloads separately if available
            if error_payload:
                if error_payload.get('request_payload'):
                    console.print("\n[bold yellow]Request Payload Sent:[/bold yellow]")
                    console.print(f"  Method: {error_payload.get('request_method', 'Unknown')}")
                    console.print(f"  URL: {error_payload.get('request_url', 'Unknown')}")
                    console.print(Syntax(json.dumps(error_payload['request_payload'], indent=2), "json", theme="monokai", line_numbers=False))
                
                console.print("\n[bold yellow]Full Error Payload (Response):[/bold yellow]")
                console.print(Syntax(error_payload['json_pretty'], "json", theme="monokai", line_numbers=False))
            
            return False
        except requests.exceptions.ConnectionError as e:
            # Connection error - no response at all
            error_msg = str(e)
            
            console.print(Panel(
                f"[red]✗[/red] Connection failed!\n\n"
                f"[yellow]Error Type:[/yellow] Connection Error\n"
                f"[yellow]Error Details:[/yellow] {error_msg}\n\n"
                f"[yellow]This may indicate:[/yellow]\n"
                f"• Network connectivity issues\n"
                f"• Firewall blocking the connection\n"
                f"• Server is down or unreachable\n"
                f"• DNS resolution problems\n"
                f"• SSL/TLS certificate problems\n\n"
                f"[yellow]Please check:[/yellow]\n"
                f"• JIRA_SERVER is correct (no trailing slash): {self.settings.jira_url}\n"
                f"• Network connectivity to {self.settings.jira_url}\n"
                f"• Firewall rules allowing outbound connections\n"
                f"• JIRA_VERIFY_SSL setting if using self-signed certificates\n\n"
                f"[yellow]Test connectivity:[/yellow]\n"
                f"Try accessing {self.settings.jira_url} in a web browser to verify it's reachable.",
                title="Connection Error (Network)",
                border_style="red"
            ))
            return False
        except requests.exceptions.Timeout as e:
            # Timeout error
            error_msg = str(e)
            
            console.print(Panel(
                f"[red]✗[/red] Connection timeout!\n\n"
                f"[yellow]Error Type:[/yellow] Timeout\n"
                f"[yellow]Error Details:[/yellow] {error_msg}\n\n"
                f"[yellow]This may indicate:[/yellow]\n"
                f"• Server is slow or overloaded\n"
                f"• Network latency is high\n"
                f"• Request is taking too long to process\n\n"
                f"[yellow]Please check:[/yellow]\n"
                f"• JIRA_SERVER is correct (no trailing slash): {self.settings.jira_url}\n"
                f"• Network connectivity\n"
                f"• Server performance and load\n",
                title="Timeout Error",
                border_style="red"
            ))
            return False
        except requests.exceptions.RequestException as e:
            # Other request exceptions
            error_msg = str(e)
            error_type = type(e).__name__
            
            check_items = [
                f"• JIRA_SERVER is correct (no trailing slash): {self.settings.jira_url}",
                f"• JIRA_API_TOKEN is valid",
                f"• Network connectivity",
                f"• JIRA_VERIFY_SSL setting if using self-signed certificates"
            ]
            if self.settings.jira_use_bearer_token:
                check_items.insert(1, "• Using Bearer Token authentication (no username required)")
            else:
                check_items.insert(1, f"• JIRA_EMAIL is correct: {self.settings.jira_email}")
            
            console.print(Panel(
                f"[red]✗[/red] Connection failed!\n\n"
                f"[yellow]Error Type:[/yellow] {error_type}\n"
                f"[yellow]Error Details:[/yellow] {error_msg}\n\n"
                f"[yellow]Please check:[/yellow]\n"
                + "\n".join(check_items) + "\n\n"
                f"Get your API token from:\n"
                f"https://id.atlassian.com/manage-profile/security/api-tokens",
                title="Request Error",
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
    
    def get_server_info_without_auth(self) -> Optional[Dict[str, Any]]:
        """Get JIRA server information without authentication.
        
        Uses the /rest/api/{version}/serverInfo endpoint which typically
        allows anonymous access by default per JIRA REST API documentation.
        
        Returns:
            Dictionary with server information or None if failed:
            - version: JIRA version (e.g., "8.5.0")
            - baseUrl: Base JIRA URL
            - serverTitle: Server title
            - buildNumber: Build number
            - deploymentType: Deployment type (Server/Cloud)
            - etc.
        """
        api_version = self.settings.jira_api_version or 'latest'
        return get_server_info_without_auth(self.settings.jira_url, api_version)
    
    def close(self):
        """Close Jira session connection."""
        if self._session:
            self._session.close()
            self._session = None
