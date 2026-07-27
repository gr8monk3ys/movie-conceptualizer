"""
Movie Conceptualizer - AI-powered filmmaking platform.

Script → Shot List → Storyboard

This package provides:
- Fountain screenplay parsing
- AI-powered script analysis
- Automated shot list generation
- Storyboard image prompt creation
- Production planning tools
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("movie-conceptualizer")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0.dev0"
