"""Source-only build with provenance. Run separately on each actual host."""
import argparse, hashlib, re, json, os, pathlib, platform, shutil, subprocess, time
B = pathlib.Path(__file__).resolve().parent

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(8<<20),b''): h.update(b)
    return h.hexdigest()

def git(repo,*args): return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()

def main():
    p=argparse.ArgumentParser(); p.add_argument('--repo',required=True); p.add_argument('--engine',choices=['pixal','trellis'],required=True); p.add_argument('--backend',choices=['Metal','CUDA','Vulkan'],required=True); p.add_argument('--arch',choices=['86','89','120']); p.add_argument('--cmake',default='cmake'); p.add_argument('--ninja',default='ninja'); p.add_argument('--jobs',type=int,default=8); a=p.parse_args()
    repo=pathlib.Path(a.repo).resolve(); out=B/'evidence'; out.mkdir(exist_ok=True)
    name=f'{a.engine}-{a.backend.lower()}'; rec={'schema_version':1,'repo':str(repo),'engine':a.engine,'backend':a.backend,'commit':git(repo,'rev-parse','HEAD'),'source_commit':git(repo,'rev-parse','HEAD'),'submodules':git(repo,'submodule','status','--recursive'),'platform':platform.platform(),'commands':[],'status':'failed','source_only':True}
    expected='1f432fd3f0689c504fa1e9b15b038c33584174d1' if a.engine=='pixal' else 'c0bed38c1578f7e36e3e50c8ff1e38fa0d47583f'
    rec['source_commit']=expected
    # Bench-only commits may follow the source baseline; record source tree identity separately.
    rec['source_tree_sha256']=hashlib.sha256(''.join(f'{x}:{sha(repo/x)}\n' for x in git(repo,'ls-files','src','include','CMakeLists.txt','thirdparty').splitlines() if (repo/x).is_file()).encode()).hexdigest()
    cmake=shutil.which(a.cmake) or a.cmake; ninja=shutil.which(a.ninja)
    cmd=[cmake,'-B','build','-G','Ninja','-DCMAKE_BUILD_TYPE=Release','-DTRELLIS_WEBP=OFF']
    if ninja: cmd+=['-DCMAKE_MAKE_PROGRAM='+str(pathlib.Path(ninja).resolve())]
    if a.backend=='CUDA':
        if not a.arch: p.error('CUDA requires --arch')
        cmd+=['-DGGML_NATIVE=OFF','-DGGML_OPENMP=OFF','-DGGML_CUDA=ON','-DCMAKE_CUDA_ARCHITECTURES='+a.arch]
    elif a.backend=='Vulkan': cmd+=['-DGGML_NATIVE=OFF','-DGGML_OPENMP=OFF','-DGGML_CUDA=OFF','-DGGML_METAL=OFF','-DGGML_VULKAN=ON']
    else: cmd+=['-DGGML_CUDA=OFF','-DGGML_VULKAN=OFF']
    start=time.perf_counter()
    try:
        if git(repo,'diff','--name-only',expected,'HEAD','--','src','include','CMakeLists.txt','thirdparty'): raise RuntimeError('Source differs from pinned baseline')
        if a.backend in ('CUDA','Vulkan'):
            gpuinfo=subprocess.check_output(['nvidia-smi','--query-gpu=name,driver_version','--format=csv,noheader'],text=True); rec['gpu_info']=gpuinfo
            if any(int(line.split(',')[-1].strip().split('.')[0])<590 for line in gpuinfo.strip().splitlines()): raise RuntimeError('NVIDIA R590+ required')
        if a.backend=='CUDA':
            toolkit=subprocess.check_output(['nvcc','--version'],text=True); rec['cuda_toolkit']=toolkit
            match=re.search(r'release (\d+)\.(\d+)',toolkit)
            if not match or tuple(map(int,match.groups()))<(13,1): raise RuntimeError('CUDA 13.1+ required for this benchmark recipe')
            if os.name=='nt' and os.environ.get('VSCMD_ARG_TGT_ARCH')!='x64': raise RuntimeError('Use VS 2022 x64 Native Tools prompt')
        if git(repo,'diff','--name-only','HEAD','--','src','include','CMakeLists.txt','thirdparty'): raise RuntimeError('Dirty source: refusing unrecorded baseline changes')
        for i,c in enumerate([cmd,[cmake,'--build','build','--target','trellis-cli','-j',str(a.jobs)]]):
            rec['commands'].append(c)
            with (out/f'{name}-{i}.log').open('w') as f: subprocess.run(c,cwd=repo,stdout=f,stderr=subprocess.STDOUT,check=True)
        exe=repo/'build'/('trellis-cli.exe' if os.name=='nt' else 'trellis-cli'); cache=(repo/'build/CMakeCache.txt').read_text()
        rec.update(status='success',binary=str(exe),binary_sha256=sha(exe),cmake_cache_sha256=sha(repo/'build/CMakeCache.txt'),webp_off='TRELLIS_WEBP:BOOL=OFF' in cache,help=subprocess.check_output([str(exe),'--help'],text=True,stderr=subprocess.STDOUT))
        if not rec['webp_off']: raise RuntimeError('WEBP not disabled')
    except Exception as e: rec.update(status='failed',error=str(e))
    rec['wall_seconds']=time.perf_counter()-start
    (out/f'{name}-build.json').write_text(json.dumps(rec,indent=2)+'\n'); print(json.dumps({k:rec.get(k) for k in ['status','commit','wall_seconds','error']}))
    return 0 if rec['status']=='success' else 1
if __name__=='__main__': raise SystemExit(main())
