#!/usr/bin/env python3
"""ECE6420 collection access; never writes the Zotero library."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    sub.add_parser('pull-papers')
    search = sub.add_parser('search')
    search.add_argument('query', nargs='?', default='')
    for name in ('read', 'edit', 'annotations'):
        command = sub.add_parser(name)
        command.add_argument('item_key')
        if name == 'read':
            command.add_argument('--page', type=int, required=True)
            command.add_argument('--end-page', type=int)
    args = parser.parse_args()
    bridge = module('ece6420_zotero_bridge', 'zotero-mcp.py')
    try:
        if args.command == 'status':
            result = bridge.zotero_status()
            collection = module('ece6420_zotero_collection', 'zotero-collection-sync.py')
            result['collection_mirror'] = collection.summary(collection.load(collection.STATE, {}))
        elif args.command == 'pull-papers':
            collection = module('ece6420_zotero_collection', 'zotero-collection-sync.py')
            result = collection.sync_once(bridge=bridge)
        elif args.command == 'search':
            result = bridge.zotero_search_items(args.query, 100)
        elif args.command == 'read':
            result = bridge.zotero_read_pdf_pages(args.item_key, args.page, args.end_page)
        elif args.command == 'edit':
            result = bridge.zotero_prepare_pdf_edit(args.item_key)
        else:
            result = bridge.zotero_get_annotations(args.item_key)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(result.get('connected') is False or result.get('status') in ('partial', 'error'))
    except (ValueError, RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
