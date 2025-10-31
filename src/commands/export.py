"""Export command for Jira Work Log Tool."""

import click
from rich.console import Console
from rich.panel import Panel

from ..services.jira_service import JiraService
from ..services.excel_service import ExcelService
from ..config.auth import JiraAuth

console = Console()


@click.command()
@click.option(
    '--filter',
    type=str,
    help='Jira filter ID to export issues from'
)
@click.option(
    '--jql',
    type=str,
    help='JQL query to export issues from'
)
@click.option(
    '--output',
    type=str,
    default='worklog.xlsx',
    help='Output Excel file path (default: worklog.xlsx)'
)
@click.option(
    '--verbose',
    is_flag=True,
    help='Show verbose output'
)
def export(filter: str, jql: str, output: str, verbose: bool):
    """Export Jira issues to Excel template for time logging.
    
    Export issues from a Jira filter or JQL query to an Excel template
    where you can log time spent on each issue.
    
    Examples:
    
    \b
    Export from a filter:
    $ python -m src.main export --filter 12345 --output worklog.xlsx
    
    \b
    Export from JQL query:
    $ python -m src.main export --jql "project = PROJ AND status = 'In Progress'"
    
    \b
    Export with verbose output:
    $ python -m src.main export --filter 12345 --verbose
    """
    try:
        # Validate input
        if not filter and not jql:
            console.print(Panel(
                "[red]Error:[/red] Either --filter or --jql is required.\n\n"
                "[yellow]Examples:[/yellow]\n"
                "  export --filter 12345 --output worklog.xlsx\n"
                "  export --jql \"project = PROJ AND status = 'In Progress'\"",
                title="Export Command",
                border_style="red"
            ))
            raise click.Abort()
        
        # Initialize services
        auth = JiraAuth()
        jira_service = JiraService(auth)
        excel_service = ExcelService()
        
        # Get issues
        if filter:
            if verbose:
                console.print(f"[cyan]Fetching issues from filter:[/cyan] {filter}")
            issues = jira_service.get_issues_from_filter(filter)
        else:
            if verbose:
                console.print(f"[cyan]Fetching issues from JQL:[/cyan] {jql}")
            issues = jira_service.get_issues_from_jql(jql)
        
        if not issues:
            console.print("[yellow]No issues found to export.[/yellow]")
            if filter:
                console.print(f"[dim]Check if filter {filter} exists and contains issues.[/dim]")
            else:
                console.print("[dim]Check your JQL query syntax.[/dim]")
            raise click.Abort()
        
        # Export to Excel
        success = excel_service.export_issues_to_excel(issues, output)
        
        if success:
            console.print(Panel(
                f"[green]✓[/green] Export completed successfully!\n\n"
                f"File: [cyan]{output}[/cyan]\n"
                f"Issues: [green]{len(issues)}[/green]\n\n"
                f"[yellow]Next steps:[/yellow]\n"
                f"1. Open {output} in Excel\n"
                f"2. Fill in 'Time Logged (hours)' column (decimal, e.g., 2.5)\n"
                f"3. Fill in 'Date' column (YYYY-MM-DD format)\n"
                f"4. Optionally add comments\n"
                f"5. Run: [cyan]python -m src.main import --input {output}[/cyan]",
                title="Export Success",
                border_style="green"
            ))
        else:
            console.print("[red]Export failed. Please check the error messages above.[/red]")
            raise click.Abort()
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Export cancelled by user.[/yellow]")
        raise click.Abort()
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {str(e)}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        raise click.Abort()

