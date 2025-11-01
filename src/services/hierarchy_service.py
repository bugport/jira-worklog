"""Hierarchical grouping service for Jira issues by Epic > Story/Task > Subtask."""

from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from ..models.issue import Issue
from ..models.worklog import ExistingWorkLog

console = None  # Will be initialized if needed


class HierarchicalGroup:
    """Represents a hierarchical group of issues."""
    
    def __init__(self, epic: Optional[Issue] = None):
        """Initialize hierarchical group.
        
        Args:
            epic: Epic issue (top level)
        """
        self.epic = epic
        self.stories_tasks: List[Issue] = []
        self.subtasks_map: Dict[str, List[Issue]] = defaultdict(list)  # parent_key -> subtasks
        self.worklogs: List[ExistingWorkLog] = []
    
    def add_issue(self, issue: Issue):
        """Add issue to appropriate level in hierarchy.
        
        Supports standard Jira hierarchy:
        - Epic (top level)
        - Story/Task/Bug (direct children of Epic)
        - Task (can be direct child of Epic OR child of Story)
        - Subtask (children of Story/Task)
        
        Args:
            issue: Issue to add
        """
        if issue.issue_type.lower() == 'epic':
            self.epic = issue
        elif issue.issue_type.lower() == 'subtask' or issue.parent_key:
            # Subtask - add under parent (Story/Task)
            # OR any issue with a parent_key (e.g., Task under Story)
            parent_key = issue.parent_key
            if parent_key:
                self.subtasks_map[parent_key].append(issue)
            else:
                # Orphan subtask/issue with parent_key but no actual parent
                # Add to stories/tasks level
                self.stories_tasks.append(issue)
        else:
            # Story or Task - can be direct children of Epic
            # This includes:
            # - Stories linked to Epic via parent_epic_key
            # - Tasks linked to Epic via parent_epic_key (direct child of Epic)
            # - Tasks that are children of Stories (will be handled via parent_key check above)
            self.stories_tasks.append(issue)
    
    def add_worklog(self, worklog: ExistingWorkLog):
        """Add worklog to this group.
        
        Args:
            worklog: Worklog to add
        """
        self.worklogs.append(worklog)
    
    def get_all_issues(self) -> List[Issue]:
        """Get all issues in this group in hierarchical order.
        
        Returns:
            List of issues: Epic, then Stories/Tasks, then Subtasks
        """
        result = []
        if self.epic:
            result.append(self.epic)
        
        for story_task in self.stories_tasks:
            result.append(story_task)
            # Add subtasks for this parent
            if story_task.key in self.subtasks_map:
                result.extend(self.subtasks_map[story_task.key])
        
        return result
    
    def get_total_time(self) -> float:
        """Get total time logged in this group.
        
        Returns:
            Total hours as float
        """
        from decimal import Decimal
        total = Decimal("0")
        for wl in self.worklogs:
            total += wl.time_spent_hours
        return float(total)


class HierarchyService:
    """Service for organizing issues by hierarchical relationships."""
    
    @staticmethod
    def _get_epic_path(issue: Issue, issue_map: Dict[str, Issue], visited: Optional[set] = None) -> List[str]:
        """Get the filesystem-like path for an issue (Epic/Story/Task/Subtask).
        
        Filesystem analogy:
        - Epics are directories in root (/)
        - Stories/Tasks are directories inside Epic directories
        - Subtasks are directories inside Story/Task directories
        
        Args:
            issue: Issue to get path for
            issue_map: Dictionary mapping issue keys to Issue objects
            visited: Set of visited issue keys to prevent infinite loops
            
        Returns:
            List of issue keys representing the path from Epic to this issue
            Example: ['EPIC-123', 'STORY-235', 'TASK-456'] for TASK-456 under STORY-235 under EPIC-123
        """
        if visited is None:
            visited = set()
        
        # Prevent infinite loops
        if issue.key in visited:
            return []
        visited.add(issue.key)
        
        path = []
        
        # If this is an Epic, return [Epic]
        if issue.issue_type.lower() == 'epic':
            return [issue.key]
        
        # If issue has direct parent_epic_key, build path: [Epic, ..., this_issue]
        if issue.parent_epic_key and issue.parent_epic_key in issue_map:
            epic_issue = issue_map[issue.parent_epic_key]
            if epic_issue.issue_type.lower() == 'epic':
                # If this issue is directly under Epic (no parent_key), return [Epic, this_issue]
                # This handles Stories and Tasks that are direct children of Epics
                if not issue.parent_key:
                    return [issue.parent_epic_key, issue.key]
                # Otherwise, this issue has a parent (e.g., Task under Story, Subtask under Task)
                # Need to traverse parent chain first to build full path
                if issue.parent_key and issue.parent_key in issue_map:
                    parent_path = HierarchyService._get_epic_path(issue_map[issue.parent_key], issue_map, visited.copy())
                    if parent_path:
                        parent_path.append(issue.key)
                        return parent_path
        
        # If issue has parent_key, traverse up the parent chain
        if issue.parent_key and issue.parent_key in issue_map:
            parent_issue = issue_map[issue.parent_key]
            parent_path = HierarchyService._get_epic_path(parent_issue, issue_map, visited)
            if parent_path:
                parent_path.append(issue.key)
                return parent_path
        
        # Fallback: if issue has parent_epic_key but we couldn't build path, return [Epic]
        if issue.parent_epic_key:
            return [issue.parent_epic_key]
        
        return []
    
    @staticmethod
    def _find_epic_for_issue(issue: Issue, issue_map: Dict[str, Issue], visited: Optional[set] = None) -> Optional[str]:
        """Find the Epic key for an issue by traversing the parent chain.
        
        Uses filesystem analogy: Epics are root directories (/), all other issues are nested inside.
        
        Args:
            issue: Issue to find Epic for
            issue_map: Dictionary mapping issue keys to Issue objects
            visited: Set of visited issue keys to prevent infinite loops
            
        Returns:
            Epic key if found, None otherwise
        """
        # Use path-based approach to ensure correct Epic assignment
        path = HierarchyService._get_epic_path(issue, issue_map, visited)
        if path:
            # First element in path is always the Epic
            epic_key = path[0]
            if epic_key in issue_map:
                epic_issue = issue_map[epic_key]
                if epic_issue.issue_type.lower() == 'epic':
                    return epic_key
        
        return None
    
    @staticmethod
    def group_by_hierarchy(issues: List[Issue], worklogs: Optional[List[ExistingWorkLog]] = None) -> Dict[str, HierarchicalGroup]:
        """Group issues by Epic > Story/Task > Subtask hierarchy.
        
        Args:
            issues: List of Issue objects
            worklogs: Optional list of worklogs to associate with issues
            
        Returns:
            Dictionary mapping epic_key to HierarchicalGroup objects
        """
        if worklogs is None:
            worklogs = []
        
        # Create worklog map by issue key
        worklog_map = defaultdict(list)
        for wl in worklogs:
            worklog_map[wl.issue_key].append(wl)
        
        # Create issue map for efficient lookups
        issue_map: Dict[str, Issue] = {issue.key: issue for issue in issues}
        
        # Group issues by epic
        groups_by_epic: Dict[str, HierarchicalGroup] = {}
        orphan_issues: List[Issue] = []
        
        # First pass: Create groups for all Epics
        for issue in issues:
            if issue.issue_type.lower() == 'epic':
                if issue.key not in groups_by_epic:
                    groups_by_epic[issue.key] = HierarchicalGroup(epic=issue)
        
        # Second pass: Assign issues to their Epic groups (filesystem analogy: place files in correct directories)
        for issue in issues:
            # Skip Epic issues (already handled - these are root directories)
            if issue.issue_type.lower() == 'epic':
                continue
            
            # Find Epic for this issue by traversing parent chain
            # Filesystem analogy: Find which root directory (Epic) this file belongs to
            epic_key = HierarchyService._find_epic_for_issue(issue, issue_map)
            
            if epic_key and epic_key in groups_by_epic:
                # Assign to Epic group (place file in correct directory)
                groups_by_epic[epic_key].add_issue(issue)
                
                # Add worklogs for this issue
                if issue.key in worklog_map:
                    for wl in worklog_map[issue.key]:
                        groups_by_epic[epic_key].add_worklog(wl)
            else:
                # Orphan issue (file without a root directory - Epic)
                orphan_issues.append(issue)
        
        # Handle orphan issues (issues without epics)
        if orphan_issues:
            for issue in orphan_issues:
                # Create a virtual group for orphans
                group_key = f"__orphan__{issue.project or 'unknown'}"
                if group_key not in groups_by_epic:
                    groups_by_epic[group_key] = HierarchicalGroup(epic=None)
                
                groups_by_epic[group_key].add_issue(issue)
                
                # Add worklogs
                if issue.key in worklog_map:
                    for wl in worklog_map[issue.key]:
                        groups_by_epic[group_key].add_worklog(wl)
        
        return groups_by_epic
    
    @staticmethod
    def get_hierarchical_list(groups: Dict[str, HierarchicalGroup]) -> List[Tuple[str, HierarchicalGroup]]:
        """Get hierarchical groups as sorted list.
        
        Args:
            groups: Dictionary of hierarchical groups
            
        Returns:
            List of (epic_key, group) tuples sorted by epic key
        """
        # Sort by epic key (orphan groups last)
        orphan_groups = [(k, g) for k, g in groups.items() if k.startswith("__orphan__")]
        epic_groups = [(k, g) for k, g in groups.items() if not k.startswith("__orphan__")]
        
        # Sort epic groups by epic key
        epic_groups.sort(key=lambda x: x[0])
        orphan_groups.sort(key=lambda x: x[0])
        
        return epic_groups + orphan_groups

