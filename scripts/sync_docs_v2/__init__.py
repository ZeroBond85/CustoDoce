"""sync_docs_v2 — heading-aware documentation sync.

Extends sync_docs.py with markdown-it heading analysis:
- --analyze: classify stale refs as CURRENT/HISTORICAL/AMBIGUOUS
- --sync: auto-update CURRENT blocks with truth values
"""

from scripts.sync_docs_v2.cli import main

__all__ = ["main"]
