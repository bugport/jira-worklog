"""Jira issue data models."""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime


class Issue(BaseModel):
    """Jira issue model."""
    
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True
    )
    
    key: str = Field(..., description="Issue key (e.g., PROJ-123)")
    summary: str = Field(..., description="Issue summary")
    issue_type: str = Field(..., alias="type", description="Issue type (Task, Story, Epic)")
    status: Optional[str] = Field(None, description="Issue status")
    project: Optional[str] = Field(None, description="Project key")
    assignee: Optional[str] = Field(None, description="Assignee name")
    created: Optional[datetime] = Field(None, description="Creation date")
    updated: Optional[datetime] = Field(None, description="Last update date")
    
    def to_dict(self) -> dict:
        """Convert to dictionary for Excel export."""
        return {
            "Issue Key": self.key,
            "Summary": self.summary,
            "Type": self.issue_type,
            "Status": self.status or "",
            "Project": self.project or "",
            "Time Logged (hours)": "",
            "Date": "",
            "Comment": "",
            "Status": "Pending"
        }

