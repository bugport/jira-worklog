# Architecture Documentation

## System Overview

The Jira Work Log Tool is a Python CLI application that provides Excel-based work log management for Jira issues. It follows a layered architecture with clear separation of concerns.

## High-Level Architecture

```
┌─────────────────────────────────────────┐
│           CLI Interface (Click)          │
│         src/main.py + commands/           │
└─────────────────┬───────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
┌───────▼─────────┐  ┌───────▼─────────┐
│  Jira Service   │  │  Excel Service  │
│  jira_service   │  │  excel_service  │
└───────┬─────────┘  └───────┬─────────┘
        │                     │
┌───────▼─────────────────────▼─────────┐
│      Filter Service                     │
│      filter_service                     │
└───────┬─────────────────────────────────┘
        │
┌───────▼─────────┐
│  Config & Auth  │
│  settings + auth │
└─────────────────┘
```

## Component Layers

### 1. CLI Layer (`src/main.py`, `src/commands/`)

**Responsibilities:**
- Command-line interface using Click framework
- User interaction and input validation
- Rich formatted output
- Help messages and examples

**Key Components:**
- `main.py`: Main entry point, command group registration
- `export.py`: Export command implementation
- `import.py`: Import command implementation
- `sync.py`: Sync workflow command

### 2. Service Layer (`src/services/`)

**Responsibilities:**
- Business logic implementation
- API integration
- Data transformation
- Error handling

**Key Components:**
- `jira_service.py`: Jira API integration (get issues, add work logs)
- `filter_service.py`: Jira filter management and JQL execution
- `excel_service.py`: Excel file read/write operations

### 3. Model Layer (`src/models/`)

**Responsibilities:**
- Data structure definitions
- Data validation using Pydantic
- Type safety

**Key Components:**
- `issue.py`: Issue data models
- `worklog.py`: Work log data models

### 4. Configuration Layer (`src/config/`)

**Responsibilities:**
- Settings management
- Authentication handling
- Environment variable loading

**Key Components:**
- `settings.py`: Application settings using Pydantic Settings
- `auth.py`: Jira authentication logic

## Data Flow

### Export Workflow

```
1. User Command → CLI (export)
2. CLI → Filter Service (get issues from filter/JQL)
3. Filter Service → Jira Service (fetch issues)
4. Jira Service → Jira API
5. Jira API → Issues Data
6. Jira Service → Excel Service (create template)
7. Excel Service → Excel File (export)
```

### Import Workflow

```
1. User Command → CLI (import)
2. CLI → Excel Service (read Excel)
3. Excel Service → Validate Data
4. Excel Service → Work Log Models
5. CLI → Jira Service (add work logs)
6. Jira Service → Jira API
7. Jira API → Work Log Created
8. Jira Service → Sync Report
```

## Technology Stack

### Core Libraries
- **Click**: CLI framework
- **Rich**: Enhanced terminal output
- **Jira**: Jira API client
- **Pandas**: Excel operations
- **OpenPyXL**: Excel file format
- **Pydantic**: Data validation
- **python-dotenv**: Environment variables

### Python Version
- Python 3.11+

## Security

### Authentication
- Personal Access Token (PAT) authentication
- Credentials stored in `.env` file (not committed)
- Token passed via HTTP Basic Auth

### Error Handling
- Comprehensive error messages
- Validation before API calls
- Dry-run mode for testing

## Deployment

### Docker
- Containerized application
- Volume mounts for file access
- Environment variable injection

### Virtual Environment
- Child venv with Python 3.11
- Extend mode for shared packages
- Isolated dependencies

## Testing Strategy

### Unit Tests
- Service layer tests
- Model validation tests
- Utility function tests

### Integration Tests
- Jira API integration (mocked)
- Excel operations tests
- End-to-end workflow tests

## Future Enhancements

- Interactive mode for step-by-step guidance
- Multiple work log entries per issue
- Work log history tracking
- Batch processing optimizations
- Configuration file support

