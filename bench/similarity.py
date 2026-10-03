"""Offline embeddings from explicitly approved, SHA-pinned safe encoder snapshots.
No downloads, remote code or pickle files. Under issue-14's current allowed-weight
policy CLIP is blocked (no allowed CLIP repository), and GGUF DINOv3 needs a native
embedding adapter. This optional transformer adapter is for future explicitly
approved compatible safetensors sets; it does not bypass the current policy.
"""
import argparse, json, pathlib, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from run import sha,allowed
p=argparse.ArgumentParser(); p.add_argument('--run',required=True); p.add_argument('--config',required=True); a=p.parse_args(); root=pathlib.Path(a.run); cfg=json.loads(pathlib.Path(a.config).read_text()); scores={}
for family in ['clip','dino']:
    c=cfg[family]
    if not allowed(c['hf_repo']): raise ValueError('Encoder source outside current authorized repositories: '+family)
    if c.get('evaluation_accepted') is not True: raise ValueError('Encoder evaluation licence acceptance missing')
    snapshot=pathlib.Path(c['snapshot']).resolve()
    if any(snapshot.rglob('*.bin')) or any(snapshot.rglob('*.pt')) or any(snapshot.rglob('*.py')): raise ValueError('Pickle or executable code in encoder snapshot')
    for name,expected in c['files'].items():
        path=(snapshot/name).resolve()
        if not path.is_relative_to(snapshot) or sha(path)!=expected: raise ValueError('Encoder hash mismatch')
    if set(str(f.relative_to(snapshot)) for f in snapshot.rglob('*') if f.is_file())!=set(c['files']): raise ValueError('Unmanifested encoder files')
    import torch
    from PIL import Image
    from transformers import AutoImageProcessor, AutoModel, CLIPModel, CLIPProcessor
    torch.set_num_threads(4)
    cls=CLIPModel if family=='clip' else AutoModel; proc_cls=CLIPProcessor if family=='clip' else AutoImageProcessor
    model=cls.from_pretrained(snapshot,local_files_only=True,trust_remote_code=False,use_safetensors=True).eval(); proc=proc_cls.from_pretrained(snapshot,local_files_only=True,trust_remote_code=False)
    def emb(path):
        image=Image.open(path).convert('RGBA'); bg=Image.new('RGBA',image.size,(227,229,225,255)); bg.alpha_composite(image); batch=proc(images=bg.convert('RGB'),return_tensors='pt')
        with torch.no_grad():
            if family=='clip': vec=model.get_image_features(**batch)
            else: vec=model(**batch).last_hidden_state[:,1:].mean(dim=1)
        return torch.nn.functional.normalize(vec,dim=-1)
    refs={'front':0,'right':2,'back':4,'left':6}; refvec={v:emb(root/'inputs'/f'{v}.png') for v in refs}; stage={}
    for kind in ['raw','cleaned']:
        vals={view:float((emb(root/kind/f'{index:02}.png')*refvec[view]).sum()) for view,index in refs.items()}; stage[kind]={'cosines':vals,'mean':sum(vals.values())/4}
    scores[family]={'encoder':c,'matched_views':stage,'note':'Similarity proxy, not clinical accuracy; alpha composited on same neutral background. Opposite views not best-match selected.'}
(root/'similarity.json').write_text(json.dumps({'status':'completed','embeddings':scores},indent=2)+'\n')
