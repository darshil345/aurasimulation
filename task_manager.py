"""
Compatibility module for cleaner imports.

User-facing architecture exposes `task_manager.py`,
while implementation lives in `core/task_manager.py`.
"""

from core.task_manager import TaskManager

__all__ = ["TaskManager"]
