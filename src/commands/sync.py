"""Sync command for Jira Work Log Tool."""

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
    help='Jira filter ID to export issues from (for export step)'
)
@click.option(
    '--jql',
    type=str,
    help='JQL query to export issues from (for export step)'
)
@click.option(
    '--output',
    type=str,
    default='worklog.xlsx',
    help='Output Excel file path (for export step, default: worklog.xlsx)'
)
@click.option(
    '--input',
    'input_file',
    type=str,
    help='Input Excel file path (for import step)'
)
@click.option(
    '--auto-import',
    is_flag=True,
    help='Automatically import after export (optional)'
)
@click.option(
    '--dry-run',
    is_flag=True,
    help='Validate only, do not actually import to Jira (for import step)'
)
@click.option(
    '--verbose',
    is_flag=True,
    help='Show verbose output'
)
def sync(filter: str, jql: str, output: str, input_file: str, auto_import: bool, dry_run: bool, verbose: bool):
    """Complete sync workflow: export issues to Excel, then import work logs back.
    
    This command can be used in two ways:
    
    1. Export mode: Export issues from filter/JQL to Excel
    2. Import mode: Import work logs from edited Excel to Jira
    
    Examples:
    
    \b
    Export to Excel:
    $ python -m src.main sync --filter 12345 --output worklog.xlsx
    
    \b
    Import from Excel:
    $ python -m src.main sync --input worklog.xlsx
    
    \b
    Export and auto-import (advanced):
    $ python -m src.main sync --filter 12345 --output worklog.xlsx --auto-import
    """
    try:
        # Determine mode based on input
        if input_file:
            # Import mode - reuse import logic
            from ..commands.import_cmd import import_cmd
            import_cmd.callback(input_file=input_file, dry_run=dry_run, verbose=verbose)
            
        elif filter or jql:
            # Export mode - reuse export logic
            from ..commands.export import export
            export.callback(filter=filter, jql=jql, output=output, verbose=verbose)
            
            if auto_import:
                console.print("\n[yellow]Auto-import enabled, but you should edit the Excel file first.[/yellow]")
                console.print("[dim]Please edit the Excel file, then run:[/dim]")
                console.print(f"[cyan]python -m src.main sync --input {output}[/cyan]")
            
        else:
            console.print(Panel(
                "[red]Error:[/red] Either --filter/--jql (for export) or --input (for import) is required.\n\n"
                "[yellow]Examples:[/yellow]\n"
                "  sync --filter 12345 --output worklog.xlsx\n"
                "  sync --input worklog.xlsx",
                title="Sync Command",
                border_style="red"
            ))
            raise click.Abort()
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Sync cancelled by user.[/yellow]")
        raise click.Abort()
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {str(e)}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        raise click.Abort()

