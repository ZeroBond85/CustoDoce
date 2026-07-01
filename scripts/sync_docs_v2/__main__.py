"""Allow `python -m scripts.sync_docs_v2 --analyze`."""

from scripts.sync_docs_v2.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
