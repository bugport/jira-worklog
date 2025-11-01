"""Jira filter and JQL query service using requests library."""

from typing import List, Optional
import requests
from rich.console import Console
from rich.table import Table

from ..config.auth import JiraAuth, extract_jira_error_payload, safe_parse_response

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
            if hasattr(e, 'response') and e.response is not None:
                error_payload = extract_jira_error_payload(e.response)
                if error_payload['formatted']:
                    console.print(f"[yellow]Error details:[/yellow]\n{error_payload['formatted']}")
                console.print(f"[dim]Full error payload:[/dim] {error_payload['json_pretty'][:500]}")
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
                filter_data = safe_parse_response(response)
                if filter_data.get('is_html'):
                    console.print(f"[yellow]Warning:[/yellow] Received HTML response from /filter/{filter_id} endpoint")
                    return None
                return filter_data.get('jql', None)
            except requests.exceptions.RequestException:
                return None
                
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Error getting filter JQL:[/red] {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                error_payload = extract_jira_error_payload(e.response)
                if error_payload['formatted']:
                    console.print(f"[yellow]Error details:[/yellow]\n{error_payload['formatted']}")
                console.print(f"[dim]Full error payload:[/dim] {error_payload['json_pretty'][:500]}")
            return None
        except Exception as e:
            console.print(f"[red]Unexpected error getting filter JQL:[/red] {str(e)}")
            return None
    
    def combine_filters_jql(self, filter_ids: List[str]) -> Optional[str]:
        """Combine multiple filter JQL queries using OR operator.
        
        Args:
            filter_ids: List of Jira filter IDs
            
        Returns:
            Combined JQL query string or None if all filters failed
        """
        import re
        
        jql_queries = []
        order_by_clauses = []
        
        for filter_id in filter_ids:
            jql = self.get_filter_jql(filter_id)
            if jql:
                # Extract ORDER BY clause if present (case-insensitive)
                # ORDER BY must come after all conditions, so we match it at the end
                order_by_pattern = r'\s+ORDER\s+BY\s+[^\s]+(?:\s+[A-Z]+)?(?:\s*,\s*[^\s]+(?:\s+[A-Z]+)?)*'
                order_by_match = re.search(order_by_pattern, jql, re.IGNORECASE)
                
                if order_by_match:
                    # Extract ORDER BY clause
                    order_by_clause = order_by_match.group(0).strip()
                    order_by_clauses.append(order_by_clause)
                    # Remove ORDER BY from JQL for combining
                    jql_without_order = jql[:order_by_match.start()].strip()
                else:
                    jql_without_order = jql.strip()
                
                # Wrap cleaned JQL in parentheses for proper OR combination
                jql_queries.append(f"({jql_without_order})")
            else:
                console.print(f"[yellow]Warning:[/yellow] Filter {filter_id} not found or has no JQL query")
        
        if not jql_queries:
            console.print("[red]No valid filters found to combine.[/red]")
            return None
        
        # Combine with OR operator
        combined_jql = " OR ".join(jql_queries)
        
        # Add ORDER BY clause at the end if any filter had one
        # Use the first ORDER BY clause found (if multiple filters have ORDER BY, use the first)
        if order_by_clauses:
            # Remove any trailing whitespace before adding ORDER BY
            combined_jql = combined_jql.rstrip()
            # Use the first ORDER BY clause (most common case)
            combined_jql = f"{combined_jql} {order_by_clauses[0]}"
        
        return combined_jql
    
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
