#!/usr/bin/env python3
"""Add internal navigation links originating only in Razavi Chapter 14.

This creates an unpublished candidate from the unannotated original source body.
It performs no Zotero writes and adds no answers, notes, colors, or page content.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import pymupdf as fitz

CHAPTER_FIRST = 594
CHAPTER_LAST = 624
PARENT = 'XEVWM2L3'
ATTACHMENT = 'S3G7I8KI'
LOCAL_TZ = ZoneInfo('America/New_York')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    if isinstance(value, fitz.Point):
        return [round(value.x, 5), round(value.y, 5)]
    if isinstance(value, fitz.Rect):
        return [round(v, 5) for v in value]
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(v) for v in value]
    return value


def fingerprint(value):
    return hashlib.sha256(json.dumps(canonical(value), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalized(value):
    return re.sub(r'\s+', '', value)


def slug(value):
    return re.sub(r'[^A-Za-z0-9]+', '_', value).strip('_')


def span_rows(page):
    """Merge adjacent identically styled fragments of one printed label."""
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            runs = []
            for span in line['spans']:
                if runs and (runs[-1]['font'], runs[-1]['size']) == (span['font'], span['size']):
                    runs[-1]['text'] += span['text']
                    runs[-1]['bbox'] = tuple(fitz.Rect(runs[-1]['bbox']) | fitz.Rect(span['bbox']))
                else:
                    runs.append(dict(span))
            yield from runs


def flattened(page):
    """Return text with character boxes and explicit line boundaries."""
    chars, boxes, lines = [], [], []
    for block in page.get_text('rawdict')['blocks']:
        for line in block.get('lines', []):
            line_id = len(lines)
            start = len(chars)
            for span in line['spans']:
                for char in span['chars']:
                    chars.append(char['c'])
                    boxes.append((list(char['bbox']), line_id))
            lines.append((start, len(chars), list(line['bbox'])))
            chars.append('\n')
            boxes.append(None)
    return ''.join(chars), boxes, lines


def target(page, kind, identifier, bbox, text, evidence):
    bbox = list(bbox)
    return {'id': kind + ':' + identifier, 'kind': kind, 'identifier': identifier,
            'index0': page.number, 'physical_page': page.number + 1, 'printed_label': page.get_label(),
            'label_bbox': bbox, 'label_text': text, 'evidence': evidence,
            'point': [0, max(0, bbox[1] - 12)]}


def inventory(document):
    targets = {}
    eq_candidates = defaultdict(list)
    for page in document:
        words = page.get_text('words')
        groups = defaultdict(list)
        for word in words:
            groups[(word[5], word[6])].append(word)
        for words_in_line in groups.values():
            if len(words_in_line) != 1:
                continue
            word = words_in_line[0]
            match = re.fullmatch(r'\((\d+\.\d+)\)', word[4])
            if match and word[0] > 440:
                eq_candidates[match[1]].append(target(page, 'equation', match[1], word[:4], word[4],
                                                     'Isolated right-aligned printed equation label.'))
        for span in span_rows(page):
            text = span['text'].strip()
            if 'Bold' in span['font']:
                match = re.fullmatch(r'Figure\s+(\d+\.\d+)', text)
                if match:
                    key = 'figure:' + match[1]
                    if key in targets:
                        raise ValueError('Duplicate figure caption ' + key)
                    targets[key] = target(page, 'figure', match[1], span['bbox'], text,
                                          'Exact bold figure caption label; prose references excluded.')
                match = re.fullmatch(r'Table\s+(\d+\.\d+)', text)
                if match:
                    targets['table:' + match[1]] = target(page, 'table', match[1], span['bbox'], text,
                                                         'Exact bold table caption label.')
                match = re.fullmatch(r'Example\s*(\d+\.\d+)', text)
                if match:
                    targets['example:' + match[1]] = target(page, 'example', match[1], span['bbox'], text,
                                                           'Exact bold example heading.')
            if CHAPTER_FIRST <= page.number <= CHAPTER_LAST and 'Optima-Bold' in span['font']:
                match = re.match(r'^(14\.\d+(?:\.\d+)?)\b', text)
                if match:
                    key = 'section:' + match[1]
                    if key in targets:
                        raise ValueError('Duplicate section heading ' + key)
                    targets[key] = target(page, 'section', match[1], span['bbox'], text,
                                          'Exact numbered bold section heading.')
    required_equations = ['2.1'] + ['14.' + str(n) for n in range(1, 101)]
    for identifier in required_equations:
        values = eq_candidates[identifier]
        if len(values) != 1:
            raise ValueError('Expected one equation definition for ' + identifier + '; found ' + str(len(values)))
        targets['equation:' + identifier] = values[0]
    for level, title, physical in document.get_toc():
        match = re.match(r'^(\d+)\s+', title) if level == 1 else None
        if match:
            page = document[physical - 1]
            value = target(page, 'chapter', match[1], [0, 0, page.rect.width, 150], title,
                           'Existing top-level chapter bookmark and matching chapter-opening page.')
            value['point'] = [0, 0]
            targets[value['id']] = value
    references_page = document[622]
    for word in references_page.get_text('words'):
        match = re.fullmatch(r'\[([1-5])\]', word[4])
        if match and word[1] > 500 and word[0] < 110:
            value = target(references_page, 'citation', match[1], word[:4], word[4],
                           'Numbered Chapter 14 bibliography entry under References.')
            targets[value['id']] = value
    assert all('figure:14.' + str(n) in targets for n in range(1, 43))
    assert all('citation:' + str(n) in targets for n in range(1, 6))
    assert sum(key.startswith('section:14.') for key in targets) == 12
    return targets


def rect_parts(text, boxes, start, end):
    groups = defaultdict(list)
    for i in range(start, end):
        if boxes[i] and not text[i].isspace():
            groups[boxes[i][1]].append(i)
    for positions in groups.values():
        box = fitz.Rect(boxes[positions[0]][0])
        for i in positions[1:]:
            box |= fitz.Rect(boxes[i][0])
        a, b = positions[0], positions[-1] + 1
        yield list(box), text[a:b]


def build_plan(document, targets):
    links, unresolved = [], []
    seen = set()
    source_references = Counter()
    for index in range(CHAPTER_FIRST, CHAPTER_LAST + 1):
        page = document[index]
        text, boxes, lines = flattened(page)
        page_links = []

        def add(kind, identifier, start, end, context):
            entity = kind + ':' + identifier
            parts = list(rect_parts(text, boxes, start, end))
            if not parts:
                return
            # Running page headers are not body references.
            if all(rect[1] < 60 for rect, _ in parts):
                return
            destination = targets.get(entity)
            if destination is None:
                unresolved.append({'physical_page': index + 1, 'printed_label': page.get_label(),
                                   'kind': kind, 'identifier': identifier, 'source_text': text[start:end],
                                   'rects': [rect for rect, _ in parts], 'reason': 'No exact, unambiguous printed target.',
                                   'context': context})
                return
            # A definition label is a destination, not a reference to itself.
            if destination['index0'] == index:
                db = fitz.Rect(destination['label_bbox'])
                if all((fitz.Rect(rect) & db).get_area() / max(1, fitz.Rect(rect).get_area()) > .8 for rect, _ in parts):
                    return
            source_references[kind] += 1
            for rect, anchor in parts:
                signature = (index, tuple(round(v, 3) for v in rect), entity)
                if signature in seen:
                    continue
                seen.add(signature)
                record = {'physical_page': index + 1, 'index0': index, 'printed_label': page.get_label(),
                          'kind': kind, 'source_text': anchor, 'source_rect': rect, 'context': context,
                          'target_id': entity, 'target_index0': destination['index0'],
                          'target_physical_page': destination['physical_page'], 'target_point': destination['point'],
                          'target_label_bbox': destination['label_bbox'], 'target_label_text': destination['label_text']}
                links.append(record)
                page_links.append(record)

        def context(match):
            return re.sub(r'\s+', ' ', text[max(0, match.start() - 55):match.end() + 85]).strip()

        # Equation references: a parenthesized number is distinct from figures and citations.
        for match in re.finditer(r'\((\d+\.\d+)\)', text):
            add('equation', match[1], match.start(), match.end(), context(match))
        for match in re.finditer(r'\bEquation\s+(\d+\.\d+)\b', text):
            add('equation', match[1], match.start(), match.end(), context(match))
        for kind, pattern in [
            ('figure', r'\b(?:Figs?\.|Figures?)\s+(\d+\.\d+)(?:\([a-z]\))?'),
            ('table', r'\bTables?\s+(\d+\.\d+)'),
            ('section', r'\b(?:Secs?\.|Sections?)\s+(\d+\.\d+(?:\.\d+)?)'),
            ('example', r'\bExample\s*(\d+\.\d+)'),
            ('problem', r'\bProblems?\s+(\d+(?:\.\d+)+)')]:
            for match in re.finditer(pattern, text):
                add(kind, match[1], match.start(), match.end(), context(match))
        for match in re.finditer(r'\b(?:Chapter|Chap-\s*ter)\s+(\d+)\b', text):
            add('chapter', match[1], match.start(), match.end(), context(match))
        for match in re.finditer(r'\bChapters\s+(\d+)\s+and\s+(\d+)\b', text):
            for group in (1, 2):
                add('chapter', match[group], match.start(group), match.end(group), context(match))
        for match in re.finditer(r'\[(\d+(?:\s*,\s*\d+)*)\]', text):
            if ',' not in match[1]:
                add('citation', match[1], match.start(), match.end(), context(match))
            else:
                for number in re.finditer(r'\d+', match[1]):
                    start = match.start(1) + number.start()
                    add('citation', number[0], start, start + len(number[0]), context(match))
        for i, left in enumerate(page_links):
            for right in page_links[i + 1:]:
                overlap = (fitz.Rect(left['source_rect']) & fitz.Rect(right['source_rect'])).get_area()
                if overlap > 0.3 and left['target_id'] != right['target_id']:
                    raise ValueError('Overlapping anchors point to different targets: ' + str((left, right)))
    return links, unresolved, dict(source_references)


def page_body(document):
    return [[{'xref': xref, 'raw_sha256': hashlib.sha256(document.xref_stream_raw(xref)).hexdigest(),
              'decoded_sha256': hashlib.sha256(document.xref_stream(xref)).hexdigest()}
             for xref in page.get_contents()] for page in document]


def native_baseline(state, row):
    records = row.get('annotations', {})
    return {'library_scope_collection_key': state.get('collection_key'),
            'server_id': state.get('server_id'), 'collection_snapshot_at': state.get('updated_at'),
            'baseline_source': 'Accepted collection-sync snapshot; recheck live Zotero before publication.',
            'parent_item_key': PARENT, 'attachment_key': ATTACHMENT,
            'attachment_version': row.get('attachment_version'),
            'annotation_fingerprint': row.get('annotation_fingerprint'),
            'annotation_canonical_sha256': fingerprint(records),
            'annotations': records,
            'annotation_versions': {key: value.get('version') for key, value in records.items()}}


def verify(source, output, manifest):
    assert len(source) == len(output) == 801
    assert source.get_page_labels() == output.get_page_labels()
    assert canonical(source.get_toc(False)) == canonical(output.get_toc(False))
    assert page_body(source) == page_body(output)
    inserted = defaultdict(list)
    for record in manifest['links']:
        inserted[record['index0']].append(record)
        page = output[record['index0']]
        target_page = output[record['target_index0']]
        actual = page.get_textbox(fitz.Rect(record['source_rect']) + (-.15, -.15, .15, .15))
        if normalized(record['source_text']) not in normalized(actual):
            raise ValueError('Source anchor text mismatch: ' + str((record, actual)))
        target_text = target_page.get_textbox(fitz.Rect(record['target_label_bbox']) + (-.15, -.15, .15, .15))
        if record['kind'] == 'chapter':
            title = record['target_label_text']
            if not re.search(r'\bCHAPTER\s+' + title.split()[0] + r'\b', target_page.get_text()[:200]):
                raise ValueError('Chapter target identity mismatch: ' + title)
        elif normalized(record['target_label_text']) not in normalized(target_text):
            raise ValueError('Target label identity mismatch: ' + str((record, target_text)))
    for index in range(len(source)):
        before = canonical(source[index].get_links())
        after = canonical(output[index].get_links())
        if index not in inserted:
            assert before == after, 'Outside-scope link annotations changed on physical page ' + str(index + 1)
        else:
            assert before == after[:len(before)], 'An existing link changed.'
            fresh = after[len(before):]
            assert len(fresh) == len(inserted[index])
            for actual, intended in zip(fresh, inserted[index]):
                assert actual['kind'] == fitz.LINK_GOTO
                assert actual['page'] == intended['target_index0']
                assert max(abs(a-b) for a,b in zip(actual['from'], intended['source_rect'])) < .01
                assert max(abs(a-b) for a,b in zip(actual['to'], intended['target_point'])) < .01
        before_annots = [a.type for a in source[index].annots() or []]
        after_annots = [a.type for a in output[index].annots() or []]
        assert before_annots == after_annots, 'Embedded non-link annotations changed.'
    return {'all_801_pages_preserved': True, 'page_content_raw_and_decoded_streams_identical': True,
            'bookmarks_identical': True, 'printed_page_labels_identical': True,
            'outside_ch14_link_objects_identical': True, 'existing_links_preserved': True,
            'every_created_link_source_and_target_verified': True, 'native_annotations_not_embedded': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--analyze-only', action='store_true')
    args = parser.parse_args()
    root = args.workspace.resolve()
    folder = args.output_dir.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    state_path = root / '.local/zotero/collection-sync.json'
    state = json.loads(state_path.read_text())
    row = state['attachments'][ATTACHMENT]
    assert row['parent_item_key'] == PARENT
    if row.get('source_pdf'):
        source_path = root / row['source_pdf']
    else:
        retained = json.loads((root / '.local/zotero/paper-retention.json').read_text())
        source_path = root / retained['papers'][PARENT]['original_pdf']
    source_sha = sha(source_path)
    assert source_sha == row['source_sha256']
    if row.get('raw_copy_sha256'):
        assert source_sha == row['raw_copy_sha256']
    document = fitz.open(source_path)
    assert len(document) == 801
    assert document[CHAPTER_FIRST].get_label() == '576'
    assert document[CHAPTER_LAST].get_label() == '606'
    assert 'CHAPTER\n14\nNonlinearity and Mismatch' in document[CHAPTER_FIRST].get_text()
    assert 'CHAPTER\n15\nOscillators' in document[CHAPTER_LAST + 1].get_text()
    targets = inventory(document)
    links, unresolved, references = build_plan(document, targets)
    stamp = datetime.now(LOCAL_TZ).strftime('%Y-%m-%d_%H-%M-%S')
    title = state['items'][PARENT]['metadata']['data']['title']
    output = folder / (stamp + '_' + slug(title) + '_Candidate_EN.pdf')
    if output.exists():
        raise ValueError('Candidate filename already exists.')
    manifest = {'scope': 'Chapter 14 hyperlinks only; no answers or notes.',
                'created_at': datetime.now(LOCAL_TZ).isoformat(timespec='seconds'),
                'version_timezone': 'America/New_York',
                'source_pdf': str(source_path), 'source_sha256': source_sha,
                'accepted_mirror_sha256': row['mirror_sha256'],
                'chapter_physical_pages': [595,625], 'chapter_printed_labels': ['576','606'],
                'candidate_pdf': str(output), 'candidate_is_unpublished': True,
                'native_baseline': native_baseline(state,row),
                'original_link_count': sum(len(page.get_links()) for page in document),
                'original_chapter_link_count': sum(len(document[i].get_links()) for i in range(594,625)),
                'new_link_count': len(links), 'new_links_by_kind': dict(Counter(l['kind'] for l in links)),
                'logical_reference_counts': references, 'links': links, 'unresolved': unresolved,
                'targets': {key: value for key,value in targets.items()
                            if key.startswith(('equation:14.','figure:14.','section:14.','citation:'))
                            or key in {link['target_id'] for link in links}}}
    manifest_path = folder / 'chapter14-links-plan.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    if args.analyze_only:
        print(json.dumps({key:manifest[key] for key in ('new_link_count','new_links_by_kind','unresolved')},indent=2))
        return
    for record in links:
        document[record['index0']].insert_link({'kind':fitz.LINK_GOTO,
            'from':fitz.Rect(record['source_rect']), 'page':record['target_index0'],
            'to':fitz.Point(record['target_point']), 'zoom':0})
    document.save(output, garbage=0, clean=False, deflate=False, encryption=fitz.PDF_ENCRYPT_KEEP)
    document.close()
    original = fitz.open(source_path)
    result = fitz.open(output)
    manifest['verification'] = verify(original,result,manifest)
    manifest['candidate_sha256'] = sha(output)
    manifest['candidate_link_count'] = sum(len(page.get_links()) for page in result)
    latest = json.loads(state_path.read_text())['attachments'][ATTACHMENT]
    if latest['source_sha256'] != source_sha or fingerprint(latest['annotations']) != manifest['native_baseline']['annotation_canonical_sha256']:
        raise ValueError('Accepted source/annotation baseline changed during candidate construction. Candidate remains unpublished.')
    if sha(source_path) != source_sha:
        raise ValueError('Source body changed during candidate construction.')
    renders=[]
    for index in (598,623):
        path=folder/('chapter14-physical-'+str(index+1)+'.png')
        result[index].get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False).save(path)
        renders.append(str(path))
    manifest['representative_renders'] = renders
    manifest_path = output.with_suffix('.manifest.json')
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'candidate':str(output),'manifest':str(manifest_path),
                     'new_link_count':len(links),'new_links_by_kind':manifest['new_links_by_kind'],
                     'unresolved_count':len(unresolved),'verification':manifest['verification']},indent=2))


if __name__ == '__main__':
    main()
