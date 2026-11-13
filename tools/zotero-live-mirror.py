#!/usr/bin/env python3
"""Mirror project-scoped Zotero reader annotations into a local PDF; GET requests only."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
from urllib.parse import unquote, urlparse
from urllib.request import Request
import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local/zotero'
CONFIG = LOCAL / 'reader-sync.json'
STATE = LOCAL / 'sync-state.json'
LOCK = LOCAL / 'publish.lock'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def workspace_path(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Configured paths must remain inside the project.')
    return path


def relative(path):
    return str(path.relative_to(ROOT))


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def save_json(path, data):
    path = workspace_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    imported = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(imported)
    return imported


class Busy(RuntimeError):
    pass


@contextmanager
def transaction(lock=LOCK):
    lock = workspace_path(lock)
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise Busy('Paused while another mirror pull or publisher holds the lock.') from exc
    try:
        yield
    finally:
        lock.rmdir()


def configuration(path=CONFIG):
    config = read_json(workspace_path(path))
    if not isinstance(config, dict) or not re.fullmatch(r'[A-Z0-9]{8}', config.get('attachment_key', '')):
        raise ValueError('Configure an actual Zotero attachment_key in reader-sync.json.')
    reader, mirror = (workspace_path(config[k]) for k in ('reader_pdf', 'mirror_pdf'))
    if reader == mirror or reader.suffix.lower() != '.pdf' or mirror.suffix.lower() != '.pdf':
        raise ValueError('Reader and mirror must be different project-local PDF paths.')
    interval = float(config.get('poll_seconds', 1))
    if not math.isfinite(interval) or interval < 0.25:
        raise ValueError('poll_seconds must be finite and at least 0.25.')
    return config


def startup_scope(bridge, config):
    key = config['attachment_key']
    item = bridge.allowed_item(key)
    data = item['data']
    if data.get('itemType') != 'attachment' or data.get('contentType') != 'application/pdf':
        raise ValueError('The configured project item is not a PDF attachment.')
    if data.get('parentItem') != config.get('parent_item_key'):
        raise ValueError('The reader attachment must belong to the configured bibliographic paper.')
    uri = urlparse(bridge.get(f'users/0/items/{key}/file/view/url', text=True).strip())
    if uri.scheme != 'file' or uri.netloc not in ('', 'localhost') or Path(unquote(uri.path)).resolve() != workspace_path(config['reader_pdf']):
        raise ValueError('The Zotero attachment does not link to the configured reader PDF.')


def fetch_annotations(bridge, config, expected_server=None):
    headers = {'Zotero-API-Version': '3', 'Accept': 'application/json'}
    if expected_server:
        headers['Zotero-Server-ID'] = expected_server
    request = Request(bridge.BASE + f"users/0/items/{config['attachment_key']}/children?itemType=annotation&format=json", headers=headers)
    with bridge.OPENER.open(request, timeout=20) as response:
        identity = response.headers.get('Zotero-Server-ID')
        if not identity:
            raise RuntimeError('Zotero 10+ server identity is required for version-safe mirroring.')
        raw = json.loads(response.read().decode('utf-8'))
    if not isinstance(raw, list):
        raise ValueError('Zotero did not return an annotation list.')
    records = {item['key']: item for item in raw
               if item['data'].get('itemType') == 'annotation' and not item['data'].get('deleted')}
    if any(item['data'].get('parentItem') != config['attachment_key'] for item in records.values()):
        raise ValueError('Zotero returned an annotation for another attachment.')
    return identity, records


def color(value):
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', value or ''):
        return (1, 1, 0)
    return tuple(int(value[i:i+2], 16) / 255 for i in (1, 3, 5))


def converted_rect(page, coordinates):
    if len(coordinates) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in coordinates):
        raise ValueError('Invalid annotation rectangle.')
    # Zotero uses PDF user space. This matrix accounts for crop/media origins and Y direction.
    rect = fitz.Rect(coordinates) * page.transformation_matrix
    if rect.is_empty or rect.is_infinite:
        raise ValueError('Empty annotation rectangle.')
    return rect


def converted_paths(page, paths):
    """Convert Zotero pen strokes from PDF user space to PyMuPDF coordinates."""
    if not isinstance(paths, list) or not paths:
        raise ValueError('Ink annotation has no paths.')
    result = []
    for path in paths:
        if (not isinstance(path, list) or len(path) < 2 or len(path) % 2
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                           and math.isfinite(v) for v in path)):
            raise ValueError('Invalid ink annotation path.')
        result.append([tuple(fitz.Point(path[i], path[i + 1]) * page.transformation_matrix)
                       for i in range(0, len(path), 2)])
    return result


def renderable(data):
    kind = data.get('annotationType')
    if kind in ('highlight', 'underline', 'note', 'ink', 'image'):
        return True
    if kind == 'text':
        position = json.loads(data['annotationPosition'])
        return not position.get('rotation', 0) % 90 and data.get('annotationComment', '').isascii()
    return False


def rebuild(reader, destination, records):
    warnings = []
    with fitz.open(reader) as document:
        if not document.is_pdf:
            raise ValueError('Reader source must be a PDF.')
        links_before = [page.get_links() for page in document]
        for page in document:
            for annotation in list(page.annots() or []):
                key = annotation.info.get('id', '').removeprefix('Zotero-')
                if key in records and renderable(records[key]['data']):
                    page.delete_annot(annotation)
                else:
                    annotation.set_flags(annotation.flags & ~(64 | 128 | 512))
        for key, item in sorted(records.items()):
            if not re.fullmatch(r'[A-Z0-9]{8}', key):
                raise ValueError('Invalid Zotero annotation key.')
            data = item['data']
            kind = data.get('annotationType')
            if kind not in ('highlight', 'underline', 'note', 'text', 'ink', 'image'):
                warnings.append(f'{key}: unsupported native {kind}; any existing base-PDF annotation was retained.')
                continue
            position = json.loads(data['annotationPosition'])
            index = position['pageIndex']
            if not isinstance(index, int) or not 0 <= index < len(document):
                raise ValueError(f'{key}: annotation page is outside the reader PDF.')
            page = document[index]
            rects = [converted_rect(page, coords) for coords in position.get('rects', [])]
            if not rects and kind != 'ink':
                raise ValueError(f'{key}: annotation has no rectangle.')
            comment = data.get('annotationComment', '')
            rgb = color(data.get('annotationColor'))
            if kind == 'highlight':
                annotation = page.add_highlight_annot([fitz.Quad(rect.tl, rect.tr, rect.bl, rect.br) for rect in rects])
            elif kind == 'underline':
                annotation = page.add_underline_annot([fitz.Quad(rect.tl, rect.tr, rect.bl, rect.br) for rect in rects])
            elif kind == 'note':
                annotation = page.add_text_annot(rects[0].tl, comment)
            elif kind == 'ink':
                paths = converted_paths(page, position.get('paths'))
                width = position.get('width', 1)
                if (not isinstance(width, (int, float)) or isinstance(width, bool)
                        or not math.isfinite(width) or width <= 0):
                    raise ValueError(f'{key}: invalid ink stroke width.')
                annotation = page.add_ink_annot(paths)
                matrix = page.transformation_matrix
                annotation.set_border(width=width * math.hypot(matrix.a, matrix.b))
            elif kind == 'image':
                region = fitz.Rect(rects[0])
                for rect in rects[1:]:
                    region |= rect
                annotation = page.add_rect_annot(region)
                warnings.append(f'{key}: image annotation is shown as its selected region; the page content is unchanged.')
            else:
                rotation = position.get('rotation', 0)
                if rotation % 90 or not comment.isascii():
                    warnings.append(f'{key}: free-text font/rotation requires a renderer not supported by this mirror.')
                    continue
                annotation = page.add_freetext_annot(rects[0], comment, fontsize=position.get('fontSize', 11),
                                                     text_color=rgb, rotate=rotation % 360)
            annotation.set_info(content=comment, title=data.get('annotationAuthorName', ''))
            if kind != 'text':
                annotation.set_colors(stroke=rgb)
            annotation.set_opacity(0.35 if kind == 'highlight' else 1)
            annotation.set_flags(4)  # Print only: never PDF ReadOnly, Locked, or LockedContents.
            annotation.update()
            document.xref_set_key(annotation.xref, 'NM', fitz.get_pdf_str('Zotero-' + key))
            if kind == 'note':
                annotation.set_rect(rects[0])
        document.save(destination, garbage=3, deflate=True)
    with fitz.open(destination) as result:
        if len(result) != len(links_before):
            raise RuntimeError('Page count changed while generating the mirror.')
        def comparable(link):
            return {k: v for k, v in link.items() if k not in ('xref', 'id')}
        for page, old in zip(result, links_before):
            if [comparable(x) for x in page.get_links()] != [comparable(x) for x in old]:
                raise RuntimeError('A source hyperlink changed while generating the mirror.')
            if any(a.flags & (64 | 128 | 512) for a in page.annots() or []):
                raise RuntimeError('Unexpected locked/read-only annotation in generated mirror.')
    return warnings


def pull_once(config, fetch, snapshot, state_path=STATE, lock_path=LOCK):
    reader, mirror = (workspace_path(config[k]) for k in ('reader_pdf', 'mirror_pdf'))
    state_path = workspace_path(state_path)
    with transaction(lock_path):
        state = read_json(state_path, {})
        try:
            expected = state.get('mirror_sha256')
            actual = sha256(mirror) if mirror.exists() else None
            if expected and actual != expected:
                state.update(status='conflict', error='Mirror changed outside the last pull. Publish or resolve it before pulling.',
                             observed_mirror_sha256=actual, updated_at=now())
                save_json(state_path, state)
                return state
            if state.get('attachment_key') not in (None, config['attachment_key']):
                raise RuntimeError('Attachment differs from the existing sync baseline; resolve the configuration explicitly.')
            reader_sha = sha256(reader)
            identity, records = fetch(state.get('server_id'))
            if state.get('server_id') not in (None, identity):
                raise RuntimeError('Zotero server identity changed; resolve the previous baseline before pulling.')
            if sha256(reader) != reader_sha:
                raise RuntimeError('Reader PDF changed while fetching annotations; retrying on the next poll.')
            fingerprint = hashlib.sha256(json.dumps(records, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if not state.get('force_pull') and expected and state.get('annotation_fingerprint') == fingerprint and state.get('reader_sha256') == reader_sha:
                if state.get('status') != 'unchanged' or state.get('error'):
                    state.update(status='unchanged', error=None, updated_at=now())
                    save_json(state_path, state)
                return state
            mirror.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.' + mirror.stem + '-', suffix='.pdf', dir=mirror.parent)
            os.close(fd)
            temp = Path(name)
            try:
                warnings = rebuild(reader, temp, records)
                geometry = snapshot(temp)['geometry']
                if sha256(reader) != reader_sha:
                    raise RuntimeError('Reader PDF changed during the pull; retrying on the next poll.')
                if (sha256(mirror) if mirror.exists() else None) != actual:
                    raise RuntimeError('Mirror was edited during generation; preserving that edit.')
                if not state.get('mirror_backup') and mirror.exists():
                    folder = LOCAL / 'mirror-backups'
                    folder.mkdir(parents=True, exist_ok=True)
                    backup = folder / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-') + mirror.name)
                    shutil.copy2(mirror, backup)
                    state['mirror_backup'] = relative(backup)
                new_hash = sha256(temp)
                os.replace(temp, mirror)
                state.update(schema_version=1, attachment_key=config['attachment_key'], reader_pdf=relative(reader),
                             mirror_pdf=relative(mirror), mirror_sha256=new_hash, reader_sha256=reader_sha,
                             server_id=identity, annotation_fingerprint=fingerprint,
                             annotation_versions={k: v.get('version', v['data'].get('version')) for k, v in records.items()},
                             annotations=records, mirror_geometry=geometry, status='updated', error=None,
                             warnings=warnings, force_pull=False, updated_at=now(), last_success_at=now())
                state.pop('observed_mirror_sha256', None)
                save_json(state_path, state)
                return state
            finally:
                temp.unlink(missing_ok=True)
        except Exception as error:
            state.update(status='error', error=str(error), updated_at=now())
            save_json(state_path, state)
            return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(CONFIG))
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    bridge = module('zotero_live_mirror_bridge', 'zotero-mcp.py')
    publisher = module('zotero_mirror_snapshot', 'zotero-publish.py')
    checked_config = None
    previous_message = None
    while True:
        interval = 1
        try:
            config = configuration(args.config)
            interval = float(config.get('poll_seconds', 1))
            if config != checked_config:
                startup_scope(bridge, config)
                checked_config = dict(config)
            state = pull_once(config, lambda identity: fetch_annotations(bridge, config, identity), publisher.pdf_snapshot)
            message = json.dumps({k: state.get(k) for k in ('status', 'error', 'warnings')}, ensure_ascii=False)
        except Busy as error:
            message = json.dumps({'status': 'paused', 'error': str(error)})
        except Exception as error:
            message = json.dumps({'status': 'error', 'error': str(error)})
        if message != previous_message:
            print(now(), message, flush=True)
            previous_message = message
        if args.once:
            return 1 if json.loads(message).get('status') in ('error', 'conflict') else 0
        time.sleep(interval)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
