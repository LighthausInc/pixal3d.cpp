"""Summarize human-rated completed comparisons; no guessing from blocked results."""
import argparse, collections, json, pathlib, statistics
p=argparse.ArgumentParser(); p.add_argument('--run',required=True); p.add_argument('--ratings',required=True); p.add_argument('--port-estimate-days',type=float); p.add_argument('--minimum-meaningful-gain',type=float,default=.5); a=p.parse_args(); out=pathlib.Path(a.run); rows=json.loads((out/'results.json').read_text()); ratings=json.loads(pathlib.Path(a.ratings).read_text()); known={r['id'] for r in rows}
if ratings['run_id']!=out.name: raise ValueError('Ratings belong to another run')
if set(ratings['ratings'])-known: raise ValueError('Unknown rated cell IDs')
groups=collections.defaultdict(list)
for r in rows:
    score=ratings['ratings'].get(r['id'],{}).get('rating')
    if score is not None and (type(score)!=int or not 1<=score<=5): raise ValueError('Ratings must be integers 1–5')
    if r['status']=='completed' and score and r['metrics']['within_budget']:
        groups[(r['asset'],r['model'],r['resolution'],r['host'])].append((r,score))
summary=[]
for key,values in groups.items():
    if len({r['seed'] for r,s in values})<3: continue
    times=[r['measurement']['wall_seconds'] for r,s in values]; mem=[r['measurement']['peak_gpu_process_bytes'] for r,s in values if r['measurement']['peak_gpu_process_bytes'] is not None]
    summary.append({'asset':key[0],'model':key[1],'resolution':key[2],'host':key[3],'human_mean':statistics.mean(s for r,s in values),'human_ratings':[s for r,s in values],'mean_generation_seconds':statistics.mean(times),'mean_gpu_bytes':statistics.mean(mem) if len(mem)==len(values) else None,'seeds':[r['seed'] for r,s in values]})
recommendations={}
for asset in sorted({r['asset'] for r in rows}):
    options=[r for r in summary if r['asset']==asset]; recommendations[asset]=max(options,key=lambda r:(r['human_mean'],-r['mean_generation_seconds'])) if options else {'status':'pending','reason':'Need three completed in-budget human-rated seeds per comparable configuration'}
pairs=[]
for mv in summary:
    if not mv['model'].startswith('pixal-mv-'): continue
    suffix=mv['model'].removeprefix('pixal-mv-')
    base=next((s for s in summary if s['asset']==mv['asset'] and s['host']==mv['host'] and s['resolution']==mv['resolution'] and s['model']=='pixal-sv-'+suffix),None)
    upstream=next((s for s in summary if s['asset']==mv['asset'] and s['host']==mv['host'] and s['resolution']==mv['resolution'] and s['model']=='trellis-pixal-sv-'+suffix),None)
    if base and upstream:
        pairs.append({'asset':mv['asset'],'host':mv['host'],'resolution':mv['resolution'],'quant':suffix,'mv_minus_baseline_sv_rating':mv['human_mean']-base['human_mean'],'mv_minus_upstream_sv_rating':mv['human_mean']-upstream['human_mean'],'mv_generation_seconds':mv['mean_generation_seconds'],'upstream_sv_generation_seconds':upstream['mean_generation_seconds'],'seed_count':3})
base_decision={'status':'pending','paired_comparisons':pairs,'reason':'Need same-host three-seed rated MV and SV comparisons on both trees.'}
if pairs:
    decisive=any(x['mv_minus_upstream_sv_rating']>=a.minimum_meaningful_gain for x in pairs)
    base_decision.update(status='provisional',meaningful_gain_threshold=a.minimum_meaningful_gain,multi_view_quality_justifies_port=decisive,port_estimate_workdays=a.port_estimate_days,decision_type='Human-rated judgment, not measured fact')
    if not decisive: base_decision.update(recommended_base='LighthausInc/trellis.cpp',port_worthwhile='No decisive gain at selected rating threshold; defer port',reason='Upstream maintenance advantage from #1 plus no material rated MV gain in completed pairs.')
    elif a.port_estimate_days is None: base_decision.update(recommended_base='conditional',port_worthwhile='Quality supports a port; effort unknown',reason='Per #1: trellis.cpp plus MV port if estimated at <=10 workdays; pixal3d.cpp temporarily if >10 workdays. Obtain engineering estimate.')
    elif a.port_estimate_days<=10: base_decision.update(recommended_base='LighthausInc/trellis.cpp',port_worthwhile=True,reason='Rated MV gain meets threshold and supplied estimate is within two workweeks; retain active upstream base and port MV.')
    else: base_decision.update(recommended_base='LighthausInc/pixal3d.cpp temporarily',port_worthwhile='Defer until cost is reduced',reason='Rated MV gain meets threshold but supplied estimate exceeds two workweeks (#1 temporary-base condition).')
result={'schema_version':1,'run_id':out.name,'reviewer':ratings.get('reviewer'),'config_summaries':summary,'provisional_defaults':recommendations,'selection_rule':'Highest mean cleaned human rating, then lowest generation time; three seeds required. Manual review of individual outliers, comparable source views and missing hardware remains necessary.','base_decision':base_decision,'facts_vs_impressions':'Timings/memory/mesh metrics measured; ratings are subjective; recommendations are provisional judgments.'}
(out/'recommendations.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result,indent=2))
