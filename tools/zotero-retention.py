#!/usr/bin/env python3
"""Keep a paper's original, latest review and previous review; never write Zotero.

Registration records explicit roles after publication verification. Planning is
read-only apart from an ignored JSON plan. Pruning requires that exact plan hash,
checks live linked-file references, and deletes project PDF derivatives only.
The collection poller reads this policy but never invokes deletion itself.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[1]
PAPERS = ROOT / 'docs/zotero/papers'
LOCAL = ROOT / '.local/zotero'
CONFIG = LOCAL / 'paper-retention.json'
PLANS = LOCAL / 'retention-plans'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools'/filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def relative(path):
    return str(path.resolve().relative_to(ROOT.resolve()))


def item_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z0-9]{8}', value):
        raise ValueError('Expected an actual eight-character Zotero item key.')
    return value


def paper_path(value):
    path = (ROOT/value).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_relative_to(PAPERS.resolve()):
        raise ValueError('Retained PDFs must remain in the project paper folders.')
    return path


def workspace_path(value):
    path = (ROOT/value).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError('Technical Reader files must remain in the workspace.')
    return path


def configuration():
    config = read(CONFIG, {'schema_version': 1, 'papers': {}})
    if config.get('schema_version') != 1 or not isinstance(config.get('papers'), dict):
        raise ValueError('Invalid paper-retention configuration.')
    return config


def policy(parent_key):
    item_key(parent_key)
    value = configuration()['papers'].get(parent_key)
    if value is None:
        return None
    if not isinstance(value, dict) or value.get('parent_item_key') != parent_key:
        raise ValueError('Retention policy does not match its bibliographic paper.')
    folder = paper_path(value['paper_folder'])
    item_key(value['active_attachment_key'])
    roles = retained_paths(value)
    if len(set(roles.values())) != len(roles):
        raise ValueError('Source, latest and previous must be different files.')
    for path in roles.values():
        if path.suffix.lower() != '.pdf' or not path.is_relative_to(folder):
            raise ValueError('Every retained role must be a PDF inside its paper folder.')
    for role, accepted in value.get('zotero_attachments', {}).items():
        if role not in roles:
            raise ValueError('Every accepted Zotero attachment role needs a retained local PDF.')
        item_key(accepted.get('attachment_key'))
        if accepted.get('source_ownership') == 'zotero_managed_source':
            # This path is comparison-only. The collection pull reads the actual
            # source returned by its scoped API and never writes managed storage.
            source = Path(accepted.get('source_path', ''))
            if not source.is_absolute() or source.suffix.lower() != '.pdf':
                raise ValueError('Managed source snapshots require their absolute API-returned PDF path.')
    return value


def retained_paths(value):
    return {role: paper_path(value[field]) for role, field in
            [('original', 'original_pdf'), ('latest', 'latest_pdf'), ('previous', 'previous_pdf')]
            if value.get(field)}


def pdf_files(folder):
    return [path for path in folder.rglob('*') if path.suffix.lower() == '.pdf'
            and (path.is_file() or path.is_symlink())]


def register(parent_key, original, latest, previous, active_attachment_key,
             publication_verified=False):
    if not publication_verified:
        raise ValueError('Register retention only after the published review has been verified.')
    item_key(parent_key)
    item_key(active_attachment_key)
    paths = {role: paper_path(path) for role, path in
             [('original', original), ('latest', latest), ('previous', previous)] if path}
    if 'original' not in paths or 'latest' not in paths:
        raise ValueError('An immutable original and a verified current review are required.')
    folder = paths['latest'].parent
    if len(set(paths.values())) != len(paths):
        raise ValueError('Each retained version must have its own file.')
    snapshots = {}
    for role, path in paths.items():
        if not path.is_file() or not path.is_relative_to(folder):
            raise ValueError('Retained versions must exist inside the same paper folder.')
        with fitz.open(path) as document:
            if not document.is_pdf or document.needs_pass or not len(document):
                raise ValueError('A retained role is not a readable PDF.')
            snapshots[role] = {'sha256': sha(path), 'pages': len(document)}
    existing = policy(parent_key)
    if existing and snapshots['original']['sha256'] != existing['snapshots']['original']['sha256']:
        raise ValueError('The immutable original differs from the registered original.')
    entry = {'parent_item_key': parent_key, 'paper_folder': relative(folder),
             'active_attachment_key': active_attachment_key,
             **{role+'_pdf': relative(path) for role, path in paths.items()},
             'snapshots': snapshots, 'publication_verified': True,
             'registered_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    config = configuration()
    config['papers'][parent_key] = entry
    collection = module('retention_registration_collection', 'zotero-collection-sync.py')
    collection.atomic_json(CONFIG, config)
    return entry


def validate_current(entry, bridge=None):
    paths = retained_paths(entry)
    if not entry.get('publication_verified'):
        raise ValueError('The latest reviewed attachment has not been verified.')
    for role, path in paths.items():
        if not path.is_file():
            raise ValueError(f'The retained {role} PDF is missing.')
        with fitz.open(path) as document:
            if not len(document) or document.needs_pass:
                raise ValueError(f'The retained {role} PDF is not readable.')
        if role in ('original', 'previous') and sha(path) != entry['snapshots'][role]['sha256']:
            raise ValueError(f'The retained {role} PDF changed; preserve it for review.')
    reader = read(LOCAL/'reader-sync.json', {})
    state = read(LOCAL/'sync-state.json', {})
    if (reader.get('parent_item_key') != entry['parent_item_key']
            or reader.get('attachment_key') != entry['active_attachment_key']
            or paper_path(reader['mirror_pdf']) != paths['latest']):
        raise ValueError('Retention must identify the current configured reviewed attachment.')
    for field, digest in [('reader_pdf', 'reader_sha256'), ('mirror_pdf', 'mirror_sha256')]:
        path = workspace_path(reader[field])
        if reader[field] != state.get(field) or not path.is_file() or sha(path) != state.get(digest):
            raise ValueError('Resolve Reader/mirror baseline conflicts before pruning.')
    if state.get('error') or state.get('status') not in ('updated', 'unchanged'):
        raise ValueError('The live annotation mirror has not accepted the published review.')
    if bridge is None:
        bridge = module('retention_live_bridge', 'zotero-mcp.py')
    parent = bridge.allowed_item(entry['parent_item_key'])
    if parent['key'] != entry['parent_item_key']:
        raise ValueError('The paper is outside the configured collection.')
    linked = []
    for item in bridge.all_objects(f"users/0/items/{entry['parent_item_key']}/children"):
        data = item['data']
        if data.get('itemType') == 'attachment' and data.get('linkMode') == 'linked_file':
            linked.append(Path(data['path']).resolve())
    return paths, linked


def build_plan(parent_key, bridge=None):
    entry = policy(parent_key)
    if entry is None:
        raise ValueError('Register explicit source/latest/previous roles before planning cleanup.')
    paths, linked = validate_current(entry, bridge)
    keep = set(paths.values())
    folder = paper_path(entry['paper_folder'])
    candidates = []
    for path in sorted(pdf_files(folder)):
        resolved = path.resolve()
        if not resolved.is_relative_to(folder):
            raise ValueError('A PDF symlink escapes the paper folder.')
        if path.is_symlink():
            raise ValueError('Resolve PDF symlink aliases before applying exact three-file retention.')
        if resolved in keep:
            continue
        if resolved in linked:
            raise ValueError('An obsolete-looking PDF is still linked in Zotero; relink it safely before pruning: '
                             + relative(resolved))
        candidates.append({'path': relative(resolved), 'sha256': sha(resolved), 'bytes': resolved.stat().st_size})
    plan = {'schema_version': 1, 'parent_item_key': parent_key,
            'keep': {role: {'path': relative(path), 'sha256': sha(path)} for role, path in paths.items()},
            'delete': candidates, 'active_attachment_key': entry['active_attachment_key'],
            'paper_folder': relative(folder)}
    encoded = json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    plan['plan_sha256'] = hashlib.sha256(encoded).hexdigest()
    return plan


def plan(parent_key, bridge=None):
    result = build_plan(parent_key, bridge)
    collection = module('retention_plan_collection', 'zotero-collection-sync.py')
    collection.atomic_json(PLANS/(parent_key+'.json'), result)
    return result


def prune(parent_key, expected_plan_sha256, bridge=None):
    if not re.fullmatch(r'[0-9a-f]{64}', expected_plan_sha256 or ''):
        raise ValueError('Pruning requires the exact reviewed plan SHA-256.')
    collection = module('retention_prune_collection', 'zotero-collection-sync.py')
    mirror = module('retention_prune_mirror', 'zotero-live-mirror.py')
    with ExitStack() as stack:
        stack.enter_context(collection.instance_lock())
        stack.enter_context(mirror.transaction())
        saved = read(PLANS/(item_key(parent_key)+'.json'))
        if not saved or saved.get('plan_sha256') != expected_plan_sha256:
            raise ValueError('No matching reviewed retention plan exists.')
        current = build_plan(parent_key, bridge)
        if current != saved:
            raise ValueError('The retention plan changed; review a fresh plan before deleting anything.')
        journal = {'parent_item_key': parent_key, 'plan_sha256': expected_plan_sha256,
                   'status': 'pruning', 'removed': [], 'keep': current['keep']}
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        journal_path = LOCAL/'retention-actions'/(parent_key+'-'+stamp+'.json')
        collection.atomic_json(journal_path, journal)
        for row in current['delete']:
            path = paper_path(row['path'])
            if not path.is_file() or sha(path) != row['sha256']:
                raise ValueError('A cleanup candidate changed; remaining files were preserved.')
            path.unlink()
            journal['removed'].append(row)
            collection.atomic_json(journal_path, journal)
        entry = policy(parent_key)
        folder = paper_path(entry['paper_folder'])
        for directory in sorted([p for p in folder.rglob('*') if p.is_dir()], key=lambda p: len(p.parts), reverse=True):
            if not any(directory.iterdir()):
                directory.rmdir()
        for row in current['keep'].values():
            if sha(paper_path(row['path'])) != row['sha256']:
                raise RuntimeError('A retained PDF changed during cleanup; inspect the journal.')
        remaining = pdf_files(folder)
        if (len(remaining) != len(current['keep'])
                or set(p.resolve() for p in remaining) != set(retained_paths(entry).values())):
            raise RuntimeError('Unexpected PDFs appeared during cleanup; they were preserved.')
        if 'previous' in current['keep']:
            # Reuse the retained snapshot instead of keeping another private PDF.
            # The mirror uses this pointer only to avoid making an initial backup.
            state = read(LOCAL/'sync-state.json', {})
            state['mirror_backup'] = current['keep']['previous']['path']
            collection.atomic_json(LOCAL/'sync-state.json', state)
            journal['mirror_backup'] = state['mirror_backup']
        journal.update(status='complete', remaining_pdfs=len(current['keep']))
        collection.atomic_json(journal_path, journal)
        return {'status': 'complete', 'removed_pdfs': len(journal['removed']),
                'remaining_pdfs': journal['remaining_pdfs'], 'journal': relative(journal_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    register_parser = commands.add_parser('register')
    register_parser.add_argument('parent_key')
    register_parser.add_argument('--original', required=True)
    register_parser.add_argument('--latest', required=True)
    register_parser.add_argument('--previous')
    register_parser.add_argument('--attachment', required=True)
    register_parser.add_argument('--publication-verified', action='store_true')
    plan_parser = commands.add_parser('plan')
    plan_parser.add_argument('parent_key')
    prune_parser = commands.add_parser('prune')
    prune_parser.add_argument('parent_key')
    prune_parser.add_argument('--expected-plan-sha256', required=True)
    args = parser.parse_args()
    if args.command == 'register':
        result = register(args.parent_key, args.original, args.latest, args.previous,
                          args.attachment, args.publication_verified)
    elif args.command == 'plan':
        result = plan(args.parent_key)
    else:
        result = prune(args.parent_key, args.expected_plan_sha256)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
