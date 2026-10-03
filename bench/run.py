"""One command executes configured cells, records blocked/failed cells, resumes and reports."""
import argparse, hashlib, itertools, json, os, pathlib, platform, re, shutil, subprocess, time
import yaml, psutil
B=pathlib.Path(__file__).resolve().parent

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(8<<20),b''): h.update(b)
    return h.hexdigest()

def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True); tmp=p.with_suffix('.tmp'); tmp.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n'); tmp.replace(p)

def resolve(v): return (B/v).resolve()
def allowed(repo): return bool(repo and (repo.startswith('raven38/pixal3d-') or repo=='ilintar/trellis2-gguf'))

def verified_models(model):
    if not allowed(model.get('hf_repo')): raise ValueError('Unapproved or unspecified Hugging Face source')
    if not re.fullmatch('[0-9a-f]{40}',model.get('hf_revision') or ''): raise ValueError('HF revision not pinned to a full commit SHA')
    manifest=resolve(model['manifest']); data=json.loads(manifest.read_text()); files=[]
    for f in data['files']:
        name=f['name']
        if pathlib.PurePosixPath(name).name!=name or '\\' in name or ':' in name or name in ('.','..'): raise ValueError('Unsafe model filename')
        if not re.fullmatch('[0-9a-f]{64}',f.get('sha256','')): raise ValueError('Missing trusted hash')
        path=resolve(model['weights'])/name
        if not path.is_file() or path.is_symlink(): raise ValueError('Missing model file: '+name)
        if path.stat().st_size!=f['size_bytes']: raise ValueError('Size mismatch: '+name)
        actual=sha(path)
        if actual!=f['sha256']: raise ValueError('SHA-256 mismatch: '+name)
        files.append(dict(f,actual_sha256=actual,hf_repo=model['hf_repo'],hf_revision=model['hf_revision']))
    if set(p.name for p in resolve(model['weights']).glob('*.gguf'))!=set(f['name'] for f in files): raise ValueError('Unmanifested GGUF present; refusing loader directory')
    receipt=resolve(model['weights'])/'manual-verification.json'
    r=json.loads(receipt.read_text())
    if r.get('manifest_sha256')!=sha(manifest) or not r.get('reviewer') or r.get('evaluation_only') is not True: raise ValueError('Manual SHA comparison receipt absent/stale')
    return {'manifest_sha256':sha(manifest),'files':files,'manual_verification':r}

def verified_input(asset):
    root=resolve(asset['input']); prov=json.loads((root/'provenance.json').read_text())
    if prov.get('no_patient_or_clinical_images') is not True: raise ValueError('Input no-PHI provenance missing')
    from PIL import Image
    hashes={}
    for name in ['front.png','back.png','left.png','right.png']:
        path=root/name
        if path.stat().st_size>32<<20: raise ValueError('Input >32MiB')
        with Image.open(path) as im:
            if im.format!='PNG' or im.mode!='RGBA' or max(im.size)>4096: raise ValueError('Bounded RGBA PNG required')
            lo,hi=im.getchannel('A').getextrema()
            if lo==hi: raise ValueError('Real alpha required')
        actual=sha(path)
        if prov['images'][name]!=actual: raise ValueError('Input differs from provenance')
        hashes[name]=actual
    t=json.loads((root/'transforms.json').read_text())
    if len(t['frames'])!=4: raise ValueError('Exactly four explicit cameras required')
    if set(x['file_path'] for x in t['frames'])!=set(hashes): raise ValueError('Unsafe/mismatched transform paths')
    hashes['transforms.json']=sha(root/'transforms.json')
    return {'provenance':prov,'files':hashes}

def build_provenance(host,engine):
    h=host['engines'][engine]; ev=json.loads(resolve(h['evidence']).read_text()); exe=resolve(h['binary'])
    if ev.get('status')!='success' or not ev.get('source_only') or not ev.get('webp_off'): raise ValueError('No successful safe source build evidence')
    if sha(exe)!=ev['binary_sha256']: raise ValueError('Binary no longer matches source build')
    if ev['backend']!=host['backend']: raise ValueError('Build/backend mismatch')
    if engine=='pixal' and not ev['source_commit'].startswith('1f432fd'): raise ValueError('Pixal baseline not built at requested commit')
    return ev

def sample_run(cmd,cwd,timeout,env=None):
    # No shell, no server; fresh process per seed includes cold model load.
    start=time.perf_counter(); peak=0; gpu_peak=None; device_peak=None; nv=None; observations=0
    try:
        import pynvml as nv
        nv.nvmlInit()
    except Exception: nv=None
    with (cwd/'generation.log').open('w') as f:
        p=subprocess.Popen(cmd,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,env=env); timed=False
        while p.poll() is None:
            observations+=1
            try:
                processes=[psutil.Process(p.pid)]+psutil.Process(p.pid).children(recursive=True); peak=max(peak,sum(x.memory_info().rss for x in processes if x.is_running())); pids={x.pid for x in processes}
                if nv:
                    total_proc=total_device=0
                    for i in range(nv.nvmlDeviceGetCount()):
                        h=nv.nvmlDeviceGetHandleByIndex(i); total_device+=nv.nvmlDeviceGetMemoryInfo(h).used
                        try: total_proc+=sum(x.usedGpuMemory for x in nv.nvmlDeviceGetComputeRunningProcesses(h) if x.pid in pids and x.usedGpuMemory!=nv.NVML_VALUE_NOT_AVAILABLE)
                        except Exception: pass
                        # Vulkan often unavailable in compute-process accounting; device total is separate.
                    gpu_peak=max(gpu_peak or 0,total_proc); device_peak=max(device_peak or 0,total_device)
            except (psutil.NoSuchProcess,psutil.AccessDenied): pass
            if time.perf_counter()-start>timeout:
                timed=True
                try:
                    for c in psutil.Process(p.pid).children(recursive=True): c.kill()
                except psutil.NoSuchProcess: pass
                p.kill(); break
            time.sleep(.1)
        p.wait()
    if nv:
        try: nv.nvmlShutdown()
        except Exception: pass
    log=(cwd/'generation.log').read_text(errors='replace')
    stages=[{'label':line.strip(),'seconds':float(m.group(1)),'method':'CLI reported stage timer'} for line in log.splitlines() if (m:=re.search(r'\(([\d.]+)s\)',line))]
    return {'returncode':p.returncode,'timed_out':timed,'wall_seconds':time.perf_counter()-start,'peak_rss_bytes':peak or None,'peak_gpu_process_bytes':gpu_peak if gpu_peak else None,'peak_device_used_bytes':device_peak,'memory_method':'100ms psutil process tree; NVML process/device samples when available. Unified Metal VRAM not separately measurable; null means unavailable.','samples':observations,'stage_times':stages,'stage_coverage':'Only CLI-reported stages; unreported stages are missing, not inferred.'}

def command(model,host,asset,res,seed,out):
    exe=str(resolve(host['engines'][model['engine']]['binary'])); c=[exe]
    if model['mode']=='mv': c+=['--views',str(out/'inputs'),'--pixal3d-weights','mv']
    elif model['engine']=='pixal': c+=['--sv-image',str(out/'inputs/front.png'),'--fov','0.3490658503988659']
    else:
        c+=[str(out/'inputs/front.png'),'--model',model['mode'],'--backend',host['backend'],'--steps','12']
        if model['mode']=='pixal': c+=['--fov','20'] # upstream degrees; baseline radians
    return c+['--models',str(resolve(model['weights'])),'--res',str(res),'--seed',str(seed),'--atlas','2048','--require-gpu',str(out/'raw.glb')]

def report(out,config):
    subprocess.run([os.sys.executable,str(B/'report.py'),str(out),str(config)],check=True)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--matrix',default=str(B/'matrix.yaml')); p.add_argument('--run-id'); p.add_argument('--host',default='metal'); p.add_argument('--asset'); p.add_argument('--model'); p.add_argument('--blender',default='/Applications/Blender.app/Contents/MacOS/Blender' if platform.system()=='Darwin' else 'blender'); p.add_argument('--retry-blocked',action='store_true'); p.add_argument('--execute',action='store_true',help='Execute eligible cells; default records preflight without generation'); a=p.parse_args()
    cfgpath=pathlib.Path(a.matrix).resolve(); cfg=yaml.safe_load(cfgpath.read_text())
    if cfg['settings']['steps']!=12 or cfg['settings']['atlas']!=2048: p.error('This baseline harness is calibrated for 12 steps / atlas 2048; no silent setting changes')
    if cfg['cloud']['rodin']['enabled']: p.error('Rodin adapter not yet audited; cannot enable by YAML alone')
    if a.host not in cfg['hosts']: p.error('Unknown host')
    runid=a.run_id or time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    if not re.fullmatch('[A-Za-z0-9_-]+',runid): p.error('Safe run-id required')
    out=B/'results'/runid
    prior=out/'run-manifest.json'
    if prior.exists() and json.loads(prior.read_text())['matrix_sha256']!=sha(cfgpath): p.error('Matrix changed: use a new run-id to preserve provenance')
    out.mkdir(parents=True,exist_ok=True); machine={'os':platform.platform(),'architecture':platform.machine(),'cpu_count':os.cpu_count(),'physical_memory_bytes':psutil.virtual_memory().total,'host':a.host}; rows=[]; cache={}
    dump(out/'run-manifest.json',{'schema_version':1,'run_id':runid,'matrix_sha256':sha(cfgpath),'machine':machine,'commits':{k:cfg[k] for k in ['baseline','trellis_commit','storyboard_commit']},'settings':cfg['settings'],'human_ratings':'pending','shipping_approved':False,'execution_requested':a.execute,'measurement_status':'No quality recommendation until outputs and human ratings exist.'})
    shutil.copyfile(cfgpath,out/'matrix.yaml')
    cells=itertools.product(cfg['assets'],cfg['models'],cfg['resolutions'],cfg['seeds'],cfg['hosts'])
    for assetid,modelid,res,seed,hostid in cells:
        cell=f'{assetid}_{modelid}_{res}_{seed}_{hostid}'; dest=out/cell; path=dest/'manifest.json'
        if path.exists() and not a.retry_blocked:
            rows.append(json.loads(path.read_text())); continue
        asset=cfg['assets'][assetid]; model=cfg['models'][modelid]; host=cfg['hosts'][hostid]
        row={'id':cell,'asset':assetid,'model':modelid,'resolution':res,'seed':seed,'host':hostid,'backend':host['backend'],'status':'blocked','reason':None,'settings':dict(cfg['settings'],native_postprocess='engine defaults; Pixal MV raw export default 1M, TRELLIS default 300k at 1024; common atlas 2048'),'machine':machine if hostid==a.host else None,'source_commit':cfg['baseline'] if model['engine']=='pixal' else cfg['trellis_commit'],'tri_budget':asset['tri_budget'],'nominal_height_m':asset['nominal_height_m'],'human_rating':None,'metrics':None,'measurement':None,'similarity':{'status':'blocked','reason':'CLIP/DINO evaluation encoder snapshots and trusted hashes not provided; no unapproved weights loaded.'},'cost':{'usd':None,'credits':0,'method':'No execution'}}
        reason=None
        if model['mode'] in ('sv','mv','pixal') and res==512: reason='unsupported: Pixal3D has no 512 texture flow (baseline rejects this resolution)'
        elif host.get('blocked'): reason=host['blocked']
        elif hostid!=a.host: reason='Not executed on this host; select actual provisioned host'
        elif a.asset and assetid!=a.asset or a.model and modelid!=a.model: reason='Outside selected execution subset'
        elif model.get('blocked'): reason=model['blocked']
        else:
            try:
                key=(hostid,model['engine'])
                if key not in cache: cache[key]=build_provenance(host,model['engine'])
                row['build']=cache[key]
                row['inputs']=verified_input(asset)
                if not cfg['evaluation']['dinov3_accepted_for_evaluation']: raise ValueError('DINOv3 evaluation acceptance not confirmed')
                if modelid not in cache: cache[modelid]=verified_models(model)
                row['models']=cache[modelid]
                if not a.execute: reason='Preflight only; pass --execute to run eligible verified cells'
            except Exception as e: reason=str(e)
        if reason:
            row['reason']=reason; dump(path,row); rows.append(row); continue
        dest.mkdir(parents=True,exist_ok=True); shutil.copytree(resolve(asset['input']),dest/'inputs',dirs_exist_ok=True)
        cmd=command(model,host,asset,res,seed,dest); row['command']=cmd; row['status']='running'; dump(path,row)
        try:
            env=os.environ.copy(); env['TRELLIS_DBG_MEM']='1'
            row['measurement']=sample_run(cmd,dest,cfg['settings']['timeout_seconds'],env)
            m=row['measurement']; row['cost']={'usd':m['wall_seconds']/3600*host['hourly_usd'] if host.get('hourly_usd') is not None else (0 if hostid!='cloud-gpu' else None),'credits':0,'method':'GPU hourly rate * generation wall time only; excludes provisioning/storage/cleanup; local excludes electricity'}
            if m['returncode'] or not (dest/'raw.glb').is_file(): raise RuntimeError('Generation failed or produced no GLB; see generation.log')
            clean=[a.blender,'--background','--python-exit-code','1','--python',str(B/'blender_pass.py'),'--','--input',str(dest/'raw.glb'),'--output',str(dest),'--budget',str(asset['tri_budget']),'--height',str(asset['nominal_height_m'])]
            start=time.perf_counter()
            with (dest/'cleanup.log').open('w') as f: subprocess.run(clean,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=1800)
            row['cleanup_wall_seconds']=time.perf_counter()-start; row['metrics']=json.loads((dest/'metrics.json').read_text()); row['status']='completed'; row['reason']=None
            row['assets_sha256']={str(f.relative_to(dest)):sha(f) for f in dest.rglob('*') if f.is_file() and f.suffix in ['.glb','.png']}
            if cfg['evaluation'].get('encoder_config'):
                subprocess.run([os.sys.executable,str(B/'similarity.py'),'--run',str(dest),'--config',str(resolve(cfg['evaluation']['encoder_config']))],check=True)
                row['similarity']=json.loads((dest/'similarity.json').read_text())
        except Exception as e: row.update(status='failed',reason=str(e))
        dump(path,row); rows.append(row); dump(out/'results.json',rows); report(out,cfgpath)
    for assetid,res,seed in itertools.product(cfg['assets'],cfg['resolutions'],cfg['seeds']):
        row={'id':f'{assetid}_rodin_{res}_{seed}','asset':assetid,'model':'rodin','resolution':res,'seed':seed,'host':'rodin','backend':'cloud','status':'blocked','reason':cfg['cloud']['rodin']['blocked'],'human_rating':None,'cost':{'credits':0,'usd':None},'provider_resolution_equivalent':False}; dump(out/row['id']/'manifest.json',row); rows.append(row)
    dump(out/'results.json',rows); report(out,cfgpath); print(json.dumps({'run_id':runid,'cells':len(rows),'statuses':{s:sum(r['status']==s for r in rows) for s in sorted(set(r['status'] for r in rows))},'report':str(out/'report.html')}))
if __name__=='__main__': main()
