"""Worklog summary command for exporting existing worklogs and importing updates."""

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
    '--filter',
    type=str,
    help='Jira filter ID to export worklogs from'
)
@click.option(
    '--jql',
    type=str,
    help='JQL query to export worklogs from'
)
@click.option(
    '--output',
    type=str,
    default='worklog_summary.xlsx',
    help='Output Excel file path (default: worklog_summary.xlsx)'
)
@click.option(
    '--input',
    'input_file',
    type=str,
    help='Input Excel file path (for import/update mode)'
)
@click.option(
    '--dry-run',
    is_flag=True,
    help='Validate only, do not actually update worklogs (for import mode)'
)
@click.option(
    '--verbose',
    is_flag=True,
    help='Show verbose output'
)
def worklog_summary(filter: str, jql: str, output: str, input_file: str, dry_run: bool, verbose: bool):
    """Export existing worklogs from filter to Excel, then import updates back.
    
    This command supports two modes:
    1. Export mode: Export existing worklogs from a filter to Excel with original values
    2. Import mode: Import edited Excel file and update worklogs based on detected changes (diff)
    
    Examples:
    
    \b
    Export existing worklogs from filter:
    $ python -m src.main worklog-summary --filter 12345 --output worklog_summary.xlsx
    
    \b
    Export from JQL query:
    $ python -m src.main worklog-summary --jql "project = PROJ" --output worklog_summary.xlsx
    
    \b
    Import and update worklogs (dry-run first):
    $ python -m src.main worklog-summary --input worklog_summary.xlsx --dry-run
    
    \b
    Import and update worklogs (actual update):
    $ python -m src.main worklog-summary --input worklog_summary.xlsx
    """
    try:
        # Initialize services
        auth = JiraAuth()
        jira_service = JiraService(auth)
        excel_service = ExcelService()
        
        if input_file:
            # Import/Update mode
            console.print(Panel(
                "[cyan]WORKLOG SUMMARY: Update Mode[/cyan]\n\n"
                "Importing edited worklog summary and updating worklogs in Jira based on detected changes.",
                title="Worklog Summary Command",
                border_style="cyan"
            ))
            
            if not dry_run:
                if not click.confirm("\nThis will update existing worklogs in Jira. Continue?", default=False):
                    console.print("[yellow]Update cancelled by user.[/yellow]")
                    raise click.Abort()
            
            # Import and detect changes
            worklog_updates = excel_service.import_worklog_summary_diff(input_file)
            
            if not worklog_updates:
                console.print("[yellow]No changes detected in worklog summary.[/yellow]")
                console.print("[dim]If you edited the Excel file, make sure you modified 'Time Logged (hours)' or 'Comment' columns.[/dim]")
                raise click.Abort()
            
            if verbose:
                console.print(f"\n[cyan]Detected {len(worklog_updates)} change(s):[/cyan]\n")
                table = Table(show_header=True, header_style="bold cyan")
                table.add_column("Worklog ID", style="cyan")
                table.add_column("Issue Key", style="green")
                table.add_column("Time Change", style="yellow")
                table.add_column("Comment Changed", style="dim")
                
                for update in worklog_updates[:20]:  # Show first 20
                    time_change = f"{update.original_time_hours}h → {update.new_time_hours}h"
                    comment_changed = "Yes" if (update.new_comment or "") != (update.original_comment or "") else "No"
                    table.add_row(
                        update.worklog_id[:10] + "...",
                        update.issue_key,
                        time_change,
                        comment_changed
                    )
                
                if len(worklog_updates) > 20:
                    table.add_row("...", "...", f"({len(worklog_updates) - 20} more changes)", "...")
                
                console.print(table)
                console.print()
            
            # Update worklogs in Jira
            results = jira_service.update_worklogs_from_diff(worklog_updates, dry_run=dry_run)
            
            # Display results
            success_count = sum(1 for r in results if r.success)
            failure_count = len(results) - success_count
            
            # Create results table
            results_table = Table(title="Update Results", show_header=True, header_style="bold cyan")
            results_table.add_column("Worklog ID", style="cyan")
            results_table.add_column("Issue Key", style="green")
            results_table.add_column("Status", style="green")
            results_table.add_column("Message", style="yellow", overflow="fold")
            
            for result in results:
                if result.success:
                    results_table.add_row(
                        result.worklog_id[:10] + "..." if result.worklog_id else "N/A",
                        result.issue_key,
                        "[green]✓ Success[/green]",
                        result.message
                    )
                else:
                    results_table.add_row(
                        result.worklog_id[:10] + "..." if result.worklog_id else "N/A",
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
            
            if failure_count > 0:
                console.print("\n[yellow]Some worklogs failed to update. Please check the error messages above.[/yellow]")
            
        elif filter or jql:
            # Export mode
            console.print(Panel(
                "[cyan]WORKLOG SUMMARY: Export Mode[/cyan]\n\n"
                "Exporting existing worklogs from filter to Excel template for editing.",
                title="Worklog Summary Command",
                border_style="cyan"
            ))
            
            # Get worklogs from filter/JQL
            if filter:
                if verbose:
                    console.print(f"[cyan]Fetching worklogs from filter:[/cyan] {filter}")
                worklogs = jira_service.get_worklogs_from_filter(filter)
            else:
                if verbose:
                    console.print(f"[cyan]Fetching worklogs from JQL:[/cyan] {jql}")
                worklogs = jira_service.get_worklogs_from_jql(jql)
            
            if not worklogs:
                console.print("[yellow]No worklogs found to export.[/yellow]")
                if filter:
                    console.print(f"[dim]Check if filter {filter} exists and contains issues with worklogs.[/dim]")
                else:
                    console.print("[dim]Check your JQL query and ensure issues have worklogs.[/dim]")
                raise click.Abort()
            
            # Get issues info for worklogs
            issue_keys = list(set([wl.issue_key for wl in worklogs]))
            issues_dict = {}
            
            for issue_key in issue_keys:
                try:
                    issue = jira_service.client.issue(issue_key)
                    issue_type = issue.fields.issuetype.name if hasattr(issue.fields, 'issuetype') else "Unknown"
                    summary = issue.fields.summary if hasattr(issue.fields, 'summary') else ""
                    issues_dict[issue_key] = (summary, issue_type)
                except Exception:
                    issues_dict[issue_key] = ("", "")
            
            # Export to Excel
            success = excel_service.export_worklog_summary(worklogs, issues_dict, output)
            
            if success:
                console.print(Panel(
                    f"[green]✓[/green] Worklog summary export completed!\n\n"
                    f"File: [cyan]{output}[/cyan]\n"
                    f"Worklogs: [green]{len(worklogs)}[/green]\n\n"
                    f"[yellow]Next steps:[/yellow]\n"
                    f"1. Open {output} in Excel\n"
                    f"2. Edit 'Time Logged (hours)' column to change time (original values preserved in gray)\n"
                    f"3. Edit 'Comment' column to change comments (original values preserved in gray)\n"
                    f"4. Save the Excel file\n"
                    f"5. Run: [cyan]python -m src.main worklog-summary --input {output}[/cyan]",
                    title="Export Success",
                    border_style="green"
                ))
            else:
                console.print("[red]Export failed. Please check the error messages above.[/red]")
                raise click.Abort()
            
        else:
            console.print(Panel(
                "[red]Error:[/red] Either --filter/--jql (for export) or --input (for import/update) is required.\n\n"
                "[yellow]Examples:[/yellow]\n"
                "  worklog-summary --filter 12345 --output worklog_summary.xlsx\n"
                "  worklog-summary --input worklog_summary.xlsx",
                title="Worklog Summary Command",
                border_style="red"
            ))
            raise click.Abort()
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Command cancelled by user.[/yellow]")
        raise click.Abort()
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {str(e)}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        raise click.Abort()

