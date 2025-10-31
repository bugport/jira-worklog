#!/bin/bash
# Example usage of Jira Work Log Tool

echo "=== Jira Work Log Tool - Usage Examples ==="
echo ""

echo "1. Test connection to Jira:"
echo "python -m src.main test"
echo ""

echo "2. List available filters:"
echo "python -m src.main filters"
echo ""

echo "3. Export issues from filter to Excel:"
echo "python -m src.main export --filter 12345 --output worklog.xlsx"
echo ""

echo "4. Export issues from JQL query:"
echo "python -m src.main export --jql \"project = PROJ AND status = 'In Progress'\" --output worklog.xlsx"
echo ""

echo "5. Validate Excel file without importing (dry-run):"
echo "python -m src.main import --input worklog.xlsx --dry-run"
echo ""

echo "6. Import work logs from Excel to Jira:"
echo "python -m src.main import --input worklog.xlsx"
echo ""

echo "7. Complete sync workflow:"
echo "# Step 1: Export"
echo "python -m src.main sync --filter 12345 --output worklog.xlsx"
echo ""
echo "# Step 2: Edit worklog.xlsx with your time logs"
echo ""
echo "# Step 3: Import"
echo "python -m src.main sync --input worklog.xlsx"
echo ""

echo "8. Get help for any command:"
echo "python -m src.main export --help"
echo "python -m src.main import --help"

