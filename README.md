# Jira Work Log Tool

Python CLI tool for managing Jira work logs with Excel integration. Export issues to Excel, log time, and sync back to Jira.

## Features

- Export Jira issues to editable Excel templates
- Import work logs from Excel back to Jira
- **Export existing worklogs and update them via diff comparison**
- Support for Jira filters and custom JQL queries
- Token-based authentication (Personal Access Token)
- User-friendly CLI with comprehensive help messages
- Rich formatted output with progress indicators
- Validation and error handling
- Docker support

## Prerequisites

- Python 3.11+
- Jira account with API access
- Jira API token (Personal Access Token)

## Installation

### Quick Setup (Recommended)

```bash
# Run setup script
./setup.sh
```

This will:
- Create virtual environment (if needed)
- Install all dependencies
- Create .env file template
- Set up the CLI entry point

### Using Virtual Environment

```bash
# Create and activate child venv
source /Users/ineutov/Projects/activate-global-venv-3.11.sh
cd /Users/ineutov/Projects/jira-worklog

# Install dependencies
pip install -r requirements.txt
```

### Using Docker

```bash
# Build and run container
docker-compose up -d

# Execute commands
docker-compose exec app python -m src.main export --filter 12345
```

## Configuration

1. Copy environment template:
```bash
cp .env.example .env
```

2. Edit `.env` file with your Jira credentials:
```env
JIRA_SERVER=https://your-domain.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-api-token

# Optional: Bypass SSL verification (for self-signed certificates)
# WARNING: Only use in development/testing environments
JIRA_VERIFY_SSL=false

# Optional: JIRA API version (default: auto-detected)
# Specify the API version to use (e.g., '1.0', '2', '3', 'latest')
# If set, this takes precedence over JIRA_API_PATH
# Example: JIRA_API_VERSION=1.0 (will use /rest/api/1.0)
JIRA_API_VERSION=1.0

# Optional: Custom JIRA API path (default: auto-detected)
# Set if your JIRA API is located at a custom path
# You can specify either '/rest/api/latest' or '/api/latest'
# (The library automatically adds '/rest', so '/rest' prefix will be removed if present)
# If JIRA_API_VERSION is set, this option is ignored
# Example: If your API is at https://baseurl/rest/api/latest:
#   JIRA_SERVER=https://baseurl
#   JIRA_API_PATH=/rest/api/latest
JIRA_API_PATH=/rest/api/latest
```

**Note**: 
- **To use API version 1.0**: Set `JIRA_API_VERSION=1.0` (this will use `/rest/api/1.0`)
- **If your JIRA API is located at `https://baseurl/rest/api/latest`**: 
  - Set `JIRA_SERVER=https://baseurl` (base URL without the API path)
  - Set `JIRA_API_PATH=/rest/api/latest` or `/api/latest` (the library will handle the conversion)
  
The JIRA library automatically adds `/rest` prefix, so if you specify `/rest/api/latest`, it will be converted to `/api/latest` to avoid the duplicate `/rest//rest` issue.

**Priority**: If `JIRA_API_VERSION` is set, it takes precedence over `JIRA_API_PATH`.

### Getting Your API Token

1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Copy the token to your `.env` file

## Usage

After running `./setup.sh`, you can use the CLI tool directly:

```bash
# Get help
jira-worklog --help

# Test connection
jira-worklog test

# Check REST API specification compatibility
jira-worklog check-spec

# List available filters
jira-worklog filters
```

Or use the Python module approach:

```bash
python -m src.main test
python -m src.main check-spec
python -m src.main filters
```

### Test Connection

```bash
jira-worklog test
```

### List Available Filters

```bash
jira-worklog filters
```

### Export Issues to Excel

From a filter:
```bash
jira-worklog export --filter 12345 --output worklog.xlsx
```

From JQL query:
```bash
jira-worklog export --jql "project = PROJ AND status = 'In Progress'" --output worklog.xlsx
```

### Import Work Logs from Excel

Dry run (validate only):
```bash
jira-worklog import --input worklog.xlsx --dry-run
```

Actual import:
```bash
jira-worklog import --input worklog.xlsx
```

### Complete Sync Workflow

Export, edit Excel, then import:
```bash
# Step 1: Export to Excel
jira-worklog export --filter 12345 --output worklog.xlsx

# Step 2: Edit worklog.xlsx with your time logs

# Step 3: Import back to Jira
jira-worklog import --input worklog.xlsx
```

Or use sync command:
```bash
jira-worklog sync --filter 12345 --output worklog.xlsx
# Edit Excel file manually
jira-worklog sync --input worklog.xlsx
```

## Excel Template Format

The exported Excel file contains these columns:

- **Issue Key** (required): Jira issue key (e.g., PROJ-123)
- **Summary** (read-only): Issue summary
- **Type** (read-only): Task/Story/Epic
- **Time Logged (hours)** (required): Decimal hours (e.g., 2.5)
- **Date** (required): Date in YYYY-MM-DD format
- **Comment** (optional): Work log comment
- **Status** (auto): Sync status after import

### Example Excel Entry

| Issue Key | Summary | Type | Time Logged | Date | Comment | Status |
|-----------|---------|------|-------------|------|----------|--------|
| PROJ-123 | Fix login bug | Task | 2.5 | 2024-01-15 | Fixed authentication | Pending |

## Commands

### `test`
Test connection to Jira server.

```bash
python -m src.main test
```

### `check-spec`
Check REST API specification compatibility with your JIRA server.

Verifies that the configured API version and path are compatible with the server.
Displays server information, API path, version, and compatibility status.

```bash
python -m src.main check-spec
```

This command will:
- Test the connection with the configured API version/path
- Display server version information
- Show the API path being used
- Indicate compatibility status
- Provide troubleshooting suggestions if compatibility issues are detected

**Use this command** to verify your `JIRA_API_VERSION` or `JIRA_API_PATH` configuration is correct.

### `filters`
List all available Jira filters.

```bash
python -m src.main filters
```

### `export`
Export issues from filter or JQL to Excel template.

Options:
- `--filter <id>`: Jira filter ID
- `--jql <query>`: JQL query string
- `--output <file>`: Output Excel file path (default: worklog.xlsx)
- `--verbose`: Verbose output

```bash
python -m src.main export --filter 12345 --output report.xlsx
python -m src.main export --jql "project = PROJ" --output report.xlsx
```

### `import`
Import work logs from edited Excel file to Jira.

Options:
- `--input <file>`: Input Excel file path
- `--dry-run`: Validate only, don't actually import
- `--verbose`: Verbose output

```bash
python -m src.main import --input worklog.xlsx --dry-run
python -m src.main import --input worklog.xlsx
```

### `sync`
Complete sync workflow (export → edit → import).

Options:
- `--filter <id>`: Jira filter ID (for export)
- `--jql <query>`: JQL query (for export)
- `--output <file>`: Output Excel file (for export)
- `--input <file>`: Input Excel file (for import)
- `--auto-import`: Automatically import after export (optional)

```bash
python -m src.main sync --filter 12345 --output worklog.xlsx
# Edit Excel file
python -m src.main sync --input worklog.xlsx
```

### `worklog-summary`
Export existing worklogs from filter and update them via diff comparison.

This command supports two modes:

**Export Mode:** Export existing worklogs from a filter to Excel with original values tracked.

**Update Mode:** Import edited Excel file and update worklogs in Jira based on detected changes (diff).

Options:
- `--filter <id>`: Jira filter ID (for export)
- `--jql <query>`: JQL query (for export)
- `--output <file>`: Output Excel file (for export, default: worklog_summary.xlsx)
- `--input <file>`: Input Excel file (for import/update)
- `--dry-run`: Validate only, don't actually update worklogs
- `--verbose`: Verbose output

```bash
# Export existing worklogs from filter
jira-worklog worklog-summary --filter 12345 --output worklog_summary.xlsx

# Edit worklog_summary.xlsx:
# - Change "Time Logged (hours)" column (original preserved in gray)
# - Change "Comment" column (original preserved in gray)

# Validate changes (dry-run)
jira-worklog worklog-summary --input worklog_summary.xlsx --dry-run

# Actually update worklogs in Jira
jira-worklog worklog-summary --input worklog_summary.xlsx
```

#### Worklog Summary Use Case

This feature allows you to:

1. **Export existing worklogs** from a Jira filter to Excel
   - Fetches all worklogs from issues matching the filter
   - Includes original values in gray (read-only) columns
   - Editable columns: Time Logged (hours) and Comment

2. **Edit worklogs in Excel**
   - Modify time logged (e.g., correct a time entry)
   - Update comments (e.g., add details or fix typos)
   - Original values remain visible for reference

3. **Import and update based on diff**
   - Tool automatically detects what changed
   - Only updates worklogs with actual changes
   - Dry-run mode available to preview updates

**Example Workflow:**

```bash
# Step 1: Export existing worklogs from your current tasks filter
jira-worklog worklog-summary --filter 12345 --output worklog_summary.xlsx

# Step 2: Open worklog_summary.xlsx in Excel
# - You'll see all existing worklogs with original values in gray
# - Edit "Time Logged (hours)" to correct time entries
# - Edit "Comment" to update descriptions
# - Save the file

# Step 3: Validate changes before updating (optional but recommended)
jira-worklog worklog-summary --input worklog_summary.xlsx --dry-run

# Step 4: Actually update worklogs in Jira
jira-worklog worklog-summary --input worklog_summary.xlsx
```

**Excel Format for Worklog Summary:**

| Column | Description | Editable |
|--------|-------------|----------|
| Worklog ID | Jira worklog ID (read-only) | No |
| Issue Key | Jira issue key (read-only) | No |
| Summary | Issue summary (read-only) | No |
| Type | Issue type (read-only) | No |
| Time Logged (hours) | Current time logged - **EDIT THIS** | Yes |
| Original Time (hours) | Original time (gray, read-only) | No |
| Date | Work log date | Yes |
| Comment | Current comment - **EDIT THIS** | Yes |
| Original Comment | Original comment (gray, read-only) | No |
| Author | Work log author (read-only) | No |
| Status | Sync status (auto-populated) | No |

**Benefits:**
- Correct time entries that were logged incorrectly
- Update comments with additional details
- Bulk update multiple worklogs efficiently
- Safe: original values preserved for reference
- Dry-run mode for testing before actual updates

## Help

Get help for any command:

```bash
jira-worklog --help
jira-worklog export --help
jira-worklog import --help
jira-worklog worklog-summary --help
```

Or using Python module:

```bash
python -m src.main --help
python -m src.main export --help
python -m src.main import --help
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `JIRA_SERVER` | Jira server URL | Yes |
| `JIRA_EMAIL` | Your email/username | Yes |
| `JIRA_API_TOKEN` | API token | Yes |
| `JIRA_PROJECT` | Default project key (optional) | No |

## Troubleshooting

### Authentication Errors

```bash
# Test connection
python -m src.main test

# Verify server URL format
# Correct: https://your-domain.atlassian.net
# Wrong: https://your-domain.atlassian.net/
```

### Issue Not Found

Verify issue key format:
- Correct: PROJ-123, ABC-456
- Wrong: PROJ123, proj-456

### Excel Validation Errors

Use `--dry-run` to validate before importing:
```bash
python -m src.main import --input worklog.xlsx --dry-run
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit pull request

## License

MIT

## Contact

Created for efficient Jira work time logging workflows.

