"""Jira API service for issues and work logs using requests library."""

from typing import List, Optional
from datetime import datetime, date, timedelta
from calendar import monthrange
import re
import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..config.auth import JiraAuth, extract_jira_error_payload, safe_parse_response
from ..models.issue import Issue
from ..models.worklog import WorkLog, WorkLogEntry, SyncResult, ExistingWorkLog, WorkLogUpdate
from ..utils.formatters import format_time_hours
from decimal import Decimal

console = Console()


class JiraService:
    """Service for Jira API operations using requests library."""
    
    def __init__(self, auth: Optional[JiraAuth] = None):
        """Initialize Jira service.
        
        Args:
            auth: Jira authentication handler (creates new if None)
        """
        self.auth = auth or JiraAuth()
        self._current_user: Optional[dict] = None
        self._epic_link_field_id: Optional[str] = None  # Cache discovered Epic Link field ID
        self._epic_name_field_id: Optional[str] = None  # Cache discovered Epic Name field ID
    
    def get_current_user(self) -> Optional[dict]:
        """Get current authenticated user information.
        
        Returns:
            Dictionary with user info (name, accountId, displayName, emailAddress) or None if failed
        """
        if self._current_user is None:
            try:
                response = self.auth._make_request('GET', '/myself')
                result = safe_parse_response(response)
                if not result.get('is_html'):
                    self._current_user = result
                else:
                    console.print("[yellow]Warning:[/yellow] Could not get current user info (HTML response)")
                    return None
            except Exception as e:
                console.print(f"[yellow]Warning:[/yellow] Could not get current user info: {str(e)}")
                return None
        return self._current_user
    
    def get_issues_from_filter(self, filter_id: str) -> List[Issue]:
        """Get issues from a Jira filter.
        
        Args:
            filter_id: Jira filter ID
            
        Returns:
            List of Issue objects
        """
        try:
            from .filter_service import FilterService
            filter_service = FilterService(self.auth)
            jql = filter_service.get_filter_jql(filter_id)
            
            if not jql:
                console.print(f"[red]Filter {filter_id} not found or has no JQL query.[/red]")
                return []
            
            return self.get_issues_from_jql(jql)
            
        except Exception as e:
            console.print(f"[red]Error getting issues from filter:[/red] {str(e)}")
            return []
    
    def discover_epic_link_field_id(self) -> Optional[str]:
        """Discover the Epic Link custom field ID from Jira API.
        
        Queries the /field endpoint to find the field with name "Epic Link".
        
        Returns:
            Epic Link field ID (e.g., "customfield_10014") or None if not found
        """
        if self._epic_link_field_id:
            return self._epic_link_field_id
        
        try:
            # Get all fields from Jira API
            response = self.auth._make_request('GET', '/field')
            fields_data = safe_parse_response(response)
            
            if fields_data.get('is_html'):
                console.print("[yellow]Warning:[/yellow] Could not discover Epic Link field (HTML response)")
                return None
            
            # Search for Epic Link field
            for field in fields_data:
                field_name = field.get('name', '').lower()
                field_id = field.get('id', '')
                
                # Look for "Epic Link" field
                if 'epic' in field_name and 'link' in field_name:
                    self._epic_link_field_id = field_id
                    console.print(f"[green]Discovered Epic Link field ID:[/green] {field_id}")
                    return field_id
            
            console.print("[yellow]Warning:[/yellow] Epic Link field not found in field list")
            return None
            
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Could not discover Epic Link field: {str(e)}")
            return None
    
    def discover_epic_name_field_id(self) -> Optional[str]:
        """Discover the Epic Name custom field ID from Jira API.
        
        Queries the /field endpoint to find the field with name "Epic Name".
        
        Returns:
            Epic Name field ID (e.g., "customfield_10011") or None if not found
        """
        if self._epic_name_field_id:
            return self._epic_name_field_id
        
        try:
            # Get all fields from Jira API
            response = self.auth._make_request('GET', '/field')
            fields_data = safe_parse_response(response)
            
            if fields_data.get('is_html'):
                console.print("[yellow]Warning:[/yellow] Could not discover Epic Name field (HTML response)")
                return None
            
            # Search for Epic Name field
            for field in fields_data:
                field_name = field.get('name', '').lower()
                field_id = field.get('id', '')
                
                # Look for "Epic Name" field
                if 'epic' in field_name and 'name' in field_name:
                    self._epic_name_field_id = field_id
                    console.print(f"[green]Discovered Epic Name field ID:[/green] {field_id}")
                    return field_id
            
            console.print("[yellow]Warning:[/yellow] Epic Name field not found in field list")
            return None
            
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Could not discover Epic Name field: {str(e)}")
            return None
    
    def get_issue_details(self, issue_key: str) -> Optional[dict]:
        """Get issue details by issue key.
        
        Args:
            issue_key: Jira issue key
            
        Returns:
            Dictionary with issue details or None if not found
        """
        try:
            response = self.auth._make_request('GET', f'/issue/{issue_key}')
            return response.json()
        except requests.exceptions.RequestException:
            return None
        except Exception:
            return None
    
    def get_issues_from_jql(self, jql: str) -> List[Issue]:
        """Get issues from JQL query.
        
        Args:
            jql: JQL query string
            
        Returns:
            List of Issue objects
        """
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Fetching issues from Jira...", total=None)
                
                # Discover Epic Link and Epic Name field IDs dynamically
                epic_link_field_id = self.discover_epic_link_field_id()
                epic_name_field_id = self.discover_epic_name_field_id()
                
                # Build fields list for API request
                # Include discovered field IDs and common fallback IDs
                fields_list = [
                    'summary', 'issuetype', 'status', 'project', 'assignee', 
                    'created', 'updated', 'parent', 'subtasks'
                ]
                
                # Add discovered Epic Link field ID
                if epic_link_field_id:
                    fields_list.append(epic_link_field_id)
                else:
                    # Fallback to common Epic Link field IDs
                    fields_list.extend(['customfield_10014', 'customfield_10010', 'customfield_10013', 'customfield_10015'])
                
                # Add discovered Epic Name field ID
                if epic_name_field_id:
                    fields_list.append(epic_name_field_id)
                else:
                    # Fallback to common Epic Name field ID
                    fields_list.append('customfield_10011')
                
                # Search issues using JQL with expanded fields for hierarchy
                # Include parent and epic link fields explicitly
                response = self.auth._make_request('GET', '/search', params={
                    'jql': jql,
                    'maxResults': 1000,
                    'expand': 'names,renderedFields,changelog',
                    'fields': ','.join(fields_list)
                })
                
                result_data = safe_parse_response(response)
                if result_data.get('is_html'):
                    console.print("[yellow]Warning:[/yellow] Received HTML response from /search endpoint")
                    return []
                
                issues_data = result_data.get('issues', [])
                
                progress.update(task, description="Processing issues with hierarchy...")
                
                result = []
                for issue_data in issues_data:
                    fields = issue_data.get('fields', {})
                    
                    issue_type_name = fields.get('issuetype', {}).get('name', 'Unknown')
                    status_name = fields.get('status', {}).get('name', 'Unknown')
                    project_key = issue_data.get('key', '').split('-')[0] if '-' in issue_data.get('key', '') else None
                    
                    assignee_data = fields.get('assignee')
                    assignee_name = assignee_data.get('displayName') if assignee_data else None
                    
                    # Get Parent issue key (for Subtasks) - handle multiple data formats
                    parent_key = None
                    parent_data = fields.get('parent')
                    if parent_data:
                        if isinstance(parent_data, dict):
                            parent_key = parent_data.get('key')
                        elif isinstance(parent_data, str):
                            parent_key = parent_data
                        elif hasattr(parent_data, 'key'):
                            parent_key = parent_data.key
                    
                    # Get Epic Link (for Stories/Tasks under Epics)
                    # Use discovered field ID first, then fallback to common IDs
                    parent_epic_key = None
                    epic_link = None
                    
                    # Try discovered field ID first
                    if epic_link_field_id:
                        epic_link = fields.get(epic_link_field_id)
                    
                    # Try common Epic Link field IDs as fallback
                    if not epic_link:
                        for field_id in ['customfield_10014', 'customfield_10010', 'customfield_10013', 'customfield_10015']:
                            epic_link = fields.get(field_id)
                            if epic_link:
                                break
                    
                    # Also try alternative field names
                    if not epic_link:
                        epic_link = fields.get('epic') or fields.get('parentEpic')
                    
                    if epic_link:
                        # Epic Link can be a string (key), dict with 'key', or object with 'key' attribute
                        if isinstance(epic_link, str):
                            parent_epic_key = epic_link
                        elif isinstance(epic_link, dict):
                            parent_epic_key = epic_link.get('key') or epic_link.get('value') or epic_link.get('id')
                        elif hasattr(epic_link, 'key'):
                            parent_epic_key = epic_link.key
                    
                    # Determine parent issue type
                    parent_issue_type = None
                    if parent_key:
                        # For Subtasks, parent is a Story/Task, find parent's type
                        # We'll resolve this after all issues are processed
                        parent_issue_type = None  # Will be resolved later
                    elif parent_epic_key:
                        # For Stories/Tasks under Epics, parent is Epic
                        parent_issue_type = "Epic"
                    
                    # Get Epic name/key if this is an Epic
                    epic_key = None
                    if issue_type_name.lower() == 'epic':
                        # Try discovered field ID first, then fallback
                        epic_name = None
                        if epic_name_field_id:
                            epic_name = fields.get(epic_name_field_id)
                        if not epic_name:
                            epic_name = fields.get('customfield_10011')  # Fallback to common Epic Name field
                        if epic_name:
                            epic_key = issue_data.get('key')
                    
                    # Determine hierarchy level
                    hierarchy_level = 0
                    if issue_type_name.lower() == 'epic':
                        hierarchy_level = 0
                    elif issue_type_name.lower() == 'subtask' or parent_key:
                        hierarchy_level = 2
                    else:
                        hierarchy_level = 1  # Story or Task
                    
                    # Parse created and updated dates
                    created_str = fields.get('created')
                    created = None
                    if created_str:
                        try:
                            created = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
                        except:
                            pass
                    
                    updated_str = fields.get('updated')
                    updated = None
                    if updated_str:
                        try:
                            updated = datetime.fromisoformat(updated_str.replace('Z', '+00:00'))
                        except:
                            pass
                    
                    # Create issue object first (parent_issue_type may be updated later)
                    issue_obj = Issue(
                        key=issue_data.get('key', ''),
                        summary=fields.get('summary', ''),
                        issue_type=issue_type_name,
                        status=status_name,
                        project=project_key,
                        assignee=assignee_name,
                        created=created,
                        updated=updated,
                        parent_key=parent_key,
                        parent_epic_key=parent_epic_key,
                        parent_issue_type=parent_issue_type,
                        epic_key=epic_key,
                        hierarchy_level=hierarchy_level
                    )
                    
                    result.append(issue_obj)
                
                # Resolve parent issue types and propagate parent_epic_key after all issues are processed
                issue_map = {issue.key: issue for issue in result}
                
                # Helper function to find Epic for an issue
                def find_epic_key(issue_obj: Issue) -> Optional[str]:
                    """Find Epic key by traversing parent chain."""
                    visited = set()
                    current = issue_obj
                    max_depth = 10  # Prevent infinite loops
                    depth = 0
                    
                    while current and depth < max_depth:
                        if current.key in visited:
                            break
                        visited.add(current.key)
                        
                        # If this is an Epic, return it
                        if current.issue_type.lower() == 'epic':
                            return current.key
                        
                        # If has direct parent_epic_key, use it
                        if current.parent_epic_key:
                            epic_key = current.parent_epic_key
                            if epic_key in issue_map:
                                epic_issue = issue_map[epic_key]
                                if epic_issue.issue_type.lower() == 'epic':
                                    return epic_key
                        
                        # Move up parent chain
                        if current.parent_key and current.parent_key in issue_map:
                            current = issue_map[current.parent_key]
                            depth += 1
                        else:
                            break
                    
                    return None
                
                # Resolve parent types and propagate parent_epic_key
                for issue in result:
                    if issue.parent_key and issue.parent_key in issue_map:
                        parent_issue = issue_map[issue.parent_key]
                        issue.parent_issue_type = parent_issue.issue_type
                        
                        # Propagate parent_epic_key: if parent has parent_epic_key, child should inherit it
                        if not issue.parent_epic_key and parent_issue.parent_epic_key:
                            # Verify the Epic exists
                            epic_key = parent_issue.parent_epic_key
                            if epic_key in issue_map:
                                epic_issue = issue_map[epic_key]
                                if epic_issue.issue_type.lower() == 'epic':
                                    issue.parent_epic_key = epic_key
                    elif issue.parent_epic_key and issue.parent_epic_key in issue_map:
                        # For Stories/Tasks under Epics, parent type is Epic
                        epic_issue = issue_map[issue.parent_epic_key]
                        if epic_issue.issue_type.lower() == 'epic':
                            issue.parent_issue_type = "Epic"
                    
                    # If issue doesn't have parent_epic_key but should (e.g., Task under Story with Epic)
                    if not issue.parent_epic_key and issue.parent_key and issue.parent_key in issue_map:
                        parent_issue = issue_map[issue.parent_key]
                        # Find Epic for parent and propagate to this issue
                        epic_key = find_epic_key(parent_issue)
                        if epic_key:
                            issue.parent_epic_key = epic_key
                
                progress.update(task, description=f"[green]Found {len(result)} issue(s)[/green]")
            
            return result
            
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Jira API error:[/red] {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                error_payload = extract_jira_error_payload(e.response)
                if error_payload['formatted']:
                    console.print(f"[yellow]Error details:[/yellow]\n{error_payload['formatted']}")
                console.print(f"[dim]Full error payload:[/dim] {error_payload['json_pretty'][:500]}")
            return []
        except Exception as e:
            console.print(f"[red]Error getting issues from JQL:[/red] {str(e)}")
            return []
    
    def add_worklog(self, issue_key: str, worklog_entry: WorkLogEntry) -> SyncResult:
        """Add work log to a Jira issue.
        
        Args:
            issue_key: Jira issue key
            worklog_entry: Work log entry from Excel
            
        Returns:
            SyncResult with success status and message
        """
        try:
            worklog = worklog_entry.to_worklog()
            
            # Format started datetime as ISO 8601 (JIRA format: YYYY-MM-DDTHH:MM:SS.000+0000)
            if worklog.started:
                # Ensure UTC timezone format
                started_str = worklog.started.strftime('%Y-%m-%dT%H:%M:%S.000+0000')
            else:
                # Default to start of work_date at UTC
                started = datetime.combine(worklog_entry.work_date, datetime.min.time())
                started_str = started.strftime('%Y-%m-%dT%H:%M:%S.000+0000')
            
            # Prepare worklog data
            worklog_data = {
                'timeSpentSeconds': worklog.time_spent_seconds,
                'comment': worklog.comment or '',
                'started': started_str
            }
            
            # Create work log in Jira
            response = self.auth._make_request('POST', f'/issue/{issue_key}/worklog', json=worklog_data)
            
            # Safely parse response - JIRA may return HTML even on success (201)
            worklog_result = safe_parse_response(response)
            
            # Handle HTML response on success code
            if worklog_result.get('is_html'):
                # Try to extract worklog ID from HTML
                html_text = worklog_result.get('text', '')
                worklog_id = None
                
                # Look for worklog ID in HTML
                id_patterns = [
                    r'worklog[^\s]*["\']?\s*id["\']?\s*[:=]\s*["\']?(\d+)',
                    r'id["\']?\s*:\s*["\']?(\d+)',
                    r'/worklog/(\d+)',
                    r'worklogId["\']?\s*[:=]\s*["\']?(\d+)',
                ]
                
                for pattern in id_patterns:
                    matches = re.findall(pattern, html_text, re.IGNORECASE)
                    if matches:
                        worklog_id = matches[0]
                        break
                
                # If we have a worklog_id, consider it successful
                if worklog_id:
                    console.print(f"[yellow]Note:[/yellow] Extracted worklog ID {worklog_id} from HTML response")
                    return SyncResult(
                        issue_key=issue_key,
                        success=True,
                        message=f"Work log added successfully ({worklog_entry.time_logged_hours} hours on {worklog_entry.work_date}) - HTML response received",
                        worklog_id=worklog_id
                    )
                else:
                    # No ID extracted, but status is 201 - assume success
                    return SyncResult(
                        issue_key=issue_key,
                        success=True,
                        message=f"Work log may have been added successfully ({worklog_entry.time_logged_hours} hours on {worklog_entry.work_date}) - HTML response, verify in JIRA",
                        worklog_id=''
                    )
            
            # Normal JSON response
            worklog_id = str(worklog_result.get('id', ''))
            
            return SyncResult(
                issue_key=issue_key,
                success=True,
                message=f"Work log added successfully ({worklog_entry.time_logged_hours} hours on {worklog_entry.work_date})",
                worklog_id=worklog_id
            )
            
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            error_payload = None
            if hasattr(e, 'response') and e.response is not None:
                error_payload = extract_jira_error_payload(e.response)
                if error_payload['errorMessages']:
                    error_msg = ', '.join(error_payload['errorMessages'])
                elif error_payload['errors']:
                    error_msg = ', '.join([f"{k}: {v}" for k, v in error_payload['errors'].items()])
                else:
                    error_msg = error_payload['formatted'] or error_msg
            
            # Include full error payload in message for detailed debugging
            full_error = f"{error_msg}"
            if error_payload and error_payload['json_pretty']:
                full_error += f"\n\nFull error payload:\n{error_payload['json_pretty']}"
            
            if "Worklog" in error_msg or "already" in error_msg.lower():
                return SyncResult(
                    issue_key=issue_key,
                    success=False,
                    message=f"Failed to add work log: {full_error}"
                )
            return SyncResult(
                issue_key=issue_key,
                success=False,
                message=f"Jira API error: {full_error}"
            )
        except Exception as e:
            return SyncResult(
                issue_key=issue_key,
                success=False,
                message=f"Unexpected error: {str(e)}"
            )
    
    def add_worklogs_batch(self, worklog_entries: List[WorkLogEntry], dry_run: bool = False) -> List[SyncResult]:
        """Add multiple work logs in batch.
        
        Args:
            worklog_entries: List of work log entries
            dry_run: If True, validate only without adding
            
        Returns:
            List of SyncResult objects
        """
        results = []
        
        if dry_run:
            console.print("[yellow]DRY RUN MODE:[/yellow] Validating work logs without adding to Jira...\n")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(
                f"[cyan]Processing {len(worklog_entries)} work log(s)...[/cyan]",
                total=len(worklog_entries)
            )
            
            for entry in worklog_entries:
                if dry_run:
                    # Just validate
                    try:
                        # Validate issue key exists
                        try:
                            self.auth._make_request('GET', f'/issue/{entry.issue_key}')
                            results.append(SyncResult(
                                issue_key=entry.issue_key,
                                success=True,
                                message=f"Validation passed ({entry.time_logged_hours}h on {entry.work_date})"
                            ))
                        except requests.exceptions.RequestException:
                            results.append(SyncResult(
                                issue_key=entry.issue_key,
                                success=False,
                                message=f"Issue {entry.issue_key} not found"
                            ))
                    except Exception as e:
                        results.append(SyncResult(
                            issue_key=entry.issue_key,
                            success=False,
                            message=f"Validation error: {str(e)}"
                        ))
                else:
                    # Actually add work log
                    result = self.add_worklog(entry.issue_key, entry)
                    results.append(result)
                
                progress.advance(task)
        
        return results
    
    def get_worklogs_from_filter(
        self, 
        filter_id: str, 
        include_all_issues: bool = True,
        filter_by_current_user: bool = True,
        time_range: Optional[str] = None  # 'previous' or 'current' month
    ) -> List[ExistingWorkLog]:
        """Get existing work logs from issues in a filter.
        
        Args:
            filter_id: Jira filter ID
            include_all_issues: If True, include all issues even if they have no worklogs (default: True)
            filter_by_current_user: If True, only include worklogs from current user (default: True)
            time_range: Time range filter - 'previous' for previous month, 'current' for current month, None for all
            
        Returns:
            List of ExistingWorkLog objects (includes empty worklogs for issues with no worklogs if include_all_issues=True)
        """
        try:
            from .filter_service import FilterService
            filter_service = FilterService(self.auth)
            jql = filter_service.get_filter_jql(filter_id)
            
            if not jql:
                console.print(f"[red]Filter {filter_id} not found or has no JQL query.[/red]")
                return []
            
            return self.get_worklogs_from_jql(
                jql, 
                include_all_issues=include_all_issues,
                filter_by_current_user=filter_by_current_user,
                time_range=time_range
            )
            
        except Exception as e:
            console.print(f"[red]Error getting worklogs from filter:[/red] {str(e)}")
            return []
    
    def get_worklogs_from_jql(
        self, 
        jql: str,
        include_all_issues: bool = True,
        filter_by_current_user: bool = True,
        time_range: Optional[str] = None  # 'previous' or 'current' month
    ) -> List[ExistingWorkLog]:
        """Get existing work logs from issues in JQL query.
        
        Args:
            jql: JQL query string
            include_all_issues: If True, include all issues even if they have no worklogs (default: True)
            filter_by_current_user: If True, only include worklogs from current user (default: True)
            time_range: Time range filter - 'previous' for previous month, 'current' for current month, None for all
            
        Returns:
            List of ExistingWorkLog objects (includes empty worklogs for issues with no worklogs if include_all_issues=True)
        """
        try:
            # Get current user if filtering by user
            current_user_account_id = None
            current_user_name = None
            if filter_by_current_user:
                user_info = self.get_current_user()
                if user_info:
                    current_user_account_id = user_info.get('accountId')
                    current_user_name = user_info.get('name') or user_info.get('key')
                    if not current_user_account_id and current_user_name:
                        # Fallback to name if accountId not available
                        console.print(f"[dim]Using username '{current_user_name}' for worklog filtering[/dim]")
                else:
                    console.print("[yellow]Warning:[/yellow] Could not get current user info, filtering by user disabled")
                    filter_by_current_user = False
            
            # Calculate time range if specified
            time_start = None
            time_end = None
            if time_range in ['previous', 'current']:
                now = datetime.now()
                if time_range == 'current':
                    # Current month: first day of current month to last day of current month
                    time_start = datetime(now.year, now.month, 1)
                    last_day = monthrange(now.year, now.month)[1]
                    time_end = datetime(now.year, now.month, last_day, 23, 59, 59)
                elif time_range == 'previous':
                    # Previous month: first day of previous month to last day of previous month
                    if now.month == 1:
                        prev_month = 12
                        prev_year = now.year - 1
                    else:
                        prev_month = now.month - 1
                        prev_year = now.year
                    time_start = datetime(prev_year, prev_month, 1)
                    last_day = monthrange(prev_year, prev_month)[1]
                    time_end = datetime(prev_year, prev_month, last_day, 23, 59, 59)
                
                console.print(f"[dim]Filtering worklogs by time range: {time_start.date()} to {time_end.date()}[/dim]")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Fetching issues from Jira...", total=None)
                
                # Search issues using JQL
                response = self.auth._make_request('GET', '/search', params={
                    'jql': jql,
                    'maxResults': 1000,
                    'expand': 'names'
                })
                
                result = safe_parse_response(response)
                if result.get('is_html'):
                    console.print("[yellow]Warning:[/yellow] Received HTML response from /search endpoint")
                    return []
                
                issues_data = result.get('issues', [])
                
                progress.update(task, description=f"Processing {len(issues_data)} issue(s)...")
                
                worklogs = []
                issues_with_worklogs = set()
                
                for issue_data in issues_data:
                    issue_key = issue_data.get('key', '')
                    issue_has_worklogs = False
                    
                    try:
                        # Get worklogs for this issue
                        worklog_response = self.auth._make_request('GET', f'/issue/{issue_key}/worklog')
                        worklog_result = safe_parse_response(worklog_response)
                        
                        if worklog_result.get('is_html'):
                            # HTML response - skip this issue
                            if include_all_issues:
                                worklogs.append(ExistingWorkLog.create_empty(issue_key))
                            continue
                        
                        issue_worklogs = worklog_result.get('worklogs', [])
                        
                        for wl in issue_worklogs:
                            # Filter by current user if enabled
                            if filter_by_current_user:
                                author_data = wl.get('author', {})
                                wl_account_id = author_data.get('accountId')
                                wl_name = author_data.get('name') or author_data.get('key')
                                
                                # Match by accountId first, fallback to name
                                if current_user_account_id:
                                    if wl_account_id != current_user_account_id:
                                        continue
                                elif current_user_name:
                                    if wl_name != current_user_name:
                                        continue
                                else:
                                    continue
                            
                            # Filter by time range if specified
                            if time_range and (time_start or time_end):
                                started_str = wl.get('started')
                                if started_str:
                                    try:
                                        started = datetime.fromisoformat(started_str.replace('Z', '+00:00'))
                                        # Convert to local time for comparison
                                        if started.tzinfo:
                                            started = started.replace(tzinfo=None)
                                        
                                        # Check if worklog is within time range
                                        if time_start and started < time_start:
                                            continue
                                        if time_end and started > time_end:
                                            continue
                                    except:
                                        # If we can't parse the date, skip this worklog
                                        continue
                            
                            time_spent_seconds = wl.get('timeSpentSeconds', 0)
                            time_spent_hours = Decimal(str(time_spent_seconds)) / Decimal("3600")
                            
                            started_str = wl.get('started')
                            started = None
                            if started_str:
                                try:
                                    started = datetime.fromisoformat(started_str.replace('Z', '+00:00'))
                                except:
                                    started = datetime.now()
                            else:
                                started = datetime.now()
                            
                            comment = wl.get('comment', '')
                            author_data = wl.get('author', {})
                            author = author_data.get('displayName') if author_data else None
                            
                            worklogs.append(ExistingWorkLog(
                                worklog_id=str(wl.get('id', '')),
                                issue_key=issue_key,
                                time_spent_seconds=time_spent_seconds,
                                time_spent_hours=time_spent_hours,
                                comment=comment or "",
                                started=started,
                                author=author
                            ))
                            issue_has_worklogs = True
                            issues_with_worklogs.add(issue_key)
                    except requests.exceptions.RequestException:
                        # Issue doesn't have worklog access or doesn't exist
                        if include_all_issues:
                            worklogs.append(ExistingWorkLog.create_empty(issue_key))
                        continue
                    
                    # If include_all_issues and this issue has no matching worklogs, add empty entry
                    if include_all_issues and not issue_has_worklogs and issue_key not in issues_with_worklogs:
                        worklogs.append(ExistingWorkLog.create_empty(issue_key))
                
                progress.update(task, description=f"[green]Found {len(worklogs)} work log entry(ies)[/green]")
            
            return worklogs
            
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Jira API error:[/red] {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                error_payload = extract_jira_error_payload(e.response)
                if error_payload['formatted']:
                    console.print(f"[yellow]Error details:[/yellow]\n{error_payload['formatted']}")
            return []
        except Exception as e:
            console.print(f"[red]Error getting worklogs from JQL:[/red] {str(e)}")
            return []
    
    def update_worklog(self, worklog_update: WorkLogUpdate) -> SyncResult:
        """Update an existing work log in Jira.
        
        Args:
            worklog_update: Work log update entry
            
        Returns:
            SyncResult with success status and message
        """
        try:
            # Convert new time to seconds
            new_time_seconds = int(float(worklog_update.new_time_hours) * 3600)
            
            # Convert date to datetime
            started = datetime.combine(worklog_update.work_date, datetime.min.time())
            started_str = started.strftime('%Y-%m-%dT%H:%M:%S.000+0000')
            
            # Prepare update data
            worklog_data = {
                'timeSpentSeconds': new_time_seconds,
                'comment': worklog_update.new_comment or "",
                'started': started_str
            }
            
            # Update work log using Jira API
            self.auth._make_request('PUT', f'/issue/{worklog_update.issue_key}/worklog/{worklog_update.worklog_id}', json=worklog_data)
            
            return SyncResult(
                issue_key=worklog_update.issue_key,
                worklog_id=worklog_update.worklog_id,
                success=True,
                message=f"Work log updated successfully ({worklog_update.original_time_hours}h -> {worklog_update.new_time_hours}h)",
                operation="update"
            )
            
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            error_payload = None
            if hasattr(e, 'response') and e.response is not None:
                error_payload = extract_jira_error_payload(e.response)
                if error_payload['errorMessages']:
                    error_msg = ', '.join(error_payload['errorMessages'])
                elif error_payload['errors']:
                    error_msg = ', '.join([f"{k}: {v}" for k, v in error_payload['errors'].items()])
                else:
                    error_msg = error_payload['formatted'] or error_msg
            
            # Include full error payload in message for detailed debugging
            full_error = f"{error_msg}"
            if error_payload and error_payload['json_pretty']:
                full_error += f"\n\nFull error payload:\n{error_payload['json_pretty']}"
            
            return SyncResult(
                issue_key=worklog_update.issue_key,
                worklog_id=worklog_update.worklog_id,
                success=False,
                message=f"Failed to update work log: {full_error}",
                operation="update"
            )
        except Exception as e:
            return SyncResult(
                issue_key=worklog_update.issue_key,
                worklog_id=worklog_update.worklog_id,
                success=False,
                message=f"Unexpected error: {str(e)}",
                operation="update"
            )
    
    def update_worklogs_from_diff(self, worklog_updates: List[WorkLogUpdate], dry_run: bool = False) -> List[SyncResult]:
        """Update multiple work logs from diff comparison.
        
        Args:
            worklog_updates: List of work log updates
            dry_run: If True, validate only without updating
            
        Returns:
            List of SyncResult objects
        """
        results = []
        
        # Filter only entries with changes
        updates_with_changes = [u for u in worklog_updates if u.has_changes()]
        
        if not updates_with_changes:
            console.print("[yellow]No changes detected in work logs.[/yellow]")
            return []
        
        if dry_run:
            console.print("[yellow]DRY RUN MODE:[/yellow] Validating work log updates without applying...\n")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(
                f"[cyan]Processing {len(updates_with_changes)} work log update(s)...[/cyan]",
                total=len(updates_with_changes)
            )
            
            for update in updates_with_changes:
                if dry_run:
                    # Just validate
                    try:
                        # Validate worklog exists
                        try:
                            self.auth._make_request('GET', f'/issue/{update.issue_key}/worklog/{update.worklog_id}')
                            results.append(SyncResult(
                                issue_key=update.issue_key,
                                worklog_id=update.worklog_id,
                                success=True,
                                message=f"Validation passed ({update.original_time_hours}h -> {update.new_time_hours}h)",
                                operation="update"
                            ))
                        except requests.exceptions.RequestException:
                            results.append(SyncResult(
                                issue_key=update.issue_key,
                                worklog_id=update.worklog_id,
                                success=False,
                                message=f"Work log {update.worklog_id} not found",
                                operation="update"
                            ))
                    except Exception as e:
                        results.append(SyncResult(
                            issue_key=update.issue_key,
                            worklog_id=update.worklog_id,
                            success=False,
                            message=f"Validation error: {str(e)}",
                            operation="update"
                        ))
                else:
                    # Actually update work log
                    result = self.update_worklog(update)
                    results.append(result)
                
                progress.advance(task)
        
        return results
