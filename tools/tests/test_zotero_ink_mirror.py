"""Regression checks for native pen strokes in the local PDF mirror."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ink_mirror', ROOT / 'tools/zotero-live-mirror.py')
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)


class InkMirrorTests(unittest.TestCase):
    def test_ink_coordinates_comments_and_navigation_survive_rebuild(self):
        temp_root = ROOT / '.local/test'
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as directory:
            source, output, second = (Path(directory) / name for name in ('source.pdf', 'mirror.pdf', 'second.pdf'))
            doc = fitz.open()
            page = doc.new_page(width=400, height=300)
            page.insert_text((40, 40), 'Source body remains unchanged.')
            page.set_cropbox(fitz.Rect(20, 10, 380, 290))
            page.insert_link({'kind': fitz.LINK_URI, 'from': fitz.Rect(40, 40, 120, 60), 'uri': 'https://example.com/'})
            doc.set_toc([[1, 'Original chapter', 1]])
            doc.save(source)
            doc.close()
            record = {'INK12345': {'key': 'INK12345', 'data': {
                'annotationType': 'ink', 'annotationColor': '#2ea8e5',
                'annotationComment': '한글 메모: Δf = 2π; café',
                'annotationAuthorName': 'Reader',
                'annotationPosition': json.dumps({'pageIndex': 0, 'width': 2.5,
                    'paths': [[50, 70, 80, 100, 110, 70], [150, 170, 160, 180]]})}}}
            self.assertEqual(mirror.rebuild(source, output, record), [])
            self.assertEqual(mirror.rebuild(output, second, record), [])
            with fitz.open(source) as original, fitz.open(second) as result:
                page = result[0]
                annotations = list(page.annots())
                self.assertEqual(len(annotations), 1)
                annotation = annotations[0]
                self.assertEqual(annotation.type[1], 'Ink')
                self.assertEqual(annotation.info['id'], 'Zotero-INK12345')
                self.assertEqual(annotation.info['content'], record['INK12345']['data']['annotationComment'])
                self.assertEqual(annotation.flags, 4)
                self.assertAlmostEqual(annotation.border['width'], 2.5)
                expected = [[tuple(fitz.Point(x, y) * original[0].transformation_matrix)
                             for x, y in [(50, 70), (80, 100), (110, 70)]],
                            [tuple(fitz.Point(x, y) * original[0].transformation_matrix)
                             for x, y in [(150, 170), (160, 180)]]]
                self.assertEqual(annotation.vertices, expected)
                for actual, wanted in zip(annotation.colors['stroke'], mirror.color('#2ea8e5')):
                    self.assertAlmostEqual(actual, wanted, places=5)
                self.assertEqual(page.get_text(), original[0].get_text())
                self.assertEqual(result.get_toc(), original.get_toc())
                self.assertEqual(page.get_links()[0]['uri'], original[0].get_links()[0]['uri'])

    def test_invalid_paths_fail_without_silent_loss(self):
        doc = fitz.open()
        page = doc.new_page(width=200, height=100)
        for paths in (None, [], [[1, 2, 3]], [[float('nan'), 1]], [['x', 1]]):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                mirror.converted_paths(page, paths)
        doc.close()


if __name__ == '__main__':
    unittest.main()
