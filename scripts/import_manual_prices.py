#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.import_service import import_manual_prices


def main():
    parser = argparse.ArgumentParser(description="Import manual prices from CSV/XLSX")
    parser.add_argument("file", help="Path to the import file")
    args = parser.parse_args()

    print(f"Importing prices from {args.file}...")
    result = import_manual_prices(args.file)

    print(f"Successfully imported: {result['imported']}")
    if result["errors"]:
        print("\nErrors encountered:")
        for err in result["errors"]:
            print(f"  - {err}")


if __name__ == "__main__":
    main()
