"""
Compatibility module for installation history.

This module re-exports InstallationHistory and InstallationType
from installation_history.py to preserve the public API
(cortex.history) used across the codebase.
"""

from cortex.installation_history import InstallationHistory, InstallationType

__all__ = ["InstallationHistory", "InstallationType"]
