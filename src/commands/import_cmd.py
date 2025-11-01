"""Import command for Jira Work Log Tool."""

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..services.jira_service import JiraService
from ..services.excel_service import ExcelService
from ..config.auth import JiraAuth

console = Console()


@click.command()
@click.option(
    '--input',
    'input_file',
    type=str,
    required=True,
    help='Input Excel file path'
)
@click.option(
    '--dry-run',
    is_flag=True,
    help='Validate only, do not actually import to Jira'
)
@click.option(
    '--verbose',
    is_flag=True,
    help='Show verbose output'
)
def import_cmd(input_file: str, dry_run: bool, verbose: bool):
    """Import work logs from edited Excel file back to Jira.
    
    Import work logs from an Excel file that was exported and edited.
    The Excel file should contain time logged entries with issue keys,
    time in hours, dates, and optional comments.
    
    Examples:
    
    \b
    Validate Excel file without importing:
    $ python -m src.main import --input worklog.xlsx --dry-run
    
    \b
    Import work logs to Jira:
    $ python -m src.main import --input worklog.xlsx
    
    \b
    Import with verbose output:
    $ python -m src.main import --input worklog.xlsx --verbose
    """
    try:
        # Initialize services
        auth = JiraAuth()
        jira_service = JiraService(auth)
        excel_service = ExcelService()
        
        if dry_run:
            console.print(Panel(
                "[yellow]DRY RUN MODE[/yellow]\n\n"
                "Validating Excel file without importing to Jira.\n"
                "Use this to check for errors before importing.",
                title="Import Command",
                border_style="yellow"
            ))
        else:
            console.print(Panel(
                "[yellow]IMPORT MODE[/yellow]\n\n"
                "This will create work logs in Jira based on your Excel file.\n"
                "Make sure you've reviewed the data in the Excel file.",
                title="Import Command",
                border_style="cyan"
            ))
            if not click.confirm("\nDo you want to continue?", default=False):
                console.print("[yellow]Import cancelled by user.[/yellow]")
                raise click.Abort()
        
        # Import work logs from Excel
        worklog_entries = excel_service.import_worklogs_from_excel(input_file)
        
        if not worklog_entries:
            console.print("[yellow]No valid work log entries found in Excel file.[/yellow]")
            console.print("[dim]Make sure you've filled in Issue Key, Time Logged (hours), and Date columns.[/dim]")
            raise click.Abort()
        
        if verbose:
            console.print(f"\n[cyan]Found {len(worklog_entries)} work log entry(ies) to process:[/cyan]\n")
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Issue Key", style="cyan")
            table.add_column("Time (hours)", style="green")
            table.add_column("Date", style="yellow")
            table.add_column("Comment", style="dim")
            
            for entry in worklog_entries[:10]:  # Show first 10
                comment = entry.comment[:30] + "..." if entry.comment and len(entry.comment) > 30 else (entry.comment or "")
                table.add_row(
                    entry.issue_key,
                    str(entry.time_logged_hours),
                    str(entry.work_date),
                    comment
                )
            
            if len(worklog_entries) > 10:
                table.add_row("...", "...", "...", f"({len(worklog_entries) - 10} more entries)")
            
            console.print(table)
            console.print()
        
        # Add work logs to Jira
        results = jira_service.add_worklogs_batch(worklog_entries, dry_run=dry_run)
        
        # Display results
        success_count = sum(1 for r in results if r.success)
        failure_count = len(results) - success_count
        
        # Create results table
        results_table = Table(title="Import Results", show_header=True, header_style="bold cyan")
        results_table.add_column("Issue Key", style="cyan")
        results_table.add_column("Status", style="green")
        results_table.add_column("Message", style="yellow", overflow="fold")
        
        for result in results:
            if result.success:
                results_table.add_row(
                    result.issue_key,
                    "[green]✓ Success[/green]",
                    result.message
                )
            else:
                results_table.add_row(
                    result.issue_key,
                    "[red]✗ Failed[/red]",
                    result.message
                )
        
        console.print(results_table)
        console.print()
        
        # Summary
        summary_panel = Panel(
            f"[green]Success:[/green] {success_count}\n"
            f"[red]Failed:[/red] {failure_count}\n"
            f"[cyan]Total:[/cyan] {len(results)}",
            title="Summary",
            border_style="green" if failure_count == 0 else "yellow"
        )
        console.print(summary_panel)
        
        # Update Excel file with status
        if not dry_run and success_count > 0:
            excel_service.update_excel_status(input_file, results)
        
        if failure_count > 0:
            console.print("\n[yellow]Some work logs failed to import. Please check the error messages above.[/yellow]")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Import cancelled by user.[/yellow]")
        raise click.Abort()
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {str(e)}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        raise click.Abort()

