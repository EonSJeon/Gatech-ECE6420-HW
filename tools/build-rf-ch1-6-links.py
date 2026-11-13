#!/usr/bin/env python3
"""Add and verify navigation for Chapters 1-6 of RF Microelectronics.

Preserve page content, native annotations, and other chapters. Publication uses
a separate scoped transaction. All destinations derive from printed labels.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo
import pymupdf as fitz

ROOT=Path('/Users/jeonsang-eon/Gatech-ECE6420')
PARENT,ATTACHMENT='5XLCGB2J','X5RDQG68'
FIRST,LAST=25,452
TZ=ZoneInfo('America/New_York')
spec=importlib.util.spec_from_file_location('ch14_helpers',ROOT/'tools/build-razavi-ch14-links.py')
h=importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

def dump(path,obj):
    path.write_text(json.dumps(h.canonical(obj),ensure_ascii=False,indent=2)+'\n')

def rows(page):
    return [l for b in page.get_text('dict')['blocks'] for l in b.get('lines',[])]

def textof(line):
    return ''.join(s['text'] for s in line['spans'])

def chapter(i,chapters):
    return max(c for c,start in chapters.items() if start<=i)

def labelbox(page,label,linebox,tp=None):
    matches=page.search_for(label,textpage=tp)
    assert matches,('Unsearchable label',page.number+1,label)
    result=min(matches,key=lambda r:abs(r.y0-linebox[1]))
    assert abs(result.y0-linebox[1])<12,('Label geometry mismatch',page.number+1,label,linebox,matches)
    return result

def inventory(doc):
    targets,definitions={},defaultdict(list)
    chapters={int(re.match(r'Chapter (\d+):',t)[1]):p-1 for l,t,p in doc.get_toc() if re.match(r'Chapter (\d+):',t)}
    def put(kind,ident,i,box,label,point=None,repeated=False):
        key=kind+':'+str(ident)
        definitions[i].append((key,list(box)))
        if repeated and key in targets:return
        assert key not in targets,('Duplicate target',key,i+1,targets.get(key))
        targets[key]={'index0':i,'physical_page':i+1,'printed_label':doc[i].get_label(),
                      'label_bbox':list(box),'label_text':label,'point':point or [0,max(50,box[1]-30)]}
    for c,i in chapters.items():
        l=next(l for l in rows(doc[i]) if textof(l).strip()=='CHAPTER')
        put('chapter',c,i,l['bbox'],'CHAPTER',[0,100])
    for i in range(FIRST,len(doc)):
        page=doc[i];ll=rows(page);tp=page.get_textpage()
        c=chapter(i,chapters)
        for j,l in enumerate(ll):
            t=textof(l).strip();bb=l['bbox']
            if bb[1]<60:continue
            if any(s['font']=='UniversLTStd-Black' and 11.8<s['size']<13.2 for s in l['spans']):
                if re.fullmatch(r'\d+\.\d+(?:\.\d+)?',t):
                    put('subsection' if t.count('.')==2 else 'section',t,i,bb,t,[0,max(50,bb[1]-18)])
                if t in ('REFERENCES','PROBLEMS'):
                    put(t.lower(),c,i,bb,t,[0,max(50,bb[1]-18)])
            m=re.fullmatch(r'\((\d+\.\d+)\)',t)
            if m and bb[0]>395:
                put('equation',m[1],i,bb,m[0])
            m=re.match(r'(Figure|Table)\s+(\d+\.\d+)\b',t)
            if m and any(s['font']=='Times-Bold' for s in l['spans']):
                b=labelbox(page,m[0],bb,tp)
                prior=[old['bbox'][3]+8 for old in ll[:j] if old['bbox'][3]<bb[1]-3 and old['bbox'][1]>55 and
                       ((len(textof(old))>35 and any(s['font']=='Times-Roman' and 10.8<s['size']<11.2 for s in old['spans'])) or re.match(r'Figure\s+\d+\.\d+',textof(old)))]
                put(m[1].lower(),m[2],i,b,m[0],[0,min(max(prior or [55]),max(55,bb[1]-40))])
            m=re.match(r'Example\s+(\d+\.\d+)\b',t)
            if m and any(s['font']=='Times-Bold' and s['size']>11 for s in l['spans']):
                b=labelbox(page,m[0],bb,tp)
                put('example',m[1],i,b,m[0],repeated=True)
    # Labels sharing a line with the equation expression are known exactly.
    for ident,i in {'2.37':44,'3.41':137,'3.50':146,'3.60':165,'4.16':204,'4.142':258,'6.132':426,'6.147':438}.items():
        if 'equation:'+ident not in targets:
            b=next(r for r in doc[i].search_for('('+ident+')') if r.x0>395)
            put('equation',ident,i,b,'('+ident+')')
    for c in range(1,7):
        start=targets['references:'+str(c)];stop=targets.get('problems:'+str(c))
        for i in range(start['index0'],(stop['index0'] if stop else chapters[c+1]-1)+1):
            for l in rows(doc[i]):
                if i==start['index0'] and l['bbox'][1]<=start['label_bbox'][3]:continue
                if stop and i==stop['index0'] and l['bbox'][1]>=stop['label_bbox'][1]:continue
                m=re.match(r'^\[(\d+)\]',textof(l))
                if m and l['bbox'][0]<85:
                    b=labelbox(doc[i],m[0],l['bbox'])
                    put('citation',str(c)+'.'+m[1],i,b,m[0])
    for c,n in {2:259,3:71,4:155,5:205,6:163}.items():
        assert all('equation:'+str(c)+'.'+str(k) in targets for k in range(1,n+1)),('Missing equations',c)
    for level,title,p in doc.get_toc():
        m=re.match(r'^(\d+\.\d+(?:\.\d+)?)\s',title)
        if m and int(m[1].split('.')[0])<=6:
            key=('subsection:' if m[1].count('.')==2 else 'section:')+m[1]
            assert key in targets and targets[key]['index0']==p-1,('Heading/TOC mismatch',title)
    return targets,definitions,chapters

def build_links(doc,targets,defs,chapters):
    links,unresolved=[],[];seen=set();skips=Counter()
    def add(i,kind,ident,parts,context,contents=False):
        key=kind+':'+ident
        if kind=='section' and key not in targets and 'subsection:'+ident in targets:
            key='subsection:'+ident;kind='subsection'
        if not parts or all(b[1]<60 for b,t in parts):return
        if all(any((fitz.Rect(b)&fitz.Rect(db)).get_area()/max(1,fitz.Rect(b).get_area())>.75 for dk,db in defs[i] if dk==key) for b,t in parts):
            skips['definition_labels']+=1;return
        dest=targets.get(key)
        if not dest:
            unresolved.append({'physical_page':i+1,'printed_label':doc[i].get_label(),'id':key,
                               'text':' '.join(t for b,t in parts),'context':context,
                               'reason':'No exact printed destination was identified.'});return
        for box,anchor in parts:
            sig=(i,tuple(round(v,3) for v in box),key)
            if sig in seen:continue
            seen.add(sig)
            links.append({'index0':i,'physical_page':i+1,'printed_label':doc[i].get_label(),
                          'kind':'contents' if contents else kind,'target_id':key,'source_text':anchor,
                          'source_rect':box,'target_index0':dest['index0'],'target_point':dest['point'],
                          'target_label_bbox':dest['label_bbox'],'target_label_text':dest['label_text'],'context':context})
    for i in range(FIRST,LAST+1):
        txt,boxes,_=h.flattened(doc[i]);c=chapter(i,chapters)
        def matchadd(kind,ident,m,a=None,b=None):
            parts=list(h.rect_parts(txt,boxes,m.start() if a is None else a,m.end() if b is None else b))
            context=re.sub(r'\s+',' ',txt[max(0,m.start()-45):m.end()+100]).strip()
            add(i,kind,ident,parts,context)
        for m in re.finditer(r'\((\d+\.\d+)\)',txt):
            if int(m[1].split('.')[0]) in chapters:matchadd('equation',m[1],m)
            else:skips['parenthesized_numeric_values']+=1
        for kind,prefix in [('figure',r'(?:Figs?\.|Figures?)'),('table',r'Tables?'),
                            ('section',r'(?:Secs?\.|Sections?|Subsections?|Sec-\s*tion)'),('example',r'Examples?')]:
            number=r'\d+\.\d+(?:\.\d+)?' if kind=='section' else r'\d+\.\d+'
            for m in re.finditer(r'\b'+prefix+r'\s+('+number+r')(?:\([a-z]\))?',txt):
                matchadd(kind,m[1],m);tail=m.end()
                for _ in range(12):
                    n=re.match(r'\s*(?:,\s*(?:and\s+)?|and\s+|or\s+|to\s+|through\s+|[\u2013\u2014-]\s*)('+number+r')(?:\([a-z]\))?',txt[tail:])
                    if not n:break
                    matchadd(kind,n[1],m,tail+n.start(1),tail+n.end());tail+=n.end()
                if kind=='figure':
                    n=re.match(r'\s+(?:and|or)\s+(\([a-z]\))',txt[m.end():])
                    if n:matchadd(kind,m[1],m,m.end()+n.start(1),m.end()+n.end(1))
        for m in re.finditer(r'\b(?:Chapters?|Chaps?\.)\s+(\d+)\b',txt):
            matchadd('chapter',m[1],m);tail=m.end()
            for _ in range(6):
                n=re.match(r'\s*(?:,\s*(?:and\s+)?|and\s+|through\s+|to\s+|[\u2013\u2014-]\s*)(\d+)\b',txt[tail:])
                if not n:break
                matchadd('chapter',n[1],m,tail+n.start(1),tail+n.end(1));tail+=n.end()
        for m in re.finditer(r'\b(?:Eq\.|Equation)\s+(\d+\.\d+)\b',txt):matchadd('equation',m[1],m)
        for m in re.finditer(r'\[(\d+(?:\s*[,\u2013-]\s*\d+)*)\]',txt):
            if any(len(n)>1 and n.startswith('0') for n in re.findall(r'\d+',m[1])):
                skips['binary_data_sequences']+=1;continue
            if m[1].isdigit():matchadd('citation',str(c)+'.'+m[1],m)
            else:
                for n in re.finditer(r'\d+',m[1]):
                    a=m.start(1)+n.start();matchadd('citation',str(c)+'.'+n[0],m,a,a+len(n[0]))
    # Clickable contents entries include the title and printed page number.
    toc_chapter=None
    for i in range(7,11):
        ll=rows(doc[i])
        for j,l in enumerate(ll):
            t=textof(l).strip();bb=l['bbox'];m=re.fullmatch(r'CHAPTER (\d+)',t);key=None
            if m:toc_chapter=int(m[1]);key='chapter:'+m[1]
            elif re.fullmatch(r'\d+\.\d+(?:\.\d+)?',t):key=('subsection:' if t.count('.')==2 else 'section:')+t
            elif t in ('References','Problems') and toc_chapter:key=t.lower()+':'+str(toc_chapter)
            if not (key and toc_chapter and toc_chapter<=6):continue
            bands=defaultdict(list);bands[round(bb[1],1)].append(l)
            for nxt in ll[j+1:j+6]:
                nb=nxt['bbox']
                if abs(nb[1]-bb[1])<3 or (m and nb[0]>=130 and nb[1]<bb[3]+15):
                    bands[round(nb[1],1)].append(nxt)
                else:break
            for band in bands.values():
                b=fitz.Rect(band[0]['bbox'])
                for old in band[1:]:b |= fitz.Rect(old['bbox'])
                add(i,*key.split(':',1),[(list(b),doc[i].get_textbox(b+(-.1,-.1,.1,.1)))],
                    'Printed table of contents',contents=True)
    bp=defaultdict(list)
    for row in links:bp[row['index0']].append(row)
    for i,ll in bp.items():
        for j,a in enumerate(ll):
            for b in ll[j+1:]:
                assert a['target_id']==b['target_id'] or (fitz.Rect(a['source_rect'])&fitz.Rect(b['source_rect'])).get_area()<.3,('Overlapping different targets',i+1,a,b)
    return links,unresolved,dict(skips)

def bookmarks(doc,targets):
    result=[];c=None
    for k,(level,title,page) in enumerate(doc.get_toc()):
        m=re.match(r'Chapter (\d+):',title);key=None
        if m:c=int(m[1]);key='chapter:'+m[1]
        if c and c<=6:
            n=re.match(r'^(\d+\.\d+(?:\.\d+)?)\s',title)
            if n:key=('subsection:' if n[1].count('.')==2 else 'section:')+n[1]
            if title in ('References','Problems'):key=title.lower()+':'+str(c)
            if key:
                dest=targets[key]
                result.append({'toc_index':k,'title':title,'target_id':key,'index0':dest['index0'],'point':dest['point']})
    return result

def set_bookmarks(doc,planned):
    toc=doc.get_toc(False)
    for r in planned:
        page=doc[r['index0']]
        dest=fitz.Point(r['point'])*~page.transformation_matrix
        xref=toc[r['toc_index']][3]['xref']
        doc.xref_set_key(xref,'A',f'<</S/GoTo/D[{page.xref} 0 R/XYZ {dest.x:.6f} {dest.y:.6f} 0]>>')
        doc.xref_set_key(xref,'Dest','null')

def verify(src,out,plan,work):
    assert len(src)==len(out)==946 and src.get_page_labels()==out.get_page_labels()
    assert h.page_body(src)==h.page_body(out)
    assert all(src.xref_stream_raw(x)==out.xref_stream_raw(x) for x in {im[0] for p in src for im in p.get_images()})
    bp=defaultdict(list)
    for row in plan['links']:bp[row['index0']].append(row)
    @lru_cache(maxsize=24)
    def tp(i):
        page=out[i]
        return page,page.get_textpage()
    for i,p in enumerate(out):
        a=h.canonical(src[i].get_links());b=h.canonical(p.get_links())
        assert a==b[:len(a)],('Original links changed',i+1)
        fresh=b[len(a):];assert len(fresh)==len(bp[i]),('Link count mismatch',i+1)
        # The source contains /GoTo /D null links. MuPDF reports xref=0 for
        # valid links on these mixed pages. Obtain object identities from the
        # actual annotation array and preserve every original object unchanged.
        old_xrefs=[x for x,t,n in src[i].annot_xrefs() if t==fitz.PDF_ANNOT_LINK]
        all_xrefs=[x for x,t,n in p.annot_xrefs() if t==fitz.PDF_ANNOT_LINK]
        assert all_xrefs[:len(old_xrefs)]==old_xrefs
        assert all(src.xref_object(x)==out.xref_object(x) for x in old_xrefs)
        new_xrefs=all_xrefs[len(old_xrefs):];assert len(new_xrefs)==len(fresh)
        for actual,want,xref in zip(fresh,bp[i],new_xrefs):
            assert actual['kind']==fitz.LINK_GOTO and actual['page']==want['target_index0']
            assert max(abs(a-b) for a,b in zip(actual['from'],want['source_rect']))<.02
            assert max(abs(a-b) for a,b in zip(actual['to'],want['target_point']))<.02
            anchor=tp(i)[1].extractTextbox(fitz.Rect(want['source_rect'])+(-.15,-.15,.15,.15))
            assert h.normalized(want['source_text']) in h.normalized(anchor),('Source text mismatch',want)
            target=tp(want['target_index0'])[1].extractTextbox(fitz.Rect(want['target_label_bbox'])+(-.15,-.15,.15,.15))
            assert h.normalized(want['target_label_text']) in h.normalized(target),('Target mismatch',want)
            assert '/W0' in re.sub(r'\s+','',out.xref_object(xref)),('Visible link border',want)
        assert len(list(p.annots() or []))==len(list(src[i].annots() or []))==0
        assert p.rect==src[i].rect and p.rotation==src[i].rotation
    before,after=src.get_toc(False),out.get_toc(False)
    assert [r[:3] for r in before]==[r[:3] for r in after]
    edited={r['toc_index']:r for r in plan['bookmarks']}
    for k,(a,b) in enumerate(zip(before,after)):
        if k not in edited:assert h.canonical(a)==h.canonical(b),('Other bookmark changed',k)
        else:
            w=edited[k];assert b[3]['page']==w['index0']
            assert max(abs(a-b) for a,b in zip(b[3]['to'],w['point']))<.02
    renders=[]
    for i in [7,32,44,99,215,291,361,438,452,453]:
        a=src[i].get_pixmap(matrix=fitz.Matrix(1.25,1.25),alpha=False)
        b=out[i].get_pixmap(matrix=fitz.Matrix(1.25,1.25),alpha=False)
        assert a.samples==b.samples,('Visual change',i+1)
        path=work/f'physical-{i+1}.png';b.save(path);renders.append(str(path))
    return {'all_946_page_bodies_and_images_identical':True,'page_labels_dimensions_preserved':True,
            'every_new_link_anchor_destination_verified':True,'outside_scope_links_preserved':True,
            'bookmark_hierarchy_titles_preserved':True,'no_embedded_native_annotations':True,
            'representative_pages_pixel_identical':True,'renders':renders}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--work-dir',type=Path,required=True)
    ap.add_argument('--analyze-only',action='store_true');args=ap.parse_args()
    work=args.work_dir.resolve();work.mkdir(parents=True,exist_ok=True)
    state=json.loads((ROOT/'.local/zotero/collection-sync.json').read_text());row=state['attachments'][ATTACHMENT]
    expected='736f467626f9fe3bddcba8ae0be441195208db22f5d3b74ac4794b3dd3d8d47d'
    if row['source_sha256']==expected:
        path=ROOT/row['source_pdf']
    else:
        retained=json.loads((ROOT/'.local/zotero/paper-retention.json').read_text())
        path=ROOT/retained['papers'][PARENT]['original_pdf']
    baseline=h.sha(path)
    assert baseline==expected,'The immutable RF source baseline changed.'
    doc=fitz.open(path);assert len(doc)==946 and doc[FIRST].get_label()=='1' and doc[LAST].get_label()=='428'
    targets,defs,chapters=inventory(doc);links,unresolved,skips=build_links(doc,targets,defs,chapters)
    stamp=datetime.now(TZ).strftime('%Y-%m-%d_%H-%M-%S')
    plan={'parent_item_key':PARENT,'attachment_key':ATTACHMENT,'collection_key':'8J2MG92V',
          'scope':'Chapters 1-6 and their printed contents entries; navigation only.',
          'created_at':datetime.now(TZ).isoformat(timespec='seconds'),'version_timezone':'America/New_York',
          'version_stamp':stamp,'source_pdf':str(path),'source_sha256':baseline,
          'source_md5':hashlib.md5(path.read_bytes()).hexdigest(),'native_baseline':row['annotations'],
          'native_fingerprint':row['annotation_fingerprint'],'attachment_version':row['attachment_version'],
          'accepted_mirror_sha256':row['mirror_sha256'],'previous_display_pdf':row['display_pdf'],
          'physical_scope':[26,453],'printed_scope':['1','428'],'targets':targets,'links':links,
          'unresolved':unresolved,'bookmarks':bookmarks(doc,targets),'skipped':skips,
          'new_links_by_kind':dict(Counter(x['kind'] for x in links)),
          'new_links_by_chapter':dict(Counter(str(chapter(x['index0'],chapters)) if x['index0']>=FIRST else 'Contents' for x in links)),
          'target_counts':dict(Counter(k.split(':')[0] for k in targets)),'status':'analyzed_unpublished'}
    dump(work/'plan.json',plan)
    if not args.analyze_only:
        for r in links:doc[r['index0']].insert_link({'kind':fitz.LINK_GOTO,'from':fitz.Rect(r['source_rect']),
                                                   'page':r['target_index0'],'to':fitz.Point(r['target_point']),'zoom':0})
        set_bookmarks(doc,plan['bookmarks'])
        output=work/(stamp+'_RF_microelectronics_Candidate_EN.pdf')
        doc.save(output,garbage=0,clean=False,deflate=False,encryption=fitz.PDF_ENCRYPT_KEEP);doc.close()
        with fitz.open(path) as src,fitz.open(output) as out:plan['verification']=verify(src,out,plan,work)
        plan.update(candidate_pdf=str(output),candidate_sha256=h.sha(output),candidate_md5=hashlib.md5(output.read_bytes()).hexdigest(),status='candidate_verified_unpublished')
        dump(work/'plan.json',plan)
    print(json.dumps({k:plan[k] for k in ['status','new_links_by_kind','new_links_by_chapter','target_counts','skipped','unresolved']},indent=2))

if __name__=='__main__':main()
