"""Compatibility import for published P7 experiments."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from adapters.project_query import ProjectQuery, compact, render_markdown
__all__ = ['ProjectQuery','compact','render_markdown']
