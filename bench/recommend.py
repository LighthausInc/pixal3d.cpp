"""Summarize human-rated completed comparisons; no guessing from blocked results."""
import argparse, collections, json, pathlib, statistics
p=argparse.ArgumentParser(); p.add_argument('--run',required=True); p.add_argument('--ratings',required=True); a=p.parse_args(); out=pathlib.Path(a.run); rows=json.loads((out/'results.json').read_text()); ratings=json.loads(pathlib.Path(a.ratings).read_text()); known={r['id'] for r in rows}
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
result={'schema_version':1,'run_id':out.name,'reviewer':ratings.get('reviewer'),'config_summaries':summary,'provisional_defaults':recommendations,'selection_rule':'Highest mean cleaned human rating, then lowest generation time; three seeds required. Manual review of individual outliers, comparable source views and missing hardware remains necessary.','base_decision':{'status':'pending','reason':'Compare same-host SV on both trees and MV on baseline; judge cleaned quality gain, variance, time/memory. Port effort needs engineering estimate; generation data cannot establish a two-week implementation cost.'},'facts_vs_impressions':'Timings/memory/mesh metrics measured; ratings are subjective; recommendations are provisional judgments.'}
(out/'recommendations.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result,indent=2))
