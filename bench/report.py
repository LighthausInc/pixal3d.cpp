"""Offline HTML report. Ratings persist locally and export as a JSON download."""
import collections, html, json, pathlib, shutil, sys
import yaml
B=pathlib.Path(__file__).resolve().parent

def make(out,cfgpath):
    cfg=yaml.safe_load(cfgpath.read_text()); rows=json.loads((out/'results.json').read_text()); groups=collections.defaultdict(list)
    for r in rows: groups[r['asset']].append(r)
    sections=[]
    def esc(x): return html.escape(str(x))
    for asset,cells in groups.items():
        ref=out/'references'/asset; src=B/cfg['assets'][asset]['input']; ref.mkdir(parents=True,exist_ok=True)
        for f in src.glob('*.png'): shutil.copyfile(f,ref/f.name)
        refs=''.join(f'<figure><img src="references/{esc(asset)}/{v}.png"><figcaption>{v}</figcaption></figure>' for v in ['front','back','left','right'] if (ref/f'{v}.png').exists())
        counts=collections.Counter(r['status'] for r in cells); completed=[r for r in cells if r['status']=='completed']; cards=[]
        for r in completed:
            views=[]
            for i in range(8):
                views.append(f'<div class="pair"><span>{i*45}°</span><img src="{esc(r["id"])}/raw/{i:02}.png"><img src="{esc(r["id"])}/cleaned/{i:02}.png"></div>')
            cards.append(f'<article><h3>{esc(r["id"])}</h3><p>Raw / cleaned, matched cameras</p><div class="turntable">'+''.join(views)+f'</div><label>Cleaned quality 1–5 <select data-rating="{esc(r["id"])}"><option value="">Unrated</option>'+''.join(f'<option>{i}</option>' for i in range(1,6))+f'</select></label><label>Review notes <input data-note="{esc(r["id"])}"></label></article>')
        tables=[]
        for r in cells:
            m=r.get('measurement') or {}; metrics=r.get('metrics') or {}; clean=metrics.get('cleaned') or {}; raw=metrics.get('raw') or {}; cost=r.get('cost') or {}; sim=r.get('similarity') or {}
            def num(k): return esc(round(m[k],3)) if m.get(k) is not None else '—'
            mem=round(m['peak_gpu_process_bytes']/2**30,3) if m.get('peak_gpu_process_bytes') is not None else '—'
            rss=round(m['peak_rss_bytes']/2**30,3) if m.get('peak_rss_bytes') is not None else '—'
            tables.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [r['model'],r['resolution'],r['seed'],r['host'],r['status'],m.get('wall_seconds','—'),mem,rss,cost.get('usd') if cost.get('usd') is not None else '—',cost.get('credits',0),raw.get('triangles','—'),clean.get('triangles','—'),clean.get('connected_components','—'),clean.get('holes_boundary_loops','—'),clean.get('uv_texel_density_px_per_m','—'),sim.get('mean_cosine','—'),r.get('reason') or ''])+f'<td><a href="{esc(r["id"])}/manifest.json">manifest</a></td></tr>')
        headers=['Model','Res','Seed','Host','State','Generation s','GPU GiB','RSS GiB','USD','Credits','Raw tris','Clean tris','Components','Hole proxy','Texel px/m','Similarity','Reason','Evidence']
        sections.append(f'<section><h2>{esc(asset)} · {cfg["assets"][asset]["tri_budget"]:,} triangle budget</h2><p>{esc(dict(counts))}</p><div class="refs">{refs}</div>'+(''.join(cards) or '<p>No generated candidates available to rate.</p>')+'<div class="table"><table><thead><tr>'+''.join(f'<th>{h}</th>' for h in headers)+'</tr></thead><tbody>'+''.join(tables)+'</tbody></table></div></section>')
    status=collections.Counter(r['status'] for r in rows)
    document='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Lighthaus 3D benchmark</title><style>
body{font:15px system-ui;background:#f4f5f2;color:#182c2d;margin:0;padding:32px}main{max-width:1500px;margin:auto}h1{font-size:34px}h2{margin-top:0}section,article{background:white;padding:24px;border-radius:12px;margin:24px 0}.refs{display:flex;gap:12px}.refs figure{margin:0;max-width:220px}.refs img,.pair img{width:100%;background:#e3e5e1}.turntable{display:flex;overflow-x:auto;gap:8px}.pair{min-width:210px;width:210px}.pair img{width:100px}label{display:inline-block;margin:16px 20px 0 0}.table{overflow:auto;margin-top:20px}table{border-collapse:collapse;font-size:12px}td,th{padding:7px;text-align:left;border-bottom:1px solid #ddd;vertical-align:top}th{white-space:nowrap}button{background:#205354;color:white;border:0;padding:12px;border-radius:6px;cursor:pointer}.note{border-left:4px solid #a2733f;padding:12px;background:#faf1e2}input{padding:8px}a{color:#205354}</style><main>
<h1>Lighthaus · 3D generation benchmark</h1>'''
    document+=f'<p>Run {esc(out.name)} · {esc(dict(status))} · <a href="run-manifest.json">Run manifest</a> · <a href="results.json">All results JSON</a></p>'
    document+='<p class="note">Measured facts: build evidence and executed cell metrics only. Blocked cells carry no inferred performance values. References are own schematic renders guided by storyboards; no clinical images. Model output, cleanup fidelity and medical accuracy remain unreviewed. No base/default recommendation until completed comparisons and David’s ratings.</p><p>Ratings judge the cleaned asset: recognizable form, silhouette, thin parts, materials and artifact severity within its triangle budget. Scores and notes are human impressions. Save ratings to JSON, then run recommend.py. Saved browser ratings are local; exporting downloads JSON without uploading it.</p><button id="export">Save ratings JSON</button> <label>Reviewer <input id="reviewer" value="David"></label>'
    document+=''.join(sections)
    document+='''<script>
const run=RUNID, key='lighthaus-bench-'+run; let ratings={}; try{ratings=JSON.parse(localStorage.getItem(key)||'{}')}catch(e){}
function save(){try{localStorage.setItem(key,JSON.stringify(ratings))}catch(e){}}
document.querySelectorAll('[data-rating]').forEach(el=>{const id=el.dataset.rating;el.value=ratings[id]?.rating||'';el.onchange=()=>{ratings[id]={...ratings[id],rating:el.value?Number(el.value):null,updated_at:new Date().toISOString()};save()}});
document.querySelectorAll('[data-note]').forEach(el=>{const id=el.dataset.note;el.value=ratings[id]?.notes||'';el.oninput=()=>{ratings[id]={...ratings[id],notes:el.value,updated_at:new Date().toISOString()};save()}});
document.getElementById('export').onclick=()=>{const data={schema_version:1,run_id:run,reviewer:document.getElementById('reviewer').value,ratings,exported_at:new Date().toISOString()};const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=run+'-ratings.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
</script></main></html>'''.replace('RUNID',json.dumps(out.name))
    (out/'report.html').write_text(document)
if __name__=='__main__': make(pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]))
