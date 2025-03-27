"""
AI Host Service for Jeopardy

This module is maintained for backward compatibility.
The AIHostService implementation has been moved to the host/ package.
"""

from .host.service import AIHostService

# Re-export for backward compatibility
__all__ = ["AIHostService"] 