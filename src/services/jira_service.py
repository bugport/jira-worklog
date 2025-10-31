"""Jira API service for issues and work logs."""

from typing import List, Optional
from datetime import datetime, date
from jira import JIRA
from jira.exceptions import JIRAError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..config.auth import JiraAuth
from ..models.issue import Issue
from ..models.worklog import WorkLog, WorkLogEntry, SyncResult, ExistingWorkLog, WorkLogUpdate
from ..utils.formatters import format_time_hours
from decimal import Decimal

console = Console()


class JiraService:
    """Service for Jira API operations."""
    
    def __init__(self, auth: Optional[JiraAuth] = None):
        """Initialize Jira service.
        
        Args:
            auth: Jira authentication handler (creates new if None)
        """
        self.auth = auth or JiraAuth()
        self._client: Optional[JIRA] = None
    
    @property
    def client(self) -> JIRA:
        """Get Jira client instance."""
        if self._client is None:
            self._client = self.auth.client
        return self._client
    
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
                
                issues = self.client.search_issues(jql, maxResults=1000, expand='names')
                
                progress.update(task, description="Processing issues...")
                
                result = []
                for issue in issues:
                    issue_type = issue.fields.issuetype.name if hasattr(issue.fields, 'issuetype') else "Unknown"
                    status = issue.fields.status.name if hasattr(issue.fields, 'status') else "Unknown"
                    project = issue.fields.project.key if hasattr(issue.fields, 'project') else None
                    
                    result.append(Issue(
                        key=issue.key,
                        summary=issue.fields.summary,
                        issue_type=issue_type,
                        status=status,
                        project=project,
                        assignee=getattr(issue.fields.assignee, 'displayName', None) if hasattr(issue.fields, 'assignee') and issue.fields.assignee else None,
                        created=datetime.fromisoformat(issue.fields.created.replace('Z', '+00:00')) if hasattr(issue.fields, 'created') else None,
                        updated=datetime.fromisoformat(issue.fields.updated.replace('Z', '+00:00')) if hasattr(issue.fields, 'updated') else None
                    ))
                
                progress.update(task, description=f"[green]Found {len(result)} issue(s)[/green]")
            
            return result
            
        except JIRAError as e:
            console.print(f"[red]Jira API error:[/red] {str(e)}")
            if "JQL" in str(e):
                console.print("[yellow]Please check your JQL query syntax.[/yellow]")
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
            issue = self.client.issue(issue_key)
            worklog = worklog_entry.to_worklog()
            
            # Create work log in Jira
            worklog_obj = self.client.add_worklog(
                issue=issue_key,
                timeSpentSeconds=worklog.time_spent_seconds,
                comment=worklog.comment,
                started=worklog.started
            )
            
            return SyncResult(
                issue_key=issue_key,
                success=True,
                message=f"Work log added successfully ({worklog_entry.time_logged_hours} hours on {worklog_entry.date})",
                worklog_id=str(worklog_obj.id) if hasattr(worklog_obj, 'id') else None
            )
            
        except JIRAError as e:
            error_msg = str(e)
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
                            issue = self.client.issue(entry.issue_key)
                            results.append(SyncResult(
                                issue_key=entry.issue_key,
                                success=True,
                                message=f"Validation passed ({entry.time_logged_hours}h on {entry.date})"
                            ))
                        except JIRAError:
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
                
                issues = self.client.search_issues(jql, maxResults=1000, expand='names')
                
                progress.update(task, description="Fetching work logs...")
                
                worklogs = []
                for issue in issues:
                    try:
                        issue_worklogs = self.client.worklogs(issue.key)
                        for wl in issue_worklogs:
                            time_spent_hours = Decimal(str(wl.timeSpentSeconds)) / Decimal("3600")
                            
                            worklogs.append(ExistingWorkLog(
                                worklog_id=str(wl.id),
                                issue_key=issue.key,
                                time_spent_seconds=wl.timeSpentSeconds,
                                time_spent_hours=time_spent_hours,
                                comment=getattr(wl, 'comment', None) or "",
                                started=datetime.fromisoformat(wl.started.replace('Z', '+00:00')) if hasattr(wl, 'started') and wl.started else datetime.now(),
                                author=getattr(wl, 'author', {}).get('displayName', None) if hasattr(wl, 'author') else None
                            ))
                    except JIRAError:
                        # Skip issues without worklog access
                        continue
                
                progress.update(task, description=f"[green]Found {len(worklogs)} work log(s)[/green]")
            
            return worklogs
            
        except JIRAError as e:
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
            started = datetime.combine(worklog_update.date, datetime.min.time())
            
            # Update work log using Jira API
            # Use the Jira library's worklog update method
            worklog = self.client.worklog(worklog_update.issue_key, worklog_update.worklog_id)
            
            # Update work log fields
            worklog.update(
                timeSpent=new_time_seconds,
                comment=worklog_update.new_comment or "",
                started=started
            )
            
            return SyncResult(
                issue_key=worklog_update.issue_key,
                worklog_id=worklog_update.worklog_id,
                success=True,
                message=f"Work log updated successfully ({worklog_update.original_time_hours}h -> {worklog_update.new_time_hours}h)",
                operation="update"
            )
            
        except JIRAError as e:
            error_msg = str(e)
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
                            worklog = self.client.worklog(update.issue_key, update.worklog_id)
                            results.append(SyncResult(
                                issue_key=update.issue_key,
                                worklog_id=update.worklog_id,
                                success=True,
                                message=f"Validation passed ({update.original_time_hours}h -> {update.new_time_hours}h)",
                                operation="update"
                            ))
                        except JIRAError:
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

