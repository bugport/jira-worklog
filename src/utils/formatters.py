"""Data formatting utilities."""

from datetime import datetime, date
from typing import Optional
from decimal import Decimal


def format_date(d: Optional[date]) -> str:
    """Format date to YYYY-MM-DD string.
    
    Args:
        d: Date to format
        
    Returns:
        Formatted date string or empty string
    """
    if d is None:
        return ""
    return d.strftime("%Y-%m-%d")


def format_datetime(dt: Optional[datetime]) -> str:
    """Format datetime to ISO string.
    
    Args:
        dt: Datetime to format
        
    Returns:
        Formatted datetime string or empty string
    """
    if dt is None:
        return ""
    return dt.isoformat()


def format_time_hours(seconds: int) -> str:
    """Format seconds to decimal hours string.
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted hours string (e.g., "2.5")
    """
    hours = seconds / 3600.0
    return f"{hours:.2f}".rstrip('0').rstrip('.')


def parse_time_hours(time_str: str) -> Decimal:
    """Parse time string to decimal hours.
    
    Args:
        time_str: Time string (e.g., "2.5")
        
    Returns:
        Decimal hours
    """
    try:
        return Decimal(str(float(time_str)))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid time format: {time_str}")


def parse_date(date_str: str) -> date:
    """Parse date string to date object.
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        
    Returns:
        Date object
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD") from e

