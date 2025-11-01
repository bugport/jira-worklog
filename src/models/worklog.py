"""Work log data models."""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional
from datetime import datetime, date
from decimal import Decimal


class WorkLog(BaseModel):
    """Work log entry model."""
    
    model_config = ConfigDict(from_attributes=True)
    
    issue_key: str = Field(..., description="Jira issue key")
    time_spent_seconds: int = Field(..., description="Time spent in seconds")
    comment: Optional[str] = Field(None, description="Work log comment")
    started: Optional[datetime] = Field(None, description="Work log start time")


class WorkLogEntry(BaseModel):
    """Work log entry from Excel."""
    
    model_config = ConfigDict(populate_by_name=True)
    
    issue_key: str = Field(..., description="Jira issue key (e.g., PROJ-123)")
    time_logged_hours: Decimal = Field(..., description="Time logged in hours (decimal)")
    work_date: date = Field(..., description="Work log date (YYYY-MM-DD)", alias="date")
    comment: Optional[str] = Field(None, description="Work log comment")
    
    @field_validator('issue_key', mode='before')
    @classmethod
    def validate_issue_key(cls, v) -> str:
        """Validate issue key format."""
        if not v:
            raise ValueError("Issue key is required")
        v = str(v).strip()
        if not v:
            raise ValueError("Issue key is required")
        
        # Basic validation: should match pattern PROJ-123
        if '-' not in v:
            raise ValueError(f"Invalid issue key format: {v}. Expected format: PROJ-123")
        
        parts = v.split('-')
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Invalid issue key format: {v}. Expected format: PROJ-123")
        
        return v.upper()
    
    @field_validator('time_logged_hours', mode='before')
    @classmethod
    def validate_time(cls, v) -> Decimal:
        """Validate time logged."""
        if isinstance(v, str):
            v = Decimal(v)
        v = Decimal(v)
        if v <= 0:
            raise ValueError("Time logged must be greater than 0")
        if v > 24:
            raise ValueError("Time logged cannot exceed 24 hours per day")
        return v
    
    def to_worklog(self) -> WorkLog:
        """Convert to Jira WorkLog model."""
        # Convert hours to seconds
        time_spent_seconds = int(float(self.time_logged_hours) * 3600)
        
        # Convert date to datetime (start of day in UTC)
        started = datetime.combine(self.work_date, datetime.min.time())
        
        return WorkLog(
            issue_key=self.issue_key,
            time_spent_seconds=time_spent_seconds,
            comment=self.comment or "",
            started=started
        )


class ExistingWorkLog(BaseModel):
    """Existing work log from Jira with ID for tracking."""
    
    model_config = ConfigDict(from_attributes=True)
    
    worklog_id: str = Field(..., description="Jira work log ID")
    issue_key: str = Field(..., description="Jira issue key")
    time_spent_seconds: int = Field(..., description="Time spent in seconds")
    time_spent_hours: Decimal = Field(..., description="Time spent in hours (calculated)")
    comment: Optional[str] = Field(None, description="Work log comment")
    started: datetime = Field(..., description="Work log start time")
    author: Optional[str] = Field(None, description="Work log author")
    
    def to_excel_row(self, issue_summary: str = "", issue_type: str = "") -> dict:
        """Convert to Excel row format with original values tracked."""
        return {
            "Worklog ID": self.worklog_id,
            "Issue Key": self.issue_key,
            "Summary": issue_summary,
            "Type": issue_type,
            "Time Logged (hours)": str(self.time_spent_hours),
            "Original Time (hours)": str(self.time_spent_hours),  # Track original
            "Date": self.started.date() if self.started else "",
            "Comment": self.comment or "",
            "Original Comment": self.comment or "",  # Track original
            "Author": self.author or "",
            "Status": "Original"
        }


class WorkLogUpdate(BaseModel):
    """Work log update entry from Excel diff."""
    
    model_config = ConfigDict(populate_by_name=True)
    
    worklog_id: str = Field(..., description="Jira work log ID")
    issue_key: str = Field(..., description="Jira issue key")
    original_time_hours: Decimal = Field(..., description="Original time in hours")
    new_time_hours: Decimal = Field(..., description="New time in hours")
    original_comment: Optional[str] = Field(None, description="Original comment")
    new_comment: Optional[str] = Field(None, description="New comment")
    work_date: date = Field(..., description="Work log date", alias="date")
    
    @field_validator('new_time_hours', mode='before')
    @classmethod
    def validate_time(cls, v) -> Decimal:
        """Validate time logged."""
        if isinstance(v, str):
            v = Decimal(v)
        v = Decimal(v)
        if v <= 0:
            raise ValueError("Time logged must be greater than 0")
        if v > 24:
            raise ValueError("Time logged cannot exceed 24 hours per day")
        return v
    
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        time_changed = self.new_time_hours != self.original_time_hours
        comment_changed = (self.new_comment or "") != (self.original_comment or "")
        return time_changed or comment_changed


class SyncResult(BaseModel):
    """Work log sync result."""
    
    model_config = ConfigDict(from_attributes=True)
    
    issue_key: str
    worklog_id: Optional[str] = None
    success: bool
    message: str
    operation: str = Field(default="add", description="Operation: add, update, or delete")

