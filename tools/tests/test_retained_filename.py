"""A saved managed review keeps its filename on later native note autosaves."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from test_collection_review_reader import sync, FakeAPI, FakeRenderer


class RetainedFilenameTests(unittest.TestCase):
    def test_managed_latest_note_autosave_keeps_published_mirror(self):
        base = Path(__file__).resolve().parents[2] / '.local/test'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory:
            root = Path(directory)
            paper = root / 'docs/zotero/papers/LN'
            paper.mkdir(parents=True)
            local = root / '.local/zotero'
            source = root / 'managed.pdf'
            source.write_bytes(b'source body')
            records = {'ANNOT001': {'key': 'ANNOT001', 'version': 1, 'data': {'annotationComment': 'first'}}}
            api, renderer = FakeAPI(source, records), FakeRenderer()
            parent = {'key': 'PARENT01', 'data': {'title': 'LN'}}
            attachment = {'key': 'LATEST01', 'data': {'linkMode': 'imported_file', 'title': 'LN'}}
            with patch.multiple(sync, ROOT=root, PAPERS=root/'docs/zotero/papers', LOCAL=local,
                                SOURCE_BODIES=local/'source-bodies', SOURCE_HISTORY=local/'source-history'):
                first = sync.sync_attachment(api, renderer, attachment, parent, paper, {}, {})
                self.assertEqual(first['status'], 'updated')
                published = paper / '2026-11-09_04-30-43_LN_Reviewed_EN_Annotated.pdf'
                (root/first['display_pdf']).rename(published)
                first.update(display_pdf=sync.relative(published), filename_role='Reviewed_EN_Annotated',
                             retained_role='latest')
                api.records = {'ANNOT001': {'key': 'ANNOT001', 'version': 2, 'data': {'annotationComment': 'updated'}}}
                second = sync.sync_attachment(api, renderer, attachment, parent, paper, first, {})
                self.assertEqual(second['status'], 'updated')
                self.assertEqual(second['display_pdf'], first['display_pdf'])
                self.assertEqual(second['filename_role'], 'Reviewed_EN_Annotated')
                self.assertEqual(len(list(paper.glob('*.pdf'))), 1)
                self.assertFalse((local/'source-history').exists())


if __name__ == '__main__':
    unittest.main()
