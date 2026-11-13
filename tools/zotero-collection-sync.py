#!/usr/bin/env python3
"""Pull the scoped Zotero collection into one project-local folder per paper.

This process performs GET requests only. It never relinks attachments, uploads
PDFs, removes files, or writes Zotero annotations. Local modifications cause a
conflict instead of being overwritten. Distinct source attachments remain separate assets. Only explicitly configured
verified review roles use the optional retention policy; polling never deletes files.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import tempfile
import threading
import time
import unicodedata
from urllib.parse import unquote, urlencode, urlparse
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
PAPERS = ROOT / 'docs/zotero/papers'
LOCAL = ROOT / '.local/zotero'
STATE = LOCAL / 'collection-sync.json'
LOCK = LOCAL / 'collection-sync.lock'
LOCAL_TZ = ZoneInfo('America/New_York')
SOURCE_BODIES = LOCAL / 'source-bodies'
SOURCE_HISTORY = LOCAL / 'source-history'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def load(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def relative(path):
    return str(path.resolve().relative_to(ROOT.resolve()))


def paper_path(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(PAPERS.resolve()):
        raise ValueError('Paper paths must remain under docs/zotero/papers/.')
    return path


def reader_path(value):
    """Native editable Reader bodies may be private implementation files."""
    path = (ROOT / value).resolve()
    if path.suffix.lower() != '.pdf' or not any(path.is_relative_to(base.resolve()) for base in
                                              (PAPERS, LOCAL/'readers')):
        raise ValueError('Reader PDFs must stay in the paper folders or private .local/zotero/readers/.')
    return path


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def instance_lock():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open('a') as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another collection synchronization is running.') from exc
        yield


def slug(value, maximum=75):
    ascii_text = unicodedata.normalize('NFKD', value or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^A-Za-z0-9]+', '_', ascii_text).strip('_')[:maximum].rstrip('_') or 'Untitled'


def item_key(item):
    key = item.get('key', '')
    if not re.fullmatch(r'[A-Z0-9]{8}', key):
        raise ValueError('Expected an eight-character Zotero item key.')
    return key


def paper_folder(item):
    """Derive a stable readable initial folder; persisted paths survive retitles."""
    data = item['data']
    authors = [c for c in data.get('creators', []) if c.get('creatorType') == 'author']
    creator = authors[0] if authors else (data.get('creators') or [{}])[0]
    name = creator.get('lastName') or creator.get('name') or 'Project'
    year = re.search(r'\b(?:18|19|20|21)\d{2}\b', data.get('date') or '')
    prefix = slug(name, 18) + '_' + (year[0] if year else 'undated')
    room = 110 - len(prefix) - len(item_key(item)) - 2
    return PAPERS / (prefix + '_' + slug(data.get('title'), min(75, room)) + '_' + item_key(item))


def version_filename(item, role, when=None):
    """Local-time saved-version name, independent of attachment labels and IDs."""
    when = when or datetime.now(LOCAL_TZ)
    if when.tzinfo is None:
        raise ValueError('Version timestamps must include a timezone.')
    stamp = when.astimezone(LOCAL_TZ).strftime('%Y-%m-%d_%H-%M-%S')
    return stamp + '_' + slug(item['data'].get('title'), 150) + '_' + slug(role, 48) + '.pdf'


def version_path(paper, item, role, when=None, reserved=()):
    """Keep the requested format even when two saves occur in the same second."""
    when = when or datetime.now(LOCAL_TZ)
    for number in range(1, 10000):
        suffix = role if number == 1 else role + '_' + str(number).zfill(2)
        path = paper / version_filename(item, suffix, when)
        if not path.exists() and not path.with_suffix('').exists() and path not in reserved:
            return path
    raise ValueError('Could not allocate a distinct timestamped version name.')


class LocalAPI:
    """Read-only Local API transport, pinned to the running Zotero instance."""
    def __init__(self, bridge, expected_server=None):
        self.bridge = bridge
        self.server_id = expected_server

    def get(self, path, params=None, text=False):
        headers = {'Zotero-API-Version': '3', 'Accept': 'application/json'}
        if self.server_id:
            headers['Zotero-Server-ID'] = self.server_id
        request = Request(self.bridge.BASE + path + ('?' + urlencode(params) if params else ''),
                          headers=headers, method='GET')
        with self.bridge.OPENER.open(request, timeout=20) as response:
            identity = response.headers.get('Zotero-Server-ID')
            if not identity or self.server_id not in (None, identity):
                raise RuntimeError('Zotero server identity changed; preserve the previous baseline for review.')
            self.server_id = identity
            raw = response.read().decode('utf-8')
        return raw if text else json.loads(raw)

    def all(self, path, params=None):
        result = []
        while True:
            batch = self.get(path, {**(params or {}), 'format': 'json', 'limit': 100, 'start': len(result)})
            if not isinstance(batch, list):
                raise ValueError('Expected an API item list.')
            result.extend(batch)
            if len(batch) < 100:
                return result

    def inventory(self):
        collections = self.all('users/0/collections')
        matches = [c for c in collections if c['key'] == self.bridge.COLLECTION_KEY] if self.bridge.COLLECTION_KEY else [
            c for c in collections if c['data']['name'].casefold() == self.bridge.COLLECTION.casefold()]
        if len(matches) != 1:
            raise RuntimeError('Expected exactly one configured project collection.')
        chosen = matches[0]
        allowed = {item_key(chosen)}
        while True:
            expanded = allowed | {item_key(c) for c in collections if c['data'].get('parentCollection') in allowed}
            if expanded == allowed:
                break
            allowed = expanded
        items = {}
        for key in sorted(allowed):
            for item in self.all(f'users/0/collections/{key}/items/top'):
                if not item['data'].get('deleted'):
                    items[item_key(item)] = item
        return chosen, items

    def source(self, attachment):
        uri = urlparse(self.get(f'users/0/items/{item_key(attachment)}/file/view/url', text=True).strip())
        if uri.scheme != 'file' or uri.netloc not in ('', 'localhost'):
            raise ValueError('Zotero did not return a local PDF file.')
        path = Path(unquote(uri.path)).resolve(strict=True)
        if not path.is_file() or path.suffix.lower() != '.pdf':
            raise ValueError('PDF is not downloaded in Zotero Desktop.')
        return path

    def annotations(self, attachment):
        key = item_key(attachment)
        values = self.all(f'users/0/items/{key}/children', {'itemType': 'annotation'})
        if any(i['data'].get('parentItem') != key or i['data'].get('itemType') != 'annotation' for i in values):
            raise ValueError('The API returned an annotation outside the requested PDF.')
        return {item_key(i): i for i in values if not i['data'].get('deleted')}


class Conflict(RuntimeError):
    pass


def guard(path, expected, incoming=None):
    actual = sha256(path) if path.exists() else None
    if expected and actual != expected:
        raise Conflict(f'Local file changed or was removed; preserving it: {relative(path)}')
    if not expected and actual is not None and actual != incoming:
        raise Conflict(f'Existing file has no accepted baseline; preserving it: {relative(path)}')
    return actual


def source_body_path(value):
    path = (ROOT / value).resolve()
    if path.suffix.lower() != '.pdf' or not path.is_relative_to(SOURCE_BODIES.resolve()):
        raise ValueError('Native annotation source bodies must remain in private .local/zotero/source-bodies/.')
    return path


def attachment_label(attachment):
    data = attachment['data']
    label = data.get('title') or Path(data.get('filename') or '').stem or 'PDF'
    return slug(label, 32)


def preserve_private(path, digest, attachment_key):
    """Preserve real source revisions and annotation-role transitions privately."""
    if not path or not digest:
        return None
    if not path.is_file() or sha256(path) != digest:
        raise Conflict('A source-version file changed before it could be preserved.')
    folder = SOURCE_HISTORY / attachment_key
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / path.name
    number = 2
    while target.exists() and sha256(target) != digest:
        target = folder / (path.stem + '_' + str(number).zfill(2) + path.suffix)
        number += 1
    if target.exists():
        if path.resolve() != target.resolve():
            if sha256(path) != digest or sha256(target) != digest:
                raise Conflict('Duplicate source history failed final hash verification.')
            path.unlink()
        return relative(target)
    os.replace(path, target)
    if sha256(target) != digest:
        raise RuntimeError('Source-version verification failed after preservation.')
    return relative(target)


def configured_reader():
    config = load(LOCAL / 'reader-sync.json', {})
    if config:
        reader_path(config['reader_pdf'])
        paper_path(config['mirror_pdf'])
        if config.get('paper_folder'):
            paper_path(config['paper_folder'])
    return config


def metadata_only_attachment(api, attachment, parent, paper, old):
    """Keep annotations searchable without recreating pruned legacy PDF copies."""
    key = item_key(attachment)
    records = api.annotations(attachment)
    return {**old, 'key': key, 'parent_item_key': item_key(parent),
            'paper_folder': relative(paper), 'attachment_title': attachment['data'].get('title', ''),
            'attachment_version': attachment.get('version'), 'in_collection': True,
            'status': 'metadata_only', 'source_pdf': None, 'display_pdf': None,
            'annotations': records, 'native_annotations': len(records),
            'source_ownership': 'zotero', 'retention_reason': 'Only original/latest/previous are retained locally.',
            'warnings': [], 'error': None, 'last_success_at': now()}


def retained_snapshot_attachment(api, attachment, parent, paper, old, retention, role):
    """Expose an accepted original/previous attachment without extra PDF copies.

    Retained snapshots never overwrite a local edit or silently accept new native
    annotations. Such changes require reconciliation before rotating versions.
    """
    key = item_key(attachment)
    row = {**old, 'key': key, 'parent_item_key': item_key(parent),
           'paper_folder': relative(paper), 'attachment_title': attachment['data'].get('title', ''),
           'attachment_version': attachment.get('version'), 'in_collection': True,
           'retained_role': role}
    try:
        accepted = retention['zotero_attachments'][role]
        records = api.annotations(attachment)
        fingerprint = hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        row.update(annotations=records, native_annotations=len(records))
        source = api.source(attachment)
        display = paper_path(retention[role+'_pdf'])
        managed_source = accepted.get('source_ownership') == 'zotero_managed_source'
        if managed_source:
            expected_source = Path(accepted['source_path'])
            if not expected_source.is_absolute() or expected_source.suffix.lower() != '.pdf':
                raise ValueError('An accepted managed PDF must identify its absolute API source path.')
            expected_source = expected_source.resolve()
        else:
            expected_source = reader_path(accepted['reader_pdf'])
        if (key != accepted['attachment_key'] or source != expected_source
                or sha256(source) != accepted['reader_sha256']):
            raise Conflict('The retained '+role+' attachment body changed; reconcile its version before pulling.')
        if not display.is_file() or sha256(display) != retention['snapshots'][role]['sha256']:
            raise Conflict('The retained '+role+' local PDF changed; preserve it for review.')
        if fingerprint != accepted['annotation_fingerprint']:
            raise Conflict('Native annotations on the retained '+role+' snapshot changed; reconcile them before rotating versions.')
        row.update(status='retained_snapshot',
                   source_pdf=relative(source) if source.is_relative_to(ROOT.resolve()) else None,
                   source_zotero_path=str(source), display_pdf=relative(display),
                   source_sha256=accepted['reader_sha256'], mirror_sha256=sha256(display),
                   annotation_fingerprint=fingerprint,
                   source_ownership='zotero_managed_source' if managed_source else 'zotero_linked',
                   warnings=[], error=None, last_success_at=now())
    except Conflict as exc:
        row.update(status='conflict', error=str(exc))
    except Exception as exc:
        row.update(status='unavailable', error=str(exc))
    return row


def sync_collection_reader(api, renderer, attachment, parent, source, source_sha, records, fingerprint, old, reader):
    """Mirror an explicitly published linked Reader without mutating its body.

    Structural publication pins the accepted Reader hash. Native annotation
    autosaves update only the configured display file and synchronization state.
    """
    key = item_key(attachment)
    configured_source = reader_path(reader['reader_pdf'])
    display = paper_path(reader['mirror_pdf'])
    if (attachment['data'].get('linkMode') != 'linked_file' or source != configured_source
            or item_key(parent) != reader.get('parent_item_key') or source == display):
        raise Conflict('The collection-owned Reader must be the configured linked PDF under the same paper.')
    if reader.get('reader_sha256') != source_sha:
        raise Conflict('The published Reader body changed; verify structural edits before accepting a new baseline.')
    state_path = LOCAL / 'sync-state.json'
    saved = load(state_path, {})
    if saved.get('attachment_key') not in (None, key):
        raise Conflict('The Reader synchronization state belongs to another attachment.')
    if saved.get('reader_sha256') not in (None, source_sha):
        raise Conflict('The Reader hash differs from its accepted synchronization baseline.')
    if saved and (saved.get('reader_pdf') != relative(source)
                  or saved.get('mirror_pdf') != relative(display)):
        raise Conflict('The Reader or mirror path differs from its accepted synchronization baseline.')
    expected_display = saved.get('mirror_sha256') or old.get('mirror_sha256') or reader.get('mirror_sha256')
    actual_display = guard(display, expected_display, source_sha if not records else None)
    accepted_fingerprint = saved.get('annotation_fingerprint') or old.get('annotation_fingerprint')
    unchanged = (actual_display is not None and accepted_fingerprint == fingerprint
                 and (saved.get('reader_sha256') or old.get('source_sha256')) == source_sha)
    warnings = saved.get('warnings', old.get('warnings', []))
    if not unchanged:
        display.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.' + key + '-mirror-', suffix='.pdf', dir=display.parent)
        os.close(fd)
        temp = Path(name)
        try:
            if records:
                warnings = renderer.rebuild(source, temp, records)
            else:
                shutil.copy2(source, temp)
                warnings = []
            final_records = api.annotations(attachment)
            final_fingerprint = hashlib.sha256(json.dumps(final_records, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            if sha256(source) != source_sha or final_fingerprint != fingerprint:
                raise Conflict('The Reader or native annotations changed while generating the review mirror.')
            if (sha256(display) if display.exists() else None) != actual_display:
                raise Conflict('The review mirror changed while generating its replacement.')
            os.replace(temp, display)
            actual_display = sha256(display)
        finally:
            temp.unlink(missing_ok=True)
    status = 'unchanged' if unchanged else 'updated'
    snapshot = {**saved, 'schema_version': 1, 'mirror_owner': 'collection', 'status': status,
                'attachment_key': key, 'parent_item_key': item_key(parent),
                'reader_pdf': relative(source), 'mirror_pdf': relative(display),
                'reader_sha256': source_sha, 'mirror_sha256': actual_display,
                'annotations': records, 'annotation_fingerprint': fingerprint,
                'native_annotations': len(records), 'warnings': warnings, 'error': None,
                'updated_at': now(), 'last_success_at': now()}
    atomic_json(state_path, snapshot)
    saved_at = reader.get('version_timestamp') or old.get('version_timestamp') or datetime.now(LOCAL_TZ).isoformat(timespec='seconds')
    return {**old, 'key': key, 'parent_item_key': item_key(parent),
            'paper_folder': relative(display.parent), 'attachment_title': attachment['data'].get('title', ''),
            'attachment_version': attachment.get('version'), 'in_collection': True,
            'status': status, 'mirror_owner': 'collection', 'asset_kind': 'explicit_review',
            'retained_role': 'latest', 'source_pdf': relative(source), 'display_pdf': relative(display),
            'source_sha256': source_sha, 'mirror_sha256': actual_display,
            'source_ownership': 'zotero_linked', 'annotations': records,
            'annotation_fingerprint': fingerprint, 'native_annotations': len(records),
            'version_timestamp': saved_at, 'version_timezone': 'America/New_York',
            'filename_role': reader.get('filename_role', 'Reviewed_EN_Annotated'),
            'warnings': warnings, 'error': None, 'last_success_at': now()}


def sync_attachment(api, renderer, attachment, parent, paper, old, reader):
    key = item_key(attachment)
    row = dict(old)
    row.update(key=key, parent_item_key=item_key(parent), paper_folder=relative(paper),
               attachment_title=attachment['data'].get('title', ''), attachment_version=attachment.get('version'),
               in_collection=True, asset_kind='distinct_source_attachment')
    try:
        records = api.annotations(attachment)
        row.update(annotations=records, native_annotations=len(records))
        source = api.source(attachment)
        source_sha = sha256(source)
        fingerprint = hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if sha256(source) != source_sha:
            raise RuntimeError('Source PDF changed while reading annotations; retry on the next cycle.')
        if reader.get('attachment_key') == key:
            if reader.get('mirror_owner') == 'collection':
                return sync_collection_reader(api, renderer, attachment, parent, source, source_sha,
                                              records, fingerprint, old, reader)
            configured_source, display = reader_path(reader['reader_pdf']), paper_path(reader['mirror_pdf'])
            if source != configured_source:
                raise Conflict('The reviewed attachment differs from its configured reader path.')
            mirror_state = load(LOCAL / 'sync-state.json', {})
            if mirror_state.get('attachment_key') != key or mirror_state.get('reader_sha256') != source_sha:
                raise Conflict('The dedicated mirror has not accepted the current source PDF yet.')
            if not display.exists() or sha256(display) != mirror_state.get('mirror_sha256'):
                raise Conflict('The dedicated mirror contains local edits or is unavailable.')
            row.update(status='dedicated_mirror', source_pdf=relative(source), display_pdf=relative(display),
                       source_sha256=source_sha, mirror_sha256=sha256(display), annotations=records,
                       annotation_fingerprint=fingerprint, native_annotations=len(records),
                       warnings=mirror_state.get('warnings', []), error=None, last_success_at=now(),
                       asset_kind='explicit_review')
            return row
        linked_source = (attachment['data'].get('linkMode') == 'linked_file'
                         and source.is_relative_to(paper.resolve()))
        if linked_source and not records:
            row.update(status='linked_source', source_pdf=relative(source), display_pdf=relative(source),
                       source_sha256=source_sha, mirror_sha256=source_sha, annotations=records,
                       annotation_fingerprint=fingerprint, native_annotations=0,
                       source_ownership='zotero_linked', warnings=[], error=None, last_success_at=now())
            return row
        saved_at = datetime.now(LOCAL_TZ)
        label = attachment_label(attachment)
        role = (old.get('filename_role') if old.get('retained_role') == 'latest'
                else ('Annotated_' if records else 'Source_') + label)
        source_role = 'Source_Body_' + label
        display = paper_path(old['display_pdf']) if old.get('display_pdf') else version_path(paper, parent, role, saved_at)
        display_baseline = old.get('mirror_sha256')
        if display == source:
            display = version_path(paper, parent, role, saved_at)
            display_baseline = None
        raw_path = source_body_path(old['source_pdf']) if old.get('source_pdf') and old.get('source_ownership') != 'zotero_linked' else None
        if not raw_path and records:
            raw_folder = SOURCE_BODIES / key
            raw_folder.mkdir(parents=True, exist_ok=True)
            raw_path = version_path(raw_folder, parent, source_role, saved_at)
        display_actual = guard(display, display_baseline, source_sha if not records else None)
        raw_actual = guard(raw_path, old.get('raw_copy_sha256'), source_sha) if raw_path else None
        if (display_actual is not None and old.get('source_sha256') == source_sha
                and old.get('annotation_fingerprint') == fingerprint):
            row.update(status='unchanged', error=None, native_annotations=len(records), last_success_at=now())
            return row
        previous_display, previous_raw = display, raw_path
        source_revision = bool(old.get('source_sha256') and old['source_sha256'] != source_sha)
        role_changed = bool(old.get('filename_role') and old['filename_role'] != role)
        if source_revision or role_changed:
            display = version_path(paper, parent, role, saved_at)
        if source_revision and raw_path:
            raw_path = version_path(SOURCE_BODIES / key, parent, source_role, saved_at)
        paper.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.' + key + '-', suffix='.pdf', dir=paper)
        os.close(fd)
        temp = Path(name)
        raw_temp = None
        try:
            if records:
                warnings = renderer.rebuild(source, temp, records)
            else:
                shutil.copy2(source, temp)
                warnings = []
            new_sha = sha256(temp)
            if sha256(source) != source_sha:
                raise RuntimeError('Source PDF changed while building the local mirror; retry.')
            final_records = api.annotations(attachment)
            final_fingerprint = hashlib.sha256(json.dumps(final_records, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            if final_fingerprint != fingerprint:
                raise Conflict('Native annotations changed during mirroring; preserve the baseline and retry.')
            if (sha256(previous_display) if previous_display.exists() else None) != display_actual:
                raise Conflict('The local display PDF changed while generating its replacement.')
            if raw_path:
                if (sha256(previous_raw) if previous_raw.exists() else None) != raw_actual:
                    raise Conflict('The private source body changed while generating its replacement.')
                if raw_actual != source_sha or raw_path != previous_raw:
                    raw_path.parent.mkdir(parents=True, exist_ok=True)
                    fd, name = tempfile.mkstemp(prefix='.' + key + '-source-', suffix='.pdf', dir=raw_path.parent)
                    os.close(fd)
                    raw_temp = Path(name)
                    shutil.copy2(source, raw_temp)
                    if sha256(raw_temp) != source_sha or sha256(source) != source_sha:
                        raise RuntimeError('Source PDF changed during copying; retry.')
                    if source_revision and raw_path.exists():
                        raise Conflict('The new source-body filename is already in use.')
                    if not source_revision:
                        guard(raw_path, raw_actual, source_sha)
                    os.replace(raw_temp, raw_path)
                row['raw_copy_sha256'] = source_sha
            if (sha256(previous_display) if previous_display.exists() else None) != display_actual:
                raise Conflict('The local display PDF changed before replacement.')
            if (source_revision or role_changed) and display.exists():
                raise Conflict('The new mirror filename is already in use.')
            os.replace(temp, display)
            if source_revision or role_changed:
                history = {field: old.get(field) for field in
                           ('version_timestamp', 'version_timezone', 'source_sha256', 'mirror_sha256',
                            'annotation_fingerprint', 'annotations', 'attachment_version', 'filename_role')}
                history['reason'] = 'source_revision' if source_revision else 'annotation_role_transition'
                history['display_pdf'] = preserve_private(previous_display, display_actual, key)
                if source_revision and previous_raw:
                    history['source_pdf'] = preserve_private(previous_raw, raw_actual, key)
                history['preserved_at'] = now()
                row['source_history'] = [*old.get('source_history', []), history]
            row.update(status='updated', source_sha256=source_sha, mirror_sha256=new_sha,
                       display_pdf=relative(display), source_pdf=relative(raw_path) if raw_path else None,
                       source_ownership='project_private_body' if raw_path else 'zotero_managed_source',
                       annotations=records, annotation_fingerprint=fingerprint, native_annotations=len(records),
                       warnings=warnings, error=None, last_success_at=now())
            if source_revision or role_changed or not old.get('version_timestamp'):
                row.update(version_timestamp=saved_at.isoformat(timespec='seconds'), version_timezone='America/New_York')
            row.update(filename_role=role, source_filename_role=source_role)
            return row
        finally:
            temp.unlink(missing_ok=True)
            if raw_temp:
                raw_temp.unlink(missing_ok=True)
    except Conflict as exc:
        row.update(status='conflict', error=str(exc))
    except Exception as exc:
        row.update(status='unavailable', error=str(exc))
    return row


def markdown(value):
    return str(value or '').replace('|', '\\|').replace('\n', ' ')


def write_readme(item, folder, attachments, previous_hash=None, retention=None):
    data = item['data']
    title = markdown(data.get('title', 'Untitled'))
    lines = ['# ' + title, '', '[Open this paper in Zotero](zotero://select/library/items/' + item_key(item) + ')', '']
    if data.get('date'):
        lines.extend(['Published: ' + markdown(data['date']) + '.', ''])
    if data.get('DOI'):
        lines.extend(['DOI: [' + markdown(data['DOI']) + '](https://doi.org/' + data['DOI'] + ').', ''])
    current = next((r for r in attachments if r.get('status') == 'dedicated_mirror'
                    or r.get('mirror_owner') == 'collection' and r.get('asset_kind') == 'explicit_review'
                    or retention and r.get('key') == retention.get('active_attachment_key')), None)
    if current:
        displayed = paper_path(current['display_pdf'])
        lines.extend(['**Current reviewed PDF for VS Code:** [' + markdown(displayed.name) + '](<'
                      + str(displayed.relative_to(folder)) + '>)', '',
                      '[Open the current editable Zotero Reader](zotero://open-pdf/library/items/'
                      + current['key'] + ')', ''])
    lines.extend(['PDF versions use `YYYY-MM-DD_HH-mm-ss_PaperTitle_Role.pdf` in local time '
                  '(America/New_York, 24-hour clock). Source/Annotated suffixes identify distinct attachment assets, including homework, solutions, and chapters. '
                  'An annotation mirror is not a reviewed answer batch. Routine annotation autosaves keep the active filename.', ''])
    if retention:
        lines.extend(['## Retained PDFs', '',
                      'This folder keeps the immutable original, the latest verified review, and the immediately previous verified review. Older derivatives are removed only after the new review and synchronization have been verified.', '',
                      '| Role | PDF |', '| --- | --- |'])
        for role, field in [('Original source', 'original_pdf'), ('Latest review', 'latest_pdf'),
                            ('Previous review', 'previous_pdf')]:
            if retention.get(field):
                path = paper_path(retention[field])
                lines.append('| ' + role + ' | [' + markdown(path.name) + '](<'
                             + str(path.relative_to(folder)) + '>) |')
        roles = retention.get('zotero_attachments', {})
        if roles:
            lines.extend(['', 'The active Zotero PDF attachments use these same original/latest/previous roles. Obsolete PDF attachments are moved to Trash only after verification. Necessary private Reader bodies back these attachments; they are not additional Zotero versions.', ''])
            for role in ('original', 'latest', 'previous'):
                if role in roles:
                    lines.append('[Open '+role+' in Zotero](zotero://open-pdf/library/items/'+roles[role]['attachment_key']+')')
            lines.append('')
        else:
            lines.extend(['', 'Superseded attachment PDFs are not recopied into this folder. The native editable Reader body is a private synchronization file; use the Reader link above to edit annotations.', ''])
    lines.extend(['Local PDFs are pulled from this paper’s Zotero attachments. Native Reader annotations are included in the displayed copies. Local edits are preserved as synchronization conflicts.', '',
                  '| Attachment | Local PDF | Native annotations | Status |',
                  '| --- | --- | ---: | --- |'])
    for row in sorted(attachments, key=lambda x: (x.get('version_timestamp', ''), x['key']), reverse=True):
        pdf = paper_path(row['display_pdf']) if row.get('display_pdf') else None
        link = ('[' + markdown(pdf.name) + '](<' + str(pdf.relative_to(folder)) + '>)' if pdf else
                'Retained in Zotero; not copied locally' if row.get('status') == 'metadata_only' else 'Unavailable')
        lines.append('| ' + markdown(row.get('attachment_title')) + ' | ' + link + ' | ' + str(row.get('native_annotations', '—')) + ' | ' + markdown(row.get('status')) + ' |')
    lines.extend(['', 'Original files and annotations remain in Zotero. This folder is a read-only pull mirror; PDF edits here do not automatically update Zotero.', ''])
    text = '\n'.join(lines)
    path = folder / 'README.md'
    wanted = hashlib.sha256(text.encode()).hexdigest()
    if path.exists():
        actual = sha256(path)
        if actual == wanted:
            return wanted, None
        if not previous_hash or actual != previous_hash:
            return previous_hash, 'README.md was edited locally and has been preserved.'
    folder.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.README-', dir=folder)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
    return wanted, None


def write_collection_index(state):
    """Show automatically discovered collection assets without claiming review."""
    lines = ['# Zotero ECE6420 collection', '',
             '[Open ECE6420 in Zotero](zotero://select/library/collections/' + state['collection_key'] + ')', '',
             'This index mirrors the configured ECE6420 collection and descendants. Distinct PDF attachments '
             '(homework, solutions, articles, or book chapters) remain separate source assets. '
             'Source and annotation mirrors are not completed paper reviews.', '',
             '| Item | Available PDFs | Native annotations |',
             '| --- | ---: | ---: |']
    for key, item in sorted(state.get('items', {}).items(),
                            key=lambda pair: pair[1].get('metadata', {}).get('data', {}).get('title', '').casefold()):
        if not item.get('in_collection'):
            continue
        folder = paper_path(item['folder'])
        title = item.get('metadata', {}).get('data', {}).get('title') or key
        rows = [r for r in state.get('attachments', {}).values()
                if r.get('in_collection') and r.get('parent_item_key') == key]
        available = sum(r.get('status') in ('updated', 'unchanged', 'dedicated_mirror', 'linked_source', 'retained_snapshot')
                        for r in rows)
        count = sum(r.get('native_annotations', 0) for r in rows)
        lines.append('| [' + markdown(title) + '](<' + str(folder.relative_to(PAPERS)) + '/README.md>) | '
                     + str(available) + ' / ' + str(len(rows)) + ' | ' + str(count) + ' |')
    lines.extend(['', 'Reader annotation changes appear after a successful automatic pull. Local mirror edits '
                  'are preserved as conflicts and do not publish to Zotero. File/collection removals do not '
                  'delete local source assets.', ''])
    wanted = '\n'.join(lines)
    path = PAPERS / 'README.md'
    digest = hashlib.sha256(wanted.encode()).hexdigest()
    if path.exists():
        actual = sha256(path)
        if actual == digest:
            return digest, None
        if actual != state.get('index_sha256'):
            return state.get('index_sha256'), 'Collection index was edited locally and has been preserved.'
    PAPERS.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.index-', dir=PAPERS)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(wanted)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
    return digest, None


def summary(state):
    rows = [row for row in state.get('attachments', {}).values() if row.get('in_collection')]
    return {'status': state.get('status'), 'collection': state.get('collection'),
            'papers': len([i for i in state.get('items', {}).values() if i.get('in_collection')]),
            'pdf_attachments': len(rows),
            'available_pdfs': sum(row.get('status') in ('updated', 'unchanged', 'dedicated_mirror', 'linked_source', 'retained_snapshot') for row in rows),
            'native_annotations': sum(row.get('native_annotations', 0) for row in rows),
            'metadata_only_attachments': sum(row.get('status') == 'metadata_only' for row in rows),
            'conflicts': [{'key': r['key'], 'reason': r.get('error')} for r in rows if r.get('status') == 'conflict'],
            'unavailable': [{'key': r['key'], 'reason': r.get('error')} for r in rows if r.get('status') == 'unavailable'],
            'paused': [{'key': r['key'], 'reason': r.get('error')} for r in rows if r.get('status') == 'paused'],
            'warnings': [{'key': r['key'], 'messages': r['warnings']} for r in rows if r.get('warnings')],
            'updated_at': state.get('updated_at'), 'last_success_at': state.get('last_success_at'),
            'error': state.get('error'), 'index_warning': state.get('index_warning'),
            'state': relative(STATE), 'papers_folder': relative(PAPERS), 'index': relative(PAPERS / 'README.md')}


def sync_once(bridge=None, renderer=None):
    bridge = bridge or module('zotero_collection_bridge', 'zotero-mcp.py')
    renderer = renderer or module('zotero_collection_renderer', 'zotero-live-mirror.py')
    retention_tool = module('zotero_collection_retention', 'zotero-retention.py')
    with instance_lock():
        state = load(STATE, {'schema_version': 1, 'items': {}, 'attachments': {}})
        api = LocalAPI(bridge, state.get('server_id'))
        try:
            collection, items = api.inventory()
            if state.get('collection_key') not in (None, collection['key']):
                raise Conflict('Configured collection differs from the saved collection baseline.')
            reader = configured_reader()
            seen_attachments = set()
            state.update(collection=collection['data']['name'], collection_key=collection['key'], server_id=api.server_id,
                         workspace=str(ROOT), version_timezone='America/New_York', zotero_access='read_only',
                         source_asset_policy='Distinct attachments are separate source assets; no inferred review rotation or deletion.',
                         sync_direction='Zotero Reader to local annotated PDF mirror only',
                         publishing='not configured; no Zotero writes')
            for key, item in sorted(items.items()):
                old = state['items'].get(key, {})
                retention = retention_tool.policy(key)
                folder = paper_path(old['folder']) if old.get('folder') else paper_folder(item)
                # The current reader configuration is authoritative after project relocations.
                if reader.get('parent_item_key') == key:
                    if retention:
                        folder = paper_path(retention['paper_folder'])
                    elif reader.get('paper_folder'):
                        folder = paper_path(reader['paper_folder'])
                    else:
                        folder = paper_path(reader['reader_pdf']).parent
                if item['data'].get('itemType') == 'attachment':
                    children = [item]
                else:
                    children = api.all(f'users/0/items/{key}/children')
                pdfs = [i for i in children if i['data'].get('itemType') == 'attachment'
                        and i['data'].get('contentType') == 'application/pdf' and not i['data'].get('deleted')]
                state['items'][key] = {**old, 'metadata': item, 'folder': relative(folder), 'in_collection': True}
                rows = []
                for attachment in pdfs:
                    ak = item_key(attachment)
                    seen_attachments.add(ak)
                    try:
                        # Do not monopolize an explicitly configured dedicated mirror lock
                        # while inventorying the rest of the collection.
                        for attempt in range(4):
                            try:
                                with renderer.transaction():
                                    if (retention and ak != retention['active_attachment_key']
                                            and ak not in retention.get('distinct_source_attachment_keys', [])):
                                        role = next((r for r, v in retention.get('zotero_attachments', {}).items()
                                                     if v['attachment_key'] == ak), None)
                                        if role in ('original', 'previous'):
                                            row = retained_snapshot_attachment(api, attachment, item, folder,
                                                                               state['attachments'].get(ak, {}), retention, role)
                                        else:
                                            row = metadata_only_attachment(api, attachment, item, folder,
                                                                           state['attachments'].get(ak, {}))
                                            if retention.get('zotero_attachments'):
                                                row['warnings'] = ['Unassigned PDF attachment: reconcile with the three-version Zotero retention policy.']
                                    else:
                                        row = sync_attachment(api, renderer, attachment, item, folder,
                                                              state['attachments'].get(ak, {}), reader)
                                break
                            except renderer.Busy:
                                if attempt == 3:
                                    raise
                                time.sleep(0.05)
                    except renderer.Busy as exc:
                        row = dict(state['attachments'].get(ak, {}))
                        row.update(key=ak, parent_item_key=key, paper_folder=relative(folder),
                                   attachment_title=attachment['data'].get('title', ''),
                                   in_collection=True, status='paused', error=str(exc))
                    state['attachments'][ak] = row
                    rows.append(row)
                    atomic_json(STATE, state)
                digest, warning = write_readme(item, folder, rows, old.get('readme_sha256'), retention)
                state['items'][key].update(readme_sha256=digest, warning=warning)
            # Mark departures only after a complete inventory succeeds. Files
            # remain untouched, including PDFs removed from the collection.
            for key, value in state['items'].items():
                value['in_collection'] = key in items
            for key, value in state['attachments'].items():
                value['in_collection'] = key in seen_attachments
            digest, warning = write_collection_index(state)
            state.update(index_sha256=digest, index_warning=warning)
            bad = [r for r in state['attachments'].values() if r.get('in_collection') and r.get('status') in ('conflict', 'unavailable', 'paused')]
            state.update(status='partial' if bad else 'healthy', error=None, updated_at=now())
            if not bad:
                state['last_success_at'] = now()
        except Exception as exc:
            state.update(status='error', error=str(exc), updated_at=now())
        atomic_json(STATE, state)
        return summary(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--once', action='store_true', help='Pull the complete collection once (the default).')
    mode.add_argument('--watch', action='store_true', help='Repeat scoped pulls until stopped.')
    mode.add_argument('--status', action='store_true', help='Read the last recorded synchronization status.')
    parser.add_argument('--interval', type=float, default=5, help='Watch interval in seconds, minimum 1 (default 5).')
    args = parser.parse_args()
    if args.interval < 1 or not args.interval < float('inf'):
        parser.error('--interval must be finite and at least one second.')
    if args.status:
        print(json.dumps(summary(load(STATE, {})), ensure_ascii=False, indent=2))
        return 0
    stopping = threading.Event()
    if args.watch:
        signal.signal(signal.SIGTERM, lambda _signum, _frame: stopping.set())
    previous = None
    while True:
        try:
            result = sync_once()
        except Exception as exc:
            result = {'status': 'paused', 'error': str(exc)}
        message = json.dumps(result, ensure_ascii=False, sort_keys=True)
        # Healthy polling does not print a new line just because its timestamp changes.
        signature = json.dumps({k: v for k, v in result.items() if k not in ('updated_at', 'last_success_at')}, sort_keys=True)
        if signature != previous or not args.watch:
            print(message, flush=True)
            previous = signature
        if not args.watch:
            return 0 if result.get('status') == 'healthy' else 1
        if stopping.wait(args.interval):
            return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
