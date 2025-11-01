"""Main CLI entry point for Jira Work Log Tool."""

import click
from rich.console import Console
from rich.panel import Panel

from .commands.export import export
from .commands.import_cmd import import_cmd
from .commands.sync import sync
from .commands.worklog_summary import worklog_summary
from .config.auth import JiraAuth
from .services.filter_service import FilterService

console = Console()


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(version="0.1.0", prog_name="jira-worklog")
def cli(ctx: click.Context):
    """Jira Work Log Tool - Manage Jira work logs with Excel integration.
    
    Export issues from Jira filters to Excel, log time, and sync back to Jira.
    
    Examples:
    
    \b
    Test connection:
    $ python -m src.main test
    
    \b
    List available filters:
    $ python -m src.main filters
    
    \b
    Export issues to Excel:
    $ python -m src.main export --filter 12345 --output worklog.xlsx
    
    \b
    Import work logs from Excel:
    $ python -m src.main import --input worklog.xlsx
    
    \b
    Complete sync workflow:
    $ python -m src.main sync --filter 12345 --output worklog.xlsx
    $ # Edit Excel file
    $ python -m src.main sync --input worklog.xlsx
    """
    if ctx.invoked_subcommand is None:
        # Show help if no command provided
        console.print(Panel(
            "[bold cyan]Jira Work Log Tool[/bold cyan]\n\n"
            "Manage Jira work logs with Excel integration.\n\n"
            "[yellow]Available Commands:[/yellow]\n"
            "  test             - Test connection to Jira server\n"
            "  check-spec       - Check REST API specification compatibility\n"
            "  filters          - List available Jira filters\n"
            "  export           - Export issues to Excel template\n"
            "  import           - Import work logs from Excel to Jira\n"
            "  sync             - Complete sync workflow (export → edit → import)\n"
            "  worklog-summary  - Export existing worklogs and update them via diff\n\n"
            "[dim]Use --help with any command for detailed help.[/dim]\n"
            "[dim]Example: python -m src.main export --help[/dim]",
            title="Welcome",
            border_style="cyan"
        ))
        console.print(ctx.get_help())


@cli.command()
def test():
    """Test connection to Jira server with current credentials.
    
    Tests the connection to Jira using credentials from .env file.
    Useful for verifying your configuration before running other commands.
    
    Examples:
    
    \b
    Test connection:
    $ python -m src.main test
    """
    try:
        auth = JiraAuth()
        success = auth.test_connection()
        
        if success:
            click.echo("\n[green]✓[/green] Connection test successful!")
        else:
            click.echo("\n[red]✗[/red] Connection test failed!")
            raise click.Abort()
            
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        console.print("[yellow]Please check your .env file configuration.[/yellow]")
        raise click.Abort()


@cli.command()
def check_spec():
    """Check REST API specification compatibility.
    
    Checks if the configured API version and path are compatible with the JIRA server.
    Displays server information and API compatibility status.
    
    Examples:
    
    \b
    Check REST spec compatibility:
    $ python -m src.main check-spec
    """
    try:
        from rich.table import Table
        
        auth = JiraAuth()
        compat_info = auth.check_rest_spec_compatibility()
        
        # Create compatibility table
        table = Table(title="REST API Specification Compatibility", show_header=True, header_style="bold cyan")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="yellow")
        
        table.add_row("Base URL", compat_info.get('base_url', 'N/A'))
        
        api_path = compat_info.get('api_path', 'Auto-detected')
        if api_path:
            table.add_row("API Path", f"/rest{api_path}")
        else:
            table.add_row("API Path", "Auto-detected")
        
        if compat_info.get('api_version'):
            table.add_row("API Version", compat_info.get('api_version'))
        else:
            table.add_row("API Version", "Not specified")
        
        server_version = compat_info.get('server_version', 'N/A')
        table.add_row("JIRA Server Version", server_version)
        
        compatible = compat_info.get('compatible', False)
        status = "[green]✓ Compatible[/green]" if compatible else "[red]✗ Not Compatible[/red]"
        table.add_row("Status", status)
        
        console.print(table)
        console.print()
        
        if compat_info.get('error'):
            console.print(Panel(
                f"[red]Error:[/red] {compat_info.get('error')}\n\n"
                f"This may indicate:\n"
                f"• API version mismatch\n"
                f"• API path is incorrect\n"
                f"• Server doesn't support the specified API version\n"
                f"• Network connectivity issues\n\n"
                f"Try adjusting:\n"
                f"• JIRA_API_VERSION in .env file\n"
                f"• JIRA_API_PATH in .env file",
                title="Compatibility Check Failed",
                border_style="red"
            ))
        elif compatible:
            console.print(Panel(
                f"[green]✓[/green] REST API specification is compatible!\n\n"
                f"Server Version: {server_version}\n"
                f"API Path: /rest{api_path or '(auto-detected)'}\n"
                f"Base URL: {compat_info.get('base_url')}",
                title="Compatibility Check Success",
                border_style="green"
            ))
        else:
            console.print(Panel(
                f"[yellow]⚠[/yellow] Compatibility status unknown.\n\n"
                f"Unable to verify API compatibility.\n"
                f"Please check your configuration.",
                title="Compatibility Check Warning",
                border_style="yellow"
            ))
            
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        console.print("[yellow]Please check your Jira connection and configuration.[/yellow]")
        raise click.Abort()


@cli.command()
def filters():
    """List all available Jira filters.
    
    Displays all saved Jira filters with their IDs and JQL queries.
    Use filter IDs with the export command to get issues from specific filters.
    
    Examples:
    
    \b
    List all filters:
    $ python -m src.main filters
    """
    try:
        auth = JiraAuth()
        filter_service = FilterService(auth)
        filter_service.display_filters()
        
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        console.print("[yellow]Please check your Jira connection and permissions.[/yellow]")
        raise click.Abort()


# Register commands
cli.add_command(export)
cli.add_command(import_cmd)
cli.add_command(sync)
cli.add_command(worklog_summary, name='worklog-summary')


if __name__ == '__main__':
    cli()

