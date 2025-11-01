"""Jira filter and JQL query service using requests library."""

from typing import List, Optional
import requests
from rich.console import Console
from rich.table import Table

from ..config.auth import JiraAuth

console = Console()


class FilterService:
    """Service for managing Jira filters and JQL queries using requests library."""
    
    def __init__(self, auth: Optional[JiraAuth] = None):
        """Initialize filter service.
        
        Args:
            auth: Jira authentication handler (creates new if None)
        """
        self.auth = auth or JiraAuth()
    
    def list_filters(self) -> List[dict]:
        """List all saved Jira filters.
        
        Returns:
            List of filter dictionaries with id, name, jql keys
        """
        try:
            # Get favorite filters
            response = self.auth._make_request('GET', '/filter/favourite')
            filters_data = response.json()
            
            return [
                {
                    "id": str(f.get('id', '')),
                    "name": f.get('name', ''),
                    "jql": f.get('jql', ''),
                    "description": f.get('description', '')
                }
                for f in filters_data
            ]
        except requests.exceptions.RequestException as e:
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
            # Try to get filter from favorites first
            filters = self.list_filters()
            for f in filters:
                if f["id"] == filter_id:
                    if f["jql"]:
                        return f["jql"]
            
            # If not in favorites, fetch filter details directly
            try:
                response = self.auth._make_request('GET', f'/filter/{filter_id}')
                filter_data = response.json()
                return filter_data.get('jql', None)
            except requests.exceptions.RequestException:
                return None
                
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Error getting filter JQL:[/red] {str(e)}")
            return None
        except Exception as e:
            console.print(f"[red]Unexpected error getting filter JQL:[/red] {str(e)}")
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
