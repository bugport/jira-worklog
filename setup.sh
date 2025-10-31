#!/bin/bash

# Setup script for Jira Work Log Tool
# This script sets up the virtual environment and installs dependencies

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_VERSION="/opt/homebrew/bin/python3.11"

echo "Setting up Jira Work Log Tool..."
echo "Project directory: $PROJECT_DIR"
echo ""

# Check if Python 3.11 is available
if [ ! -f "$PYTHON_VERSION" ]; then
    echo "Error: Python 3.11 not found at $PYTHON_VERSION"
    echo "Please install Python 3.11 or update the PYTHON_VERSION variable in this script"
    exit 1
fi

# Check if child venv creation script exists
if [ -f "$PROJECT_DIR/../create-child-venv-multi-python.sh" ]; then
    echo "Creating child virtual environment..."
    cd "$PROJECT_DIR/.."
    ./create-child-venv-multi-python.sh jira-worklog 3.11 --extend
    cd "$PROJECT_DIR"
else
    echo "Warning: Child venv script not found. Using standard venv..."
    VENV_DIR="$PROJECT_DIR/.venv"
    if [ ! -d "$VENV_DIR" ]; then
        echo "Creating virtual environment..."
        "$PYTHON_VERSION" -m venv "$VENV_DIR"
    else
        echo "Virtual environment already exists"
    fi
    
    # Activate virtual environment
    echo "Activating virtual environment..."
    source "$VENV_DIR/bin/activate"
fi

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Install package in development mode for CLI entry point
if [ -f "setup.py" ]; then
    echo "Installing package for CLI entry point..."
    pip install -e .
fi

# Create .env file if it doesn't exist
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "Created .env file. Please edit it with your Jira credentials."
else
    echo ".env file already exists"
fi

echo ""
echo "✓ Setup complete!"
echo ""
echo "To use the CLI tool:"
echo "  jira-worklog --help"
echo ""
echo "Or run commands directly:"
echo "  jira-worklog test"
echo "  jira-worklog filters"
echo "  jira-worklog export --filter <id>"
echo ""
echo "Don't forget to edit .env file with your Jira credentials!"
echo "  - JIRA_SERVER: Your Jira server URL"
echo "  - JIRA_EMAIL: Your email/username"
echo "  - JIRA_API_TOKEN: Your API token (get from https://id.atlassian.com/manage-profile/security/api-tokens)"

