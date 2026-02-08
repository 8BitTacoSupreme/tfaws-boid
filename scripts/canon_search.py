#!/usr/bin/env python3
"""Canon search CLI — thin wrapper around canon_lib search functions.

Usage:
    canon_search.py --error "Cycle: aws_security_group"
    canon_search.py --resource aws_security_group
    canon_search.py --tags cycle,dependency

Outputs JSON to stdout. Intended for piping into other tools or agent consumption.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure canon_lib is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from canon_lib import load_canon, match_error, search_by_resource, search_by_tags


def search_error(error_text: str) -> list[dict]:
    """Search error-signatures.json for matching error patterns."""
    try:
        data = load_canon("error-signatures.json")
        matches = match_error(error_text, data.get("signatures", []))
        return [{"source": "error-signatures.json", "entry": m} for m in matches]
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"WARN: Could not load error-signatures.json: {e}", file=sys.stderr)
        return []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search Canon knowledge base",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               '  %(prog)s --error "Cycle: aws_security_group"\n'
               "  %(prog)s --resource aws_security_group\n"
               "  %(prog)s --tags cycle,dependency\n",
    )
    parser.add_argument(
        "--error", metavar="TEXT",
        help="Match error text against Canon error signatures",
    )
    parser.add_argument(
        "--resource", metavar="TYPE",
        help="Search Canon for entries related to a Terraform resource type",
    )
    parser.add_argument(
        "--tags", metavar="TAG,TAG,...",
        help="Search Canon for entries matching any of the given tags (comma-separated)",
    )

    args = parser.parse_args()

    if not any([args.error, args.resource, args.tags]):
        parser.print_help()
        sys.exit(1)

    results: list[dict] = []

    if args.error:
        results.extend(search_error(args.error))
    if args.resource:
        results.extend(search_by_resource(args.resource))
    if args.tags:
        tag_list = [t.strip() for t in args.tags.split(",") if t.strip()]
        results.extend(search_by_tags(tag_list))

    # Deduplicate by entry content
    seen: set[str] = set()
    unique: list[dict] = []
    for r in results:
        key = json.dumps(r["entry"], sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(r)

    output = {"query": vars(args), "count": len(unique), "results": unique}
    json.dump(output, sys.stdout, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
