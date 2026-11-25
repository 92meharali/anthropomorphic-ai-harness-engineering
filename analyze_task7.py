"""Descriptive agreement on frozen development ballots; no adjudication or model scoring."""
import argparse, collections, itertools, json, hashlib
from pathlib import Path

FIELDS=('preference','cue_needs_correction','content_preserved')
CATEGORIES=(('A','B','tie','cannot_judge'),('A','B','both','neither','cannot_judge'),(True,False,None))
RIDS=('R01','R02','R03')

def load(p): return [json.loads(l) for l in p.read_text(encoding='utf-8-sig').splitlines() if l.strip()]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def check(ok,msg):
    if not ok: raise ValueError(msg)
def label(v): return json.dumps(v) if v is None or isinstance(v,bool) else v
def kappa(matrix,cats):
    n=len(matrix); r=len(matrix[0]); counts=[collections.Counter(row) for row in matrix]
    observed=sum(sum(c[v]*(c[v]-1) for v in cats)/(r*(r-1)) for c in counts)/n
    marginals={v:sum(c[v] for c in counts)/(n*r) for v in cats}; expected=sum(p*p for p in marginals.values())
    return {'observed_pairwise_agreement':observed,'expected_agreement':expected,'fleiss_kappa':None if expected==1 else (observed-expected)/(1-expected)}
def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--validated',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args()
    audit=json.loads((a.validated/'validation.json').read_text(encoding='utf-8')); check(audit['status']=='technical_pass','validation required')
    ballots=[]
    for rid in RIDS:
        p=a.validated/f'{rid}.jsonl'; check(sha(p)==audit['reviewers'][rid]['output_sha256'],f'{rid}: ballot changed since validation'); ballots.append(load(p))
    ids=[(r['review_id'],r['pair_sha256']) for r in ballots[0]]
    check(len(ids)==20 and len(set(ids))==20,'expected 20 distinct cases')
    for b in ballots:
        check([(r['review_id'],r['pair_sha256']) for r in b]==ids,'ballot case mismatch')
        for r in b:
            check(set(r)=={'review_id','pair_sha256',*FIELDS},'unexpected ballot schema')
            for f,cats in zip(FIELDS,CATEGORIES): check(any(type(r[f]) is type(v) and r[f]==v for v in cats),f'invalid value {f}')
    summary={}; disagreements=[]; majority=[]
    for f,cats in zip(FIELDS,CATEGORIES):
        matrix=[[b[i][f] for b in ballots] for i in range(20)]; freq=collections.Counter(v for row in matrix for v in row)
        summary[f]={'unanimous_cases':sum(len(set(row))==1 for row in matrix),'cases':20,'rating_counts':{label(v):freq[v] for v in cats},**kappa(matrix,cats)}
        for i,row in enumerate(matrix):
            if len(set(row))>1: disagreements.append({'review_id':ids[i][0],'field':f,'original_ratings':dict(zip(RIDS,row)),'discussion_status':'pending_human_discussion','adjudication_status':'not_adjudicated'})
    for i,(review_id,h) in enumerate(ids):
        out={'review_id':review_id,'pair_sha256':h,'majority':{}}
        for f in FIELDS:
            v,n=collections.Counter(b[i][f] for b in ballots).most_common(1)[0]
            out['majority'][f]={'has_majority':n>=2,'value':v if n>=2 else None,'votes':n}
        majority.append(out)
    a.out.mkdir(parents=True,exist_ok=False)
    for name,data in [('aggregate.json',{'provenance':'unverified; descriptive submission agreement only','cases':20,'reviewers':3,'metrics':summary,'unanimous_case_question_combinations':sum(x['unanimous_cases'] for x in summary.values()),'case_question_combinations':60}),('disagreements.json',disagreements),('majority_private.json',majority)]:
        (a.out/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2)); print(f'{len(disagreements)} disagreements; human discussion not performed.')
if __name__=='__main__': main()
