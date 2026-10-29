"""Matched RDM summaries and scenario discovery with untouched future holdout."""
from pathlib import Path
import json,math,itertools,warnings,hashlib
import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier,export_text
from sklearn.metrics import balanced_accuracy_score,precision_score,recall_score
from rdm_design import POLICIES
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'results/analysis'
OUTCOMES=['cash_service','preferred_continuity','common_preservation','joint_success']

def write(name,value):
    OUT.mkdir(parents=True,exist_ok=True);p=OUT/name;tmp=p.with_suffix('.partial')
    def default(x):
        if isinstance(x,(np.integer,np.floating,np.bool_)):return x.item()
        if isinstance(x,set):return sorted(x)
        raise TypeError(str(type(x)))
    tmp.write_text(json.dumps(value,indent=2,default=default,allow_nan=False));tmp.replace(p)

def load(phase):
    groups=[json.loads(line) for line in (ROOT/f'results/rdm/{phase}.jsonl').open()]
    rows=[];features=[]
    for g in groups:
        features.append({'id':g['id'],'split':g['split'],**g['features']})
        for r in g['rows']:rows.append({**r,'split':g['split'],'phase':phase})
    return pd.DataFrame(rows),pd.DataFrame(features).set_index('id').sort_index()

def frame(features):
    x=features.drop(columns='split').copy()
    for c in x:
        if x[c].dtype==bool or x[c].dtype==object:x[c]=pd.Categorical(x[c].astype(str))
    return x

def metrics(mask,y):
    mask=np.asarray(mask,bool);y=np.asarray(y,bool);hits=int((mask&y).sum());inside=int(mask.sum());cases=int(y.sum())
    return {'n':len(y),'failures':cases,'inside':inside,'hits':hits,
      'density':hits/inside if inside else None,'coverage':hits/cases if cases else None,'mass':inside/len(y)}

def mask_rules(x,rules):
    total=np.zeros(len(x),bool)
    for rule in rules:
        m=np.ones(len(x),bool)
        for c,b in rule.items():
            if 'allowed' in b:m&=x[c].astype(str).isin(b['allowed']).to_numpy()
            else:
                if b['lo'] is not None:m&=x[c].to_numpy()>=b['lo']
                if b['hi'] is not None:m&=x[c].to_numpy()<=b['hi']
        total|=m
    return total

def fit_boxes(x,y):
    from ema_workbench.analysis import prim
    y=np.asarray(y,bool)
    if not y.any() or y.all():return [],'constant_target'
    with warnings.catch_warnings():
        warnings.simplefilter('ignore');p=prim.Prim(x.reset_index(drop=True),y,peel_alpha=.05,paste_alpha=.05,mass_min=.05)
        rules=[]
        for _ in range(3):
            b=p.find_box()
            if b is None:break
            tr=b.peeling_trajectory;ok=tr[(tr.res_dim<=4)&(tr.mass>=.05)&(tr.density>=y.mean()+.025)]
            if ok.empty:break
            qualified=ok[ok.density>=.9]
            pick=(qualified.sort_values(['coverage','density'],ascending=False) if not qualified.empty else ok.sort_values(['density','coverage'],ascending=False)).index[0]
            b.select(int(pick));limits=b.box_lims[int(pick)];rule={}
            for c in x:
                lo,hi=limits[c].iloc[0],limits[c].iloc[1];a,z=p.box_init[c].iloc[0],p.box_init[c].iloc[1]
                if isinstance(lo,set):
                    if lo!=a:rule[c]={'allowed':sorted(str(v) for v in lo)}
                elif lo!=a or hi!=z:rule[c]={'lo':float(lo) if lo!=a else None,'hi':float(hi) if hi!=z else None}
            if not rule:break
            rules.append(rule)
        return rules,'fitted' if rules else 'no_informative_box'

def jaccard(a,b):
    a,b=np.asarray(a,bool),np.asarray(b,bool);union=int((a|b).sum())
    return int((a&b).sum())/union if union else None

def summaries(main,challenge,cash,features):
    allrows=pd.concat([main,challenge],ignore_index=True);keys=['phase','horizon','structure','policy'];summary=[]
    for k,g in allrows.groupby(keys,sort=True):
        summary.append({**dict(zip(keys,k)),'n':len(g),**{o:int(g[o].sum()) for o in OUTCOMES},
          'median_Bitcoin_units':float(g.Bitcoin_units.median()),'median_common_backing_survivors':float(g.common_backing_per_share.median()) if g.common_backing_per_share.notna().any() else None,
          'common_backing_survivors':int(g.common_backing_per_share.notna().sum())})
    write('robustness_summary.json',summary)
    pairs=[]
    for key,g in main.groupby(['horizon','structure']):
        for outcome in OUTCOMES:
            pivot=g.pivot(index='id',columns='policy',values=outcome)
            for a,b in itertools.combinations(pivot.columns,2):
                pairs.append({'horizon':key[0],'structure':key[1],'outcome':outcome,'policy_a':a,'policy_b':b,'n':len(pivot),
                 'a_only':int((pivot[a]&~pivot[b]).sum()),'b_only':int((pivot[b]&~pivot[a]).sum()),'both':int((pivot[a]&pivot[b]).sum()),'neither':int((~pivot[a]&~pivot[b]).sum())})
    write('paired_policy_comparisons.json',pairs)
    sensitivity=[]
    for key,g in main.groupby(['horizon','policy']):
        for o in OUTCOMES:
            v=g.pivot(index='id',columns='structure',values=o)
            sensitivity.append({'horizon':key[0],'policy':key[1],'outcome':o,'n':len(v),'changed':int((v.face!=v.continuation).sum()),
              'continuation_only':int((v.continuation&~v.face).sum()),'face_only':int((v.face&~v.continuation).sum())})
    write('structural_sensitivity.json',sensitivity)
    sizes=[]
    for key,g in main.groupby(['horizon','structure','policy']):
        small=g[g.id.str[-4:].astype(int)<1000]
        sizes.append({'horizon':key[0],'structure':key[1],'policy':key[2],**{o:{'first_1000':float(small[o].mean()),'all_2000':float(g[o].mean()),'absolute_difference':abs(float(small[o].mean()-g[o].mean()))} for o in OUTCOMES}})
    write('sample_size_comparison.json',sizes)
    joined=main.merge(features[['legal_regime']],left_on='id',right_index=True);strata=[]
    for key,g in joined.groupby(['horizon','structure','policy','legal_regime']):
        strata.append({**dict(zip(['horizon','structure','policy','legal_regime'],key)),'n':len(g),**{o:int(g[o].sum()) for o in OUTCOMES}})
    write('legal_regime_stratification.json',strata)
    regret=[]
    for key,g in main.groupby(['horizon','structure']):
        p=g.pivot(index='id',columns='policy',values='common_backing_per_share').dropna()
        for policy in p:
            r=p.max(axis=1)-p[policy]
            regret.append({'horizon':key[0],'structure':key[1],'policy':policy,'common_survivor_futures':len(p),
              'median_regret_usd_per_share':float(r.median()) if len(r) else None,'p90_regret':float(r.quantile(.9)) if len(r) else None,'max_regret':float(r.max()) if len(r) else None})
    write('conditional_regret.json',regret)
    perturb=[]
    keycols=['id','horizon','structure','policy'];paired=cash.merge(main,on=keycols,suffixes=('_extra','_base'),validate='one_to_one')
    for key,g in paired.groupby(['horizon','structure','policy']):
        survivors=g[g.cash_service_extra & g.cash_service_base];ratio=(survivors.common_backing_per_share_extra-survivors.common_backing_per_share_base)*371603000/1e8
        perturb.append({'horizon':key[0],'structure':key[1],'policy':key[2],'n':len(g),'both_survive':len(survivors),
          **{o:{'rescued':int((g[o+'_extra']&~g[o+'_base']).sum()),'lost':int((~g[o+'_extra']&g[o+'_base']).sum())} for o in OUTCOMES},
          'finite_backing_gain_per_extra_dollar':{'median':float(ratio.median()) if len(ratio) else None,'p10':float(ratio.quantile(.1)) if len(ratio) else None,'p90':float(ratio.quantile(.9)) if len(ratio) else None}})
    write('marginal_cash.json',perturb)
    # Use the identical future set for the cross-policy cash-value figure.
    # Policy-specific paired-survivor results above remain available separately.
    common_cash=[]
    for h,g in paired.groupby('horizon'):
        survives=(g.cash_service_extra & g.cash_service_base).groupby(g.id).all()
        ids=sorted(survives.index[survives]);matched=g[g.id.isin(ids)]
        assert g.groupby('id').size().eq(16).all()
        for structure,policy in itertools.product(['face','continuation'],[p.name for p in POLICIES]):
            v=matched[(matched.structure==structure)&(matched.policy==policy)]
            ratio=(v.common_backing_per_share_extra-v.common_backing_per_share_base)*371603000/1e8
            common_cash.append({'horizon':h,'structure':structure,'policy':policy,'selected_futures':125,'common_survivor_futures':len(ids),'future_ids':ids,
              'domain':'Same futures surviving under all eight policies, both valuations, and both opening cash endowments',
              'finite_backing_gain_per_extra_dollar':{'median':float(ratio.median()) if len(ratio) else None,'p10':float(ratio.quantile(.1)) if len(ratio) else None,'p90':float(ratio.quantile(.9)) if len(ratio) else None}})
    write('marginal_cash_common_domain.json',common_cash)

    write('execution_summary.json',{'main_simulations':len(main)//2,'challenge_simulations':len(challenge)//2,'cash_simulations':len(cash)//2,
      'main_futures':main.id.nunique(),'challenge_futures':challenge.id.nunique(),'cash_futures':cash.id.nunique(),
      'max_cash_reconciliation_residual':float(pd.concat([main,challenge,cash]).max_cash_residual.max()),
      'censored_endpoint_rows':int(pd.concat([main,challenge,cash]).censored.sum()),'probabilistic_interpretation':False})
    allrows.drop(columns=['metrics','first_preferred_miss','debt_shortfall','operating_shortfall']).to_csv(OUT/'outcomes.csv',index=False)
    quotes=[]
    for key,g in main.groupby(['horizon','structure','policy']):
        quotes.append({'horizon':key[0],'structure':key[1],'policy':key[2],'n':len(g),
          'quote_at_least_opening':int((g.cash_service & (g.common_quote>=86.93)).sum()),
          'backing_at_least_opening':int(g.common_preservation.sum()),
          'interpretation':'Conditional market quote and asset backing answer different questions; neither is a forecast or probability.'})
    write('common_value_metrics.json',quotes)

def closure_tails(main):
    results=[]
    for year in (2031,2033):
        tail,_=load('tail'+str(year));opening=main[main.horizon==f'{year}-06-30']
        paired=tail.merge(opening,on=['id','structure','policy'],suffixes=('_tail','_opening'),validate='one_to_one')
        for key,g in paired.groupby(['structure','policy']):
            eligible=g[g.cash_service_opening]
            results.append({'closure_start':f'{year}-06-30','closure_end':f'{year+1}-06-30','structure':key[0],'policy':key[1],
              'selected_futures':len(g),'survived_to_closure':len(eligible),'survived_extra_year':int(eligible.cash_service_tail.sum()),
              'lost_cash_service':int((~eligible.cash_service_tail).sum()),'preferred_continuity_extra_year':int(eligible.preferred_continuity_tail.sum()),
              'scope':'Preselected 125-future subset; continuation conditions differ from a permanently self-financing corporation.'})
    write('closure_tail_results.json',results)

_DISCOVERY_DATA=None

def _init_discovery(main,challenge,fm,fc):
    global _DISCOVERY_DATA
    xm,xc=frame(fm),frame(fc);train=fm.index[fm.split=='train'];hold=fm.index[fm.split=='holdout']
    _DISCOVERY_DATA=(main,challenge,fm,fc,xm,xc,train,hold)

def _discover_one(task):
    main,challenge,fm,fc,xm,xc,train,hold=_DISCOVERY_DATA
    h,structure,policy,outcome=task;key='|'.join(task)
    m=main[(main.horizon==h)&(main.structure==structure)&(main.policy==policy)].set_index('id')
    c=challenge[(challenge.horizon==h)&(challenge.structure==structure)&(challenge.policy==policy)].set_index('id')
    y=(~m[outcome]).reindex(fm.index);yc=(~c[outcome]).reindex(fc.index);yt=y.loc[train].to_numpy();yh=y.loc[hold].to_numpy()
    rules,status=fit_boxes(xm.loc[train],yt)
    rec={'key':key,'horizon':h,'structure':structure,'policy':policy,'failure_of':outcome,'status':status,'rules':rules,
      'train':metrics(mask_rules(xm.loc[train],rules),yt),'holdout':metrics(mask_rules(xm.loc[hold],rules),yh),'challenge':metrics(mask_rules(xc,rules),yc)}
    # CART is a separate diagnostic with fixed complexity; no test-set tuning.
    enc=pd.get_dummies(pd.concat([xm,xc],ignore_index=True),dtype=float);em=enc.iloc[:len(xm)].set_axis(xm.index);ec=enc.iloc[len(xm):].set_axis(xc.index)
    tree=DecisionTreeClassifier(max_depth=3,min_samples_leaf=45,random_state=4411).fit(em.loc[train],yt)
    rec['cart_rules']=export_text(tree,feature_names=list(em.columns),decimals=3)
    rec['cart']={}
    for label,xx,yy in [('holdout',em.loc[hold],yh),('challenge',ec,yc.to_numpy())]:
        pred=tree.predict(xx);rec['cart'][label]={**metrics(pred,yy),'balanced_accuracy':float(balanced_accuracy_score(yy,pred)) if len(np.unique(yy))==2 else None}
    if h=='2033-06-30' and policy in ('common_12m','dual_12m','retire_12m'):
        masks=[];counts={};rng=np.random.default_rng(99107)
        for _ in range(12):
            sub=rng.choice(train,size=1200,replace=False);rr,_=fit_boxes(xm.loc[sub],y.loc[sub].to_numpy());masks.append(mask_rules(xm.loc[hold],rr))
            for name in {c for r in rr for c in r}:counts[name]=counts.get(name,0)+1
        js=[jaccard(a,b) for a,b in itertools.combinations(masks,2)];valid=[j for j in js if j is not None]
        half,_=fit_boxes(xm.loc[train[:750]],y.loc[train[:750]].to_numpy())
        rec['stability']={'subsamples':12,'median_holdout_membership_Jaccard':float(np.median(valid)) if valid else None,
          'empty_union_pairs':len(js)-len(valid),'variable_selection_counts':counts,'half_training_Jaccard':jaccard(mask_rules(xm.loc[hold],half),mask_rules(xm.loc[hold],rules))}
    adequate=all(rec[k]['inside']>=20 and rec[k]['failures']>=20 for k in ('holdout','challenge'))
    quality=adequate and all((rec[k]['density'] or 0)>=.8 and (rec[k]['coverage'] or 0)>=.7 for k in ('holdout','challenge'))
    rec['validation_screen_pass']=bool(quality)
    rec['stability_screen_pass']=(rec['stability']['median_holdout_membership_Jaccard'] is not None and rec['stability']['median_holdout_membership_Jaccard']>=.6) if 'stability' in rec else None
    return rec

def discovery(main,challenge,fm,fc):
    from concurrent.futures import ProcessPoolExecutor,as_completed
    import multiprocessing,os
    provenance={'analysis_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'input_sha256':{name:hashlib.sha256((ROOT/f'results/rdm/{name}.jsonl').read_bytes()).hexdigest() for name in ('main','challenge')}}
    pp=OUT/'discovery_identity.json'
    if pp.exists():assert json.loads(pp.read_text())==provenance,'Discovery inputs changed'
    else:write('discovery_identity.json',provenance)
    records=json.loads((OUT/'scenario_discovery.json').read_text()) if (OUT/'scenario_discovery.json').exists() else []
    done={r['key'] for r in records}
    tasks=[t for t in itertools.product(['2031-06-30','2033-06-30'],['face','continuation'],[p.name for p in POLICIES],OUTCOMES[:3]) if '|'.join(t) not in done]
    context=multiprocessing.get_context('fork' if 'fork' in multiprocessing.get_all_start_methods() else 'spawn')
    with ProcessPoolExecutor(max_workers=int(os.environ.get('RDM_ANALYSIS_WORKERS','8')),mp_context=context,initializer=_init_discovery,initargs=(main,challenge,fm,fc)) as pool:
        for rec in pool.map(_discover_one,tasks,chunksize=1):
            records.append(rec);records.sort(key=lambda r:r['key']);write('scenario_discovery.json',records)
            print('discovery',len(records),'/96',rec['key'],flush=True)
    write('discovery_readiness.json',{'models':len(records),'validation_screen_pass':sum(r['validation_screen_pass'] for r in records),
      'stability_models':sum('stability' in r for r in records),'stability_screen_pass':sum(r.get('stability_screen_pass') is True for r in records),
      'joint_validation_stability_pass':sum(r['validation_screen_pass'] and r.get('stability_screen_pass') is True for r in records),
      'interpretation':'Screening failures limit claims about stable, compact failure regions. They do not invalidate completed simulation comparisons or justify post-hoc threshold changes.'})

def main():
    import os
    write('analysis_environment.json',{'python_hash_seed':os.environ.get('PYTHONHASHSEED'),'worker_count':int(os.environ.get('RDM_ANALYSIS_WORKERS','8')),'selection':'Prespecified PRIM/CART settings; parallelization does not change per-model fitting.'})
    identity={'analysis_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'run_identity_sha256':hashlib.sha256((ROOT/'results/rdm/run_identity.json').read_bytes()).hexdigest(),
      'data_sha256':{name:hashlib.sha256((ROOT/f'results/rdm/{name}.jsonl').read_bytes()).hexdigest() for name in ('main','challenge','cash','tail2031','tail2033')}}
    ip=OUT/'analysis_identity.json'
    if ip.exists() and json.loads(ip.read_text())!=identity:raise RuntimeError('Analysis or input identity changed; preserve and replace the analysis directory before refitting')
    write('analysis_identity.json',identity)
    main,fm=load('main');challenge,fc=load('challenge');cash,_=load('cash')
    assert main.id.nunique()==2000 and challenge.id.nunique()==512 and cash.id.nunique()==125
    assert len(main)==64000 and len(challenge)==16384 and len(cash)==4000
    assert not set(fm.index)&set(fc.index)
    assert (fm.split=='train').sum()==1500 and (fm.split=='holdout').sum()==500
    for df in (main,challenge,cash):
        assert df.groupby('id').path_sha256.nunique().max()==1
        assert not df.duplicated(['id','horizon','structure','policy']).any()
    summaries(main,challenge,cash,fm);closure_tails(main);discovery(main,challenge,fm,fc)

if __name__=='__main__':
    import os,sys
    if os.environ.get('PYTHONHASHSEED')!='0':
        os.environ['PYTHONHASHSEED']='0'
        os.execv(sys.executable,[sys.executable,str(Path(__file__).resolve()),*sys.argv[1:]])
    main()
