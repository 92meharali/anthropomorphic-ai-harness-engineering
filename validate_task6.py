"""Offline, read-only XLSX validation and conversion. Standard library only."""
import argparse, collections, csv, hashlib, json, posixpath, re, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

FIELDS = ('preference', 'cue_needs_correction', 'content_preserved')
MAP = ({'A':'A','B':'B','Both fit equally well':'tie','Cannot judge':'cannot_judge'},
       {'A':'A','B':'B','Both':'both','Neither':'neither','Cannot judge':'cannot_judge'},
       {'Yes':True,'No':False,'Uncertain':None})
NS = {'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'

def check(ok, message):
    if not ok: raise ValueError(message)

def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def jsonl(p): return [json.loads(s) for s in Path(p).read_text(encoding='utf-8-sig').splitlines() if s.strip()]
def dump(p, obj): Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def write_rows(p, rows):
    with Path(p).open('w',encoding='utf-8',newline='\n') as f:
        for r in rows: f.write(json.dumps(r,ensure_ascii=False)+'\n')
def unique(rows, key):
    out={r[key]:r for r in rows}; check(len(out)==len(rows),f'duplicate {key}'); return out

def workbook(path):
    with zipfile.ZipFile(path) as z:
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            shared=[''.join(t.text or '' for t in si.findall('.//m:t',NS)) for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',NS)]
        rels={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        result={}
        for s in ET.fromstring(z.read('xl/workbook.xml')).findall('m:sheets/m:sheet',NS):
            target=rels[s.attrib[REL+'id']]; target=target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('xl',target))
            cells={}
            for c in ET.fromstring(z.read(target)).findall('.//m:sheetData/m:row/m:c',NS):
                typ=c.get('t'); v=c.findtext('m:v',default='',namespaces=NS)
                if typ=='s': v=shared[int(v)]
                elif typ=='inlineStr': v=''.join(t.text or '' for t in c.findall('.//m:t',NS))
                cells[c.attrib['r']]=(v,c.find('m:f',NS) is not None)
            result[s.attrib['name']]=cells
        return result

def value(sheet, addr, literal=False):
    v,f=sheet.get(addr,('',False)); check(not(literal and f),f'unexpected formula at {addr}'); return v

def frozen(study, source):
    m=json.loads((study/'manifest.json').read_text(encoding='utf-8-sig'))
    check(digest(source)==m['source_sha256'],'source hash mismatch')
    for fn in ('review_packet.jsonl','pair_key.jsonl'):
        check(digest(study/fn)==m['sha256'][fn],f'{fn} hash mismatch')
    packet=jsonl(study/'review_packet.jsonl'); key=unique(jsonl(study/'pair_key.jsonl'),'review_id'); src=unique(jsonl(source),'pair_id')
    check(len(packet)==len(key)==len(src)==m['pairs']==20,'expected 20 cases')
    check(list(unique(packet,'review_id'))==[f'W{i:04}' for i in range(1,21)],'unexpected packet IDs/order')
    check(set(key)=={p['review_id'] for p in packet},'key ID mismatch')
    check({k['pair_id'] for k in key.values()}==set(src),'source coverage mismatch')
    for p in packet:
        check(set(p)=={'review_id','prompt','A','B','pair_sha256'},'unexpected reviewer fields')
        h=hashlib.sha256(json.dumps({k:v for k,v in p.items() if k!='pair_sha256'},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        check(h==p['pair_sha256'],f'pair hash mismatch: {p["review_id"]}')
        k=key[p['review_id']]; s=src[k['pair_id']]
        check({k['A'],k['B']}=={'original','edited'} and k['cue']==s['cue'] and k['prompt_group_id']==s['prompt_group_id'],'invalid mapping')
        check((p['prompt'],p['A'],p['B'])==(s['prompt'],s[k['A']],s[k['B']]),'candidate/context mismatch')
    return packet

def convert(path, rid, packet):
    w=workbook(path); check(set(w)=={'Instructions','Annotation','Completion','Internal ballot'},f'{rid}: unexpected worksheets')
    id_rows=[n for n in (3,4) if value(w['Instructions'],f'A{n}',True)=='Annotator ID']
    check(len(id_rows)==1,f'{rid}: missing/ambiguous annotator ID label')
    embedded_id=value(w['Instructions'],f'B{id_rows[0]}',True)
    check(embedded_id==rid,f'{rid}: annotator ID mismatch')
    a=w['Annotation']; b=w['Internal ballot']; rows=[]; absent_cache=0
    check([value(b,f'{c}1',True) for c in 'ABCDE']==['review_id','pair_sha256',*FIELDS],f'{rid}: ballot header mismatch')
    check([value(a,f'{c}4',True) for c in 'ABCD']==['Case ID','Conversation context','Answer A','Answer B'],f'{rid}: annotation header mismatch')
    for i,p in enumerate(packet):
        ar=i+5; br=i+2
        check([value(a,f'{c}{ar}',True) for c in 'ABCD']==[p['review_id'],p['prompt'],p['A'],p['B']],f'{rid}: altered case at row {ar}')
        check([value(b,f'{c}{br}',True) for c in 'AB']==[p['review_id'],p['pair_sha256']],f'{rid}: metadata mismatch')
        vals=[]
        for c, mapping in zip('EFG',MAP):
            v=value(a,f'{c}{ar}',True); check(v in mapping,f'{rid}: missing/invalid {c}{ar}: {v!r}'); vals.append(mapping[v])
        for c,v in zip('CDE',vals):
            cached=value(b,f'{c}{br}'); expected=json.dumps(v) if v is None or isinstance(v,bool) else v
            if not cached: absent_cache+=1
            else: check(cached==expected,f'{rid}: cached ballot disagrees at {c}{br}')
        rows.append(dict(review_id=p['review_id'],pair_sha256=p['pair_sha256'],**dict(zip(FIELDS,vals))))
    for sheet,start,cols in [(a,25,'ABCDEFG'),(b,22,'ABCDE')]:
        for addr,(v,f) in sheet.items():
            match=re.fullmatch(r'([A-Z]+)(\d+)',addr)
            if match and match[1] in cols and int(match[2])>=start: check(not v and not f,f'{rid}: unexpected data after final case: {addr}')
    return rows,absent_cache,embedded_id

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--study',type=Path,required=True); ap.add_argument('--source',type=Path,required=True); ap.add_argument('--raw',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); args=ap.parse_args()
    packet=frozen(args.study,args.source); results={}; audit={}
    for rid in ('R01','R02','R03'):
        path=args.raw/f'Development_Annotation_Sheet_{rid}.xlsx'; rows,missing,embedded=convert(path,rid,packet); results[rid]=rows
        audit[rid]={'input_sha256':digest(path),'pairs':len(rows),'questions':len(rows)*3,'uncached_ballot_cells':missing,'embedded_id':embedded,'identity_status':'matches_filename','status':'technical_pass'}
    args.out.mkdir(parents=True,exist_ok=False)
    for rid,rows in results.items():
        write_rows(args.out/f'{rid}.jsonl',rows)
        audit[rid]['output_sha256']=digest(args.out/f'{rid}.jsonl')
    dump(args.out/'validation.json',{'status':'technical_pass','provenance':'not verifiable from workbooks','source_sha256':digest(args.source),'packet_sha256':digest(args.study/'review_packet.jsonl'),'reviewers':audit,'total_pairs':60,'total_question_responses':180})
    print('PASS: 3 workbooks, 60 pair judgments, 180 question responses; provenance not verified.')
if __name__=='__main__': main()
