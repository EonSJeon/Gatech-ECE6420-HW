"""Fake-API checks for a collection-owned linked review and retained original."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('review_collection', ROOT / 'tools/zotero-collection-sync.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def fingerprint(records):
    return hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class FakeAPI:
    def __init__(self, source, records):
        self.path = source
        self.records = records

    def source(self, attachment):
        return self.path

    def annotations(self, attachment):
        return self.records


class FakeRenderer:
    def __init__(self):
        self.calls = 0

    def rebuild(self, source, destination, records):
        self.calls += 1
        destination.write_bytes(source.read_bytes() + json.dumps(records, sort_keys=True).encode())
        return []


class CollectionReviewReaderTests(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / '.local/test'
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / 'workspace'
        self.local = self.root / '.local/zotero'
        self.papers = self.root / 'docs/zotero/papers'
        self.paper = self.papers / 'Book_PARENT01'
        self.paper.mkdir(parents=True)
        self.source = self.local / 'readers/ch14/2026-11-09_11-00-00_Book_Reviewed_EN_Reader.pdf'
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'accepted immutable reader body')
        self.display = self.paper / '2026-11-09_11-00-00_Book_Reviewed_EN_Annotated.pdf'
        self.patch = patch.multiple(sync, ROOT=self.root, PAPERS=self.papers, LOCAL=self.local,
                                    SOURCE_BODIES=self.local / 'source-bodies',
                                    SOURCE_HISTORY=self.local / 'source-history')
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.parent = {'key': 'PARENT01', 'data': {'title': 'Book'}}
        self.attachment = {'key': 'LATEST01', 'version': 1,
                           'data': {'linkMode': 'linked_file', 'title': 'Chapter 14 linked review'}}
        self.records = {'ANNOT001': {'key': 'ANNOT001', 'version': 4,
                                    'data': {'annotationType': 'highlight', 'annotationComment': 'Saved question'}}}
        self.api = FakeAPI(self.source, self.records)
        self.renderer = FakeRenderer()
        self.reader = {'mirror_owner': 'collection', 'attachment_key': 'LATEST01',
                       'parent_item_key': 'PARENT01', 'reader_pdf': sync.relative(self.source),
                       'mirror_pdf': sync.relative(self.display), 'paper_folder': sync.relative(self.paper),
                       'reader_sha256': sync.sha256(self.source),
                       'version_timestamp': '2026-11-09T11:00:00-05:00'}

    def pull(self, old=None):
        return sync.sync_attachment(self.api, self.renderer, self.attachment, self.parent,
                                    self.paper, old or {}, self.reader)

    def test_linked_reader_updates_only_same_mirror_and_unchanged_poll_creates_nothing(self):
        source_before = (self.source.read_bytes(), self.source.stat().st_mtime_ns)
        first = self.pull()
        self.assertEqual(first['status'], 'updated')
        self.assertEqual(first['source_ownership'], 'zotero_linked')
        self.assertEqual(first['source_pdf'], self.reader['reader_pdf'])
        self.assertEqual(self.renderer.calls, 1)
        paths = set(self.root.rglob('*'))
        mirror_before = (self.display.read_bytes(), self.display.stat().st_mtime_ns)
        second = self.pull(first)
        self.assertEqual(second['status'], 'unchanged')
        self.assertEqual(self.renderer.calls, 1)
        self.assertEqual(paths, set(self.root.rglob('*')))
        self.assertEqual(mirror_before, (self.display.read_bytes(), self.display.stat().st_mtime_ns))
        self.assertEqual(source_before, (self.source.read_bytes(), self.source.stat().st_mtime_ns))
        self.assertFalse((self.local / 'source-bodies').exists())
        self.assertFalse((self.local / 'source-history').exists())
        state = json.loads((self.local / 'sync-state.json').read_text())
        self.assertEqual(state['reader_sha256'], self.reader['reader_sha256'])
        self.assertEqual(state['mirror_sha256'], sync.sha256(self.display))
        self.assertEqual(state['annotations'], self.records)
        self.assertEqual(state['mirror_owner'], 'collection')

        self.api.records = {**self.records, 'ANNOT002': {'key': 'ANNOT002', 'version': 5,
                            'data': {'annotationType': 'note', 'annotationComment': 'New note'}}}
        third = self.pull(second)
        self.assertEqual(third['status'], 'updated')
        self.assertEqual(third['display_pdf'], first['display_pdf'])
        self.assertEqual(third['source_sha256'], first['source_sha256'])
        self.assertEqual(set(third['annotations']), {'ANNOT001', 'ANNOT002'})
        self.assertEqual(source_before, (self.source.read_bytes(), self.source.stat().st_mtime_ns))

    def test_changed_raw_or_local_mirror_is_preserved_as_conflict(self):
        first = self.pull()
        mirror_before = self.display.read_bytes()
        self.source.write_bytes(b'unverified structural edit')
        self.assertEqual(self.pull(first)['status'], 'conflict')
        self.assertEqual(self.display.read_bytes(), mirror_before)
        self.source.write_bytes(b'accepted immutable reader body')
        self.display.write_bytes(b'local mirror edit')
        self.assertEqual(self.pull(first)['status'], 'conflict')
        self.assertEqual(self.display.read_bytes(), b'local mirror edit')

    def test_retained_managed_original_uses_api_source_and_rejects_changed_annotations(self):
        managed = self.root.parent / 'fake-managed/original.pdf'
        managed.parent.mkdir()
        managed.write_bytes(b'original article body')
        original = self.paper / '2026-11-09_10-00-00_Book_Original_Source.pdf'
        original.write_bytes(managed.read_bytes())
        attachment = {'key': 'ORIGIN01', 'version': 1, 'data': {'linkMode': 'imported_file', 'title': 'Original'}}
        api = FakeAPI(managed, self.records)
        accepted = {'attachment_key': 'ORIGIN01', 'source_ownership': 'zotero_managed_source',
                    'source_path': str(managed), 'reader_sha256': sync.sha256(managed),
                    'annotation_fingerprint': fingerprint(self.records)}
        policy = {'original_pdf': sync.relative(original),
                  'snapshots': {'original': {'sha256': sync.sha256(original)}},
                  'zotero_attachments': {'original': accepted}}
        before = (managed.read_bytes(), original.read_bytes(), managed.stat().st_mtime_ns, original.stat().st_mtime_ns)
        row = sync.retained_snapshot_attachment(api, attachment, self.parent, self.paper, {}, policy, 'original')
        self.assertEqual(row['status'], 'retained_snapshot')
        self.assertIsNone(row['source_pdf'])
        self.assertEqual(row['source_zotero_path'], str(managed))
        api.records = {}
        changed = sync.retained_snapshot_attachment(api, attachment, self.parent, self.paper, row, policy, 'original')
        self.assertEqual(changed['status'], 'conflict')
        self.assertIn('Native annotations', changed['error'])
        self.assertEqual(before, (managed.read_bytes(), original.read_bytes(), managed.stat().st_mtime_ns, original.stat().st_mtime_ns))


if __name__ == '__main__':
    unittest.main()
