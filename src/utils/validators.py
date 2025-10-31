"""Input validation utilities."""

from typing import Optional
from datetime import datetime


def validate_date(date_str: str) -> bool:
    """Validate date string in YYYY-MM-DD format.
    
    Args:
        date_str: Date string to validate
        
    Returns:
        True if valid, False otherwise
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def validate_time_hours(time_str: str) -> bool:
    """Validate time string as decimal hours.
    
    Args:
        time_str: Time string to validate
        
    Returns:
        True if valid, False otherwise
    """
    try:
        hours = float(time_str)
        return 0 < hours <= 24
    except (ValueError, TypeError):
        return False


def validate_issue_key(issue_key: str) -> bool:
    """Validate Jira issue key format.
    
    Args:
        issue_key: Issue key to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not issue_key or not isinstance(issue_key, str):
        return False
    
    if '-' not in issue_key:
        return False
    
    parts = issue_key.split('-')
    if len(parts) != 2:
        return False
    
    return bool(parts[0] and parts[1])

