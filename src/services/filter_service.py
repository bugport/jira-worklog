"""Jira filter and JQL query service."""

from typing import List, Optional
from jira import JIRA
from jira.exceptions import JIRAError
from rich.console import Console
from rich.table import Table

from ..config.auth import JiraAuth
from ..models.issue import Issue

console = Console()


class FilterService:
    """Service for managing Jira filters and JQL queries."""
    
    def __init__(self, auth: Optional[JiraAuth] = None):
        """Initialize filter service.
        
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
    
    def list_filters(self) -> List[dict]:
        """List all saved Jira filters.
        
        Returns:
            List of filter dictionaries with id, name, jql keys
        """
        try:
            filters = self.client.favourite_filters()
            return [
                {
                    "id": str(f.id),
                    "name": f.name,
                    "jql": f.jql if hasattr(f, 'jql') else "",
                    "description": getattr(f, 'description', '')
                }
                for f in filters
            ]
        except JIRAError as e:
            console.print(f"[red]Error listing filters:[/red] {str(e)}")
            return []
        except Exception as e:
            console.print(f"[red]Unexpected error listing filters:[/red] {str(e)}")
            return []
    
    def get_filter_jql(self, filter_id: str) -> Optional[str]:
        """Get JQL query from filter ID.
        
        Args:
            filter_id: Jira filter ID
            
        Returns:
            JQL query string or None if not found
        """
        try:
            filters = self.list_filters()
            for f in filters:
                if f["id"] == filter_id:
                    if f["jql"]:
                        return f["jql"]
                    # If jql not in list, fetch full filter details
                    filter_obj = self.client.filter(filter_id)
                    return filter_obj.jql if hasattr(filter_obj, 'jql') else None
            return None
        except JIRAError as e:
            console.print(f"[red]Error getting filter JQL:[/red] {str(e)}")
            return None
    
    def display_filters(self):
        """Display all filters in a formatted table."""
        filters = self.list_filters()
        
        if not filters:
            console.print("[yellow]No filters found.[/yellow]")
            console.print("You can create filters in Jira and mark them as favorites.")
            return
        
        table = Table(title="Available Jira Filters", show_header=True, header_style="bold cyan")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="green")
        table.add_column("JQL Query", style="yellow", overflow="fold")
        
        for f in filters:
            jql_display = f["jql"][:50] + "..." if len(f["jql"]) > 50 else f["jql"]
            table.add_row(f["id"], f["name"], jql_display)
        
        console.print(table)
        console.print(f"\n[dim]Found {len(filters)} filter(s). Use --filter <id> to export issues.[/dim]")

