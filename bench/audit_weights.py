"""Print hashes for independent/manual comparison, then record reviewed receipt."""
import argparse,json,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent)); from run import sha
p=argparse.ArgumentParser(); p.add_argument('--manifest',required=True); p.add_argument('--weights',required=True); p.add_argument('--reviewer'); p.add_argument('--confirm-compared',action='store_true'); a=p.parse_args(); m=pathlib.Path(a.manifest).resolve(); root=pathlib.Path(a.weights).resolve(); data=json.loads(m.read_text()); ok=True; files=[]
for f in data['files']:
    if pathlib.Path(f['name']).name!=f['name'] or '\\' in f['name'] or ':' in f['name']: raise ValueError('Unsafe name')
    path=root/f['name']; actual=sha(path); match=actual==f['sha256'] and path.stat().st_size==f['size_bytes']; ok &=match; files.append({'name':f['name'],'expected':f['sha256'],'actual':actual,'match':match}); print(json.dumps(files[-1]))
if not ok: raise SystemExit('Verification mismatch; loader remains blocked')
if a.confirm_compared:
    if not a.reviewer: p.error('--reviewer required')
    (root/'manual-verification.json').write_text(json.dumps({'manifest_sha256':sha(m),'reviewer':a.reviewer,'evaluation_only':True,'independently_compared_files':files},indent=2)+'\n')
