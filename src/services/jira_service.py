"""Jira API service for issues and work logs using requests library."""

from typing import List, Optional
from datetime import datetime, date
import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..config.auth import JiraAuth
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
                
                # Search issues using JQL
                response = self.auth._make_request('GET', '/search', params={
                    'jql': jql,
                    'maxResults': 1000,
                    'expand': 'names'
                })
                
                data = response.json()
                issues_data = data.get('issues', [])
                
                progress.update(task, description="Processing issues...")
                
                result = []
                for issue_data in issues_data:
                    fields = issue_data.get('fields', {})
                    
                    issue_type_name = fields.get('issuetype', {}).get('name', 'Unknown')
                    status_name = fields.get('status', {}).get('name', 'Unknown')
                    project_key = issue_data.get('key', '').split('-')[0] if '-' in issue_data.get('key', '') else None
                    
                    assignee_data = fields.get('assignee')
                    assignee_name = assignee_data.get('displayName') if assignee_data else None
                    
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
                    
                    result.append(Issue(
                        key=issue_data.get('key', ''),
                        summary=fields.get('summary', ''),
                        issue_type=issue_type_name,
                        status=status_name,
                        project=project_key,
                        assignee=assignee_name,
                        created=created,
                        updated=updated
                    ))
                
                progress.update(task, description=f"[green]Found {len(result)} issue(s)[/green]")
            
            return result
            
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Jira API error:[/red] {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get('errorMessages', []) or error_data.get('errors', {})
                    if error_msg:
                        console.print(f"[yellow]Error details:[/yellow] {error_msg}")
                except:
                    pass
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
            worklog_result = response.json()
            
            worklog_id = str(worklog_result.get('id', ''))
            
            return SyncResult(
                issue_key=issue_key,
                success=True,
                message=f"Work log added successfully ({worklog_entry.time_logged_hours} hours on {worklog_entry.work_date})",
                worklog_id=worklog_id
            )
            
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = ' '.join(error_data.get('errorMessages', [])) or str(error_data.get('errors', error_msg))
                except:
                    pass
            
            if "Worklog" in error_msg or "already" in error_msg.lower():
                return SyncResult(
                    issue_key=issue_key,
                    success=False,
                    message=f"Failed to add work log: {error_msg}"
                )
            return SyncResult(
                issue_key=issue_key,
                success=False,
                message=f"Jira API error: {error_msg}"
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
    
    def get_worklogs_from_filter(self, filter_id: str) -> List[ExistingWorkLog]:
        """Get existing work logs from issues in a filter.
        
        Args:
            filter_id: Jira filter ID
            
        Returns:
            List of ExistingWorkLog objects
        """
        try:
            from .filter_service import FilterService
            filter_service = FilterService(self.auth)
            jql = filter_service.get_filter_jql(filter_id)
            
            if not jql:
                console.print(f"[red]Filter {filter_id} not found or has no JQL query.[/red]")
                return []
            
            return self.get_worklogs_from_jql(jql)
            
        except Exception as e:
            console.print(f"[red]Error getting worklogs from filter:[/red] {str(e)}")
            return []
    
    def get_worklogs_from_jql(self, jql: str) -> List[ExistingWorkLog]:
        """Get existing work logs from issues in JQL query.
        
        Args:
            jql: JQL query string
            
        Returns:
            List of ExistingWorkLog objects
        """
        try:
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
                
                data = response.json()
                issues_data = data.get('issues', [])
                
                progress.update(task, description="Fetching work logs...")
                
                worklogs = []
                for issue_data in issues_data:
                    issue_key = issue_data.get('key', '')
                    try:
                        # Get worklogs for this issue
                        worklog_response = self.auth._make_request('GET', f'/issue/{issue_key}/worklog')
                        worklog_data = worklog_response.json()
                        issue_worklogs = worklog_data.get('worklogs', [])
                        
                        for wl in issue_worklogs:
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
                    except requests.exceptions.RequestException:
                        # Skip issues without worklog access
                        continue
                
                progress.update(task, description=f"[green]Found {len(worklogs)} work log(s)[/green]")
            
            return worklogs
            
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Jira API error:[/red] {str(e)}")
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
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = ' '.join(error_data.get('errorMessages', [])) or str(error_data.get('errors', error_msg))
                except:
                    pass
            
            return SyncResult(
                issue_key=worklog_update.issue_key,
                worklog_id=worklog_update.worklog_id,
                success=False,
                message=f"Failed to update work log: {error_msg}",
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
