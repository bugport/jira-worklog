"""Worklog summary command for exporting existing worklogs and importing updates."""

from typing import Optional
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..services.jira_service import JiraService
from ..services.excel_service import ExcelService
from ..services.hierarchy_service import HierarchyService, HierarchicalGroup
from ..services.filter_service import FilterService
from ..config.auth import JiraAuth
from decimal import Decimal

console = Console()


@click.command()
@click.option(
    '--filter',
    'filter_ids',
    type=str,
    help='Jira filter ID(s) to export worklogs from (comma-separated: --filter 12345,67890 or multiple: --filter 12345 --filter 67890)'
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
@click.option(
    '--time-range',
    type=click.Choice(['previous', 'current'], case_sensitive=False),
    default=None,
    help='Filter worklogs by time range: previous (previous month) or current (current month). Default: all time'
)
@click.option(
    '--all-users',
    is_flag=True,
    default=False,
    help='Include worklogs from all users (default: only current user)'
)
@click.option(
    '--issues-only',
    is_flag=True,
    default=False,
    help='Only include issues with worklogs (default: include all issues even with no worklogs)'
)
@click.option(
    '--group-by-hierarchy',
    is_flag=True,
    default=False,
    help='Group issues by hierarchy: Epic > Story/Task > Subtask (default: flat list)'
)
def worklog_summary(filter_ids: str, jql: str, output: str, input_file: str, dry_run: bool, verbose: bool, time_range: Optional[str], all_users: bool, issues_only: bool, group_by_hierarchy: bool):
    """Export existing worklogs from filter to Excel, then import updates back.
    
    This command supports two modes:
    1. Export mode: Export existing worklogs from filter(s) to Excel with original values
       - By default includes ALL issues from filter (even with no worklogs, showing 0 time)
       - By default filters worklogs by current user only
       - Supports time range filtering (previous or current month)
       - Supports multiple filters (combines with OR)
       - Supports hierarchical grouping: Epic > Story/Task > Subtask
       - Shows sum of all worklogs in export summary
    2. Import mode: Import edited Excel file and update worklogs based on detected changes (diff)
    
    Examples:
    
    \b
    Export all issues from single filter (including those with no worklogs):
    $ python -m src.main worklog-summary --filter 12345 --output worklog_summary.xlsx
    
    \b
    Export from multiple filters with hierarchical grouping (comma-separated):
    $ python -m src.main worklog-summary --filter 12345,67890 --group-by-hierarchy --output worklog_summary.xlsx
    
    \b
    Export from JQL query for current month, current user only:
    $ python -m src.main worklog-summary --jql "project = PROJ" --time-range current --output worklog_summary.xlsx
    
    \b
    Export previous month worklogs, all users, grouped by hierarchy (multiple filters):
    $ python -m src.main worklog-summary --filter 12345,67890 --time-range previous --all-users --group-by-hierarchy --output worklog_summary.xlsx
    
    \b
    Export only issues that have worklogs (exclude issues with 0 time):
    $ python -m src.main worklog-summary --filter 12345 --issues-only --output worklog_summary.xlsx
    
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
            
            # Get worklogs from filter(s)/JQL with filtering options
            if filter_ids:
                # Parse comma-separated filter IDs
                filter_id_list = [fid.strip() for fid in filter_ids.split(',') if fid.strip()]
                
                if not filter_id_list:
                    console.print("[red]No valid filter IDs provided.[/red]")
                    raise click.Abort()
                
                if verbose:
                    if len(filter_id_list) == 1:
                        console.print(f"[cyan]Fetching worklogs from filter:[/cyan] {filter_id_list[0]}")
                    else:
                        console.print(f"[cyan]Fetching worklogs from {len(filter_id_list)} filters:[/cyan] {', '.join(filter_id_list)}")
                
                # Combine multiple filters
                filter_service = FilterService(jira_service.auth)
                combined_jql = filter_service.combine_filters_jql(filter_id_list)
                
                if not combined_jql:
                    console.print("[red]Failed to combine filters.[/red]")
                    raise click.Abort()
                
                if verbose and len(filter_id_list) > 1:
                    console.print(f"[dim]Combined JQL: {combined_jql[:100]}...[/dim]" if len(combined_jql) > 100 else f"[dim]Combined JQL: {combined_jql}[/dim]")
                
                worklogs = jira_service.get_worklogs_from_jql(
                    combined_jql,
                    include_all_issues=not issues_only,
                    filter_by_current_user=not all_users,
                    time_range=time_range.lower() if time_range else None
                )
            else:
                if verbose:
                    console.print(f"[cyan]Fetching worklogs from JQL:[/cyan] {jql}")
                worklogs = jira_service.get_worklogs_from_jql(
                    jql,
                    include_all_issues=not issues_only,
                    filter_by_current_user=not all_users,
                    time_range=time_range.lower() if time_range else None
                )
            
            if not worklogs and issues_only:
                console.print("[yellow]No worklogs found to export.[/yellow]")
                if filter_ids:
                    filter_id_list = [fid.strip() for fid in filter_ids.split(',') if fid.strip()]
                    console.print(f"[dim]Check if filter(s) {', '.join(filter_id_list)} exist and contain issues with worklogs.[/dim]")
                else:
                    console.print("[dim]Check your JQL query and ensure issues have worklogs.[/dim]")
                raise click.Abort()
            
            # Get issues from the same source for hierarchy grouping
            if filter_ids:
                # Parse comma-separated filter IDs
                filter_id_list = [fid.strip() for fid in filter_ids.split(',') if fid.strip()]
                filter_service = FilterService(jira_service.auth)
                combined_jql = filter_service.combine_filters_jql(filter_id_list)
                if combined_jql:
                    all_issues = jira_service.get_issues_from_jql(combined_jql)
                else:
                    all_issues = []
            else:
                all_issues = jira_service.get_issues_from_jql(jql) if jql else []
            
            # Get issues info for worklogs (if not already fetched)
            issue_keys = list(set([wl.issue_key for wl in worklogs]))
            issues_dict = {}
            
            # Build issues_dict from fetched issues if available
            # Use issue key as fallback title if summary is empty
            for issue in all_issues:
                summary = issue.summary or issue.key  # Use issue key as title if summary is empty
                issues_dict[issue.key] = (summary, issue.issue_type)
            
            # Fetch any missing issues
            for issue_key in issue_keys:
                if issue_key not in issues_dict:
                    try:
                        issue_data = jira_service.get_issue_details(issue_key)
                        if issue_data:
                            fields = issue_data.get('fields', {})
                            issue_type = fields.get('issuetype', {}).get('name', 'Unknown')
                            summary = fields.get('summary', '') or issue_key  # Use issue key as title if summary is empty
                            issues_dict[issue_key] = (summary, issue_type)
                        else:
                            issues_dict[issue_key] = (issue_key, "")  # Use issue key as fallback
                    except Exception:
                        issues_dict[issue_key] = (issue_key, "")  # Use issue key as fallback
            
            # Group by hierarchy if requested
            if group_by_hierarchy and all_issues:
                hierarchical_groups = HierarchyService.group_by_hierarchy(all_issues, worklogs)
                sorted_groups = HierarchyService.get_hierarchical_list(hierarchical_groups)
                
                if verbose:
                    console.print(f"\n[cyan]Grouped {len(all_issues)} issues into {len(hierarchical_groups)} hierarchical group(s)[/cyan]")
                    for epic_key, group in sorted_groups[:5]:  # Show first 5
                        epic_name = (group.epic.summary or group.epic.key) if group.epic else "Orphan Issues"  # Use issue key as fallback
                        console.print(f"  • {epic_name}: {len(group.stories_tasks)} stories/tasks, {sum(len(s) for s in group.subtasks_map.values())} subtasks")
                    if len(sorted_groups) > 5:
                        console.print(f"  ... and {len(sorted_groups) - 5} more group(s)")
            else:
                hierarchical_groups = None
                sorted_groups = None
            
            # Calculate sum of worklogs for current user
            total_hours = Decimal("0")
            issues_with_time = 0
            issues_without_time = 0
            
            for wl in worklogs:
                if wl.time_spent_hours > 0:
                    total_hours += wl.time_spent_hours
                    issues_with_time += 1
                else:
                    issues_without_time += 1
            
            # Export to Excel with optional hierarchy grouping
            success = excel_service.export_worklog_summary(
                worklogs, 
                issues_dict, 
                output,
                hierarchical_groups=sorted_groups if group_by_hierarchy else None,
                all_issues=all_issues if group_by_hierarchy else None
            )
            
            if success:
                summary_info = [
                    f"[green]✓[/green] Worklog summary export completed!\n",
                    f"File: [cyan]{output}[/cyan]",
                    f"Total entries: [green]{len(worklogs)}[/green]",
                    f"  • Issues with worklogs: [cyan]{issues_with_time}[/cyan]",
                    f"  • Issues without worklogs (0 time): [yellow]{issues_without_time}[/yellow]",
                    f"Total time logged: [green]{float(total_hours):.2f} hours[/green]",
                ]
                
                if time_range:
                    summary_info.append(f"Time range: [cyan]{time_range} month[/cyan]")
                if not all_users:
                    summary_info.append(f"User filter: [cyan]Current user only[/cyan]")
                
                summary_info.extend([
                    "",
                    "[yellow]Next steps:[/yellow]",
                    f"1. Open {output} in Excel",
                    f"2. Edit 'Time Logged (hours)' column to change time (original values preserved in gray)",
                    f"3. Edit 'Comment' column to change comments (original values preserved in gray)",
                    f"4. Save the Excel file",
                    f"5. Run: [cyan]python -m src.main worklog-summary --input {output}[/cyan]"
                ])
                
                console.print(Panel(
                    "\n".join(summary_info),
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

