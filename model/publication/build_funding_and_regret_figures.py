"""Funding and regret figures from frozen outputs; no new simulations or fitting."""
from pathlib import Path
import csv, hashlib, json, io
from PIL import Image
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

ROOT=Path(__file__).resolve().parent
MODEL=ROOT.parent
OUT=ROOT/'figures'; OUT.mkdir(exist_ok=True)
DATA=ROOT/'figure_data'; DATA.mkdir(exist_ok=True)
sources={}; checks={}
def load(rel):
    p=MODEL/rel
    sources[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
    return json.loads(p.read_text())
def sel(rows,**kw):
    rows=[r for r in rows if all(r[k]==v for k,v in kw.items())]
    assert len(rows)==1,(kw,len(rows))
    return rows[0]
def check(name,ok):
    checks[name]=bool(ok); assert ok,name
def csv_out(name,rows):
    with (DATA/(name+'.csv')).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def save(fig,name):
    for ext in ('png','pdf','svg'):
        buffer=io.BytesIO()
        fig.savefig(buffer,format=ext,dpi=600,bbox_inches='tight',pad_inches=.12,facecolor='white')
        data=buffer.getvalue()
        if ext=='png':Image.open(io.BytesIO(data)).verify()
        dest=OUT/(name+'.'+ext);tmp=OUT/(name+'.'+ext+'.tmp')
        tmp.write_bytes(data);tmp.replace(dest)
        assert dest.read_bytes()==data
    plt.close(fig)

BLUE='#224F72'; ORANGE='#B25A29'; LIGHT='#D7E3EB'; INK='#24343A'; GRAY='#71828A'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':13,'axes.titlesize':14,'axes.titleweight':'bold','axes.labelsize':12.5,'xtick.labelsize':11.5,'ytick.labelsize':12,'text.color':INK,'axes.labelcolor':INK,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none'})
KW={'phase':'main','structure':'continuation','horizon':'2033-06-30'}
base=load('results/analysis/robustness_summary.json')
bps=load('analysis/bitcoin_per_share_analysis.json')
reg=load('results/technical_revision/regret_metric_diagnostics.json')
fund=load('results/technical_revision/matched_funding_summary.json')
NAMES={'common':'Common','dual':'Dual','capped':'Capped dual','retire':'Retirement'}

# Figure 5: preserve the exact matched-funding domain and paired survivors.
cohort=sel(fund,**KW);ids=set(cohort['matched_future_ids'])
points=[];seen=set();fail=[]
for path in sorted((MODEL/'results/technical_revision/groups/funding').glob('*.json')):
    g=load(str(path.relative_to(MODEL)))
    if g['phase']!='main':continue
    rs=[r for r in g['rows'] if r['id'] in ids and r['structure']==KW['structure'] and r['horizon']==KW['horizon']]
    if not rs:continue
    ps={r['policy']:r for r in rs};b=ps['replay_STRC_0pct'];a=ps['replay_STRC_50pct']
    check('reference survives '+b['id'],b['cash_service'])
    seen.add(a['id'])
    if not a['cash_service']:fail.append(a['id']);continue
    points.append({'future_id':a['id'],'BPS_change_satoshis':1e8*(a['Bitcoin_per_economic_share']-b['Bitcoin_per_economic_share']),
                   'common_backing_change_dollars':a['common_backing_per_share']-b['common_backing_per_share']})
check('funding domain retained',seen==ids and len(ids)==92 and len(points)==90 and len(fail)==2)
x=np.array([r['BPS_change_satoshis'] for r in points]);y=np.array([r['common_backing_change_dollars'] for r in points])
record=sel(bps['matched_funding'],**KW,policy='replay_STRC_50pct')
check('paired Bitcoin median matches saved summary',np.isclose(np.median(x),record['BPS_difference_sats']['median']))
check('paired backing median matches saved summary',np.isclose(np.median(y),sel(cohort['policies'],policy='replay_STRC_50pct')['median_backing_difference_per_share']))
check('higher Bitcoin lower backing matches saved summary',int(((x>0)&(y<0)).sum())==record['higher_BPS_lower_backing']==29)
csv_out('figure_5_matched_funding',points)
quadrants=[((x<0)&(y>0),'Bitcoin falls\nBacking rises',GRAY),((x>0)&(y>0),'Both increase',BLUE),((x<0)&(y<0),'Both decline',GRAY),((x>0)&(y<0),'Bitcoin rises\nBacking falls',ORANGE)]
ties=(x==0)|(y==0)
check('scatter categories exhaustive',sum(int(m.sum()) for m,_,_ in quadrants)+int(ties.sum())==len(points))
fig,ax=plt.subplots(figsize=(9.6,6.3));fig.subplots_adjust(left=.115,right=.985,top=.86,bottom=.16)
ax.axvspan(0,23,ymin=0,ymax=37/105,color='#FCF4EE',zorder=0)
ax.axhline(0,color=GRAY,lw=1.0);ax.axvline(0,color=GRAY,lw=1.0)
for mask,label,color in quadrants:ax.scatter(x[mask]/1000,y[mask],c=color,s=42,alpha=.9,edgecolors='white',linewidths=.45,zorder=3)
if ties.any():ax.scatter(x[ties]/1000,y[ties],c=GRAY,marker='x',s=42,zorder=4)
ax.set_xlim(-42,23);ax.set_ylim(-37,68);ax.set_xticks([-40,-30,-20,-10,0,10,20]);ax.set_yticks([-30,-15,0,15,30,45,60])
ax.set_xlabel('Change in Bitcoin per share\n(thousand satoshis per economic common share)',labelpad=9)
ax.set_ylabel('Change in common backing ($ per share)',labelpad=9)
fig.text(.115,.975,'Matched funding can move investor outcomes in opposite directions',ha='left',va='top',weight='bold',fontsize=14.5)
fig.text(.115,.92,'50% STRC versus all-common funding · 90 paired survivors · June 2033',ha='left',va='top',fontsize=11.5)
positions=[(.025,.96),(.70,.97),(.025,.025),(.99,.025)]
for (mask,label,color),(tx,ty) in zip(quadrants,positions):
    ax.text(tx,ty,label+f'\n{int(mask.sum())} futures',transform=ax.transAxes,ha='left' if tx<.9 else 'right',va='top' if ty>.5 else 'bottom',fontsize=11,color=color,bbox={'facecolor':'white','edgecolor':'none','alpha':.9,'pad':3})
ax.grid(alpha=.12);ax.set_axisbelow(True)
save(fig,'matched_funding_tradeoff')

# Figure 7: same futures and candidates, separate regret quantities and units.
policies=[f'{kind}_{m}m' for m in (3,12) for kind in NAMES]
rows=[]
for p in policies:
    a=sel(reg,structure='continuation',horizon='2033-06-30',policy=p)['floored_regret_per_share']
    b=sel(bps['original_summary'],**KW,policy=p)['BPS_regret_sats']
    check('regret shared domain '+p,a['n']==b['n']==1740)
    rows.append({'policy':p,'shared_survivors':1740,'residual_median_dollars':a['median'],'residual_p90_dollars':a['p90'],'accumulation_median_satoshis':b['median'],'accumulation_p90_satoshis':b['p90']})
csv_out('figure_7_regret_objectives',rows)
fig,axes=plt.subplots(1,2,figsize=(10,5.7),sharey=True)
fig.subplots_adjust(left=.225,right=.985,bottom=.14,top=.77,wspace=.18)
y=np.arange(8)
for ax,metric,scale,color,title,xlabel,limit in zip(axes,['residual','accumulation'],[1,1000],[BLUE,ORANGE],['A  Common residual','B  Bitcoin accumulation'],['Regret ($ per share)','Regret (thousand satoshis per share)'],[100,40]):
    unit='dollars' if metric=='residual' else 'satoshis'
    med=np.array([r[f'{metric}_median_{unit}'] for r in rows])/scale
    upper=np.array([r[f'{metric}_p90_{unit}'] for r in rows])/scale
    ax.hlines(y,med,upper,color=color,lw=1.8)
    ax.scatter(med,y,c=color,marker='o',s=43,zorder=3);ax.scatter(upper,y,c=color,marker='D',s=38,zorder=3)
    ax.set_xlim(-limit*.025,limit);ax.set_xlabel(xlabel,labelpad=9);ax.set_title(title,loc='left',pad=13)
    ax.axvline(0,color=GRAY,lw=.7);ax.axhline(3.5,color='#CED5D9',lw=.8);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    ax.tick_params(axis='y',length=0,pad=8);ax.spines['left'].set_visible(False)
axes[0].set_yticks(y,[NAMES[p.split('_')[0]]+'  '+p.split('_')[1].replace('m',' months') for p in policies]);axes[0].invert_yaxis()
fig.text(.225,.975,'Policy comparisons depend on the regret measure',ha='left',va='top',weight='bold',fontsize=15.5)
fig.text(.225,.92,'June 2033 · same 1,740 shared survivors · lower regret is preferable',ha='left',va='top',fontsize=11.5)
fig.legend(handles=[Line2D([0],[0],marker='o',color=INK,ls='',label='Median'),Line2D([0],[0],marker='D',color=INK,ls='',label='90th percentile')],loc='upper left',bbox_to_anchor=(.218,.885),ncol=2,frameon=False,fontsize=11.5)
save(fig,'regret_objectives')

report={'passed':all(checks.values()),'checks':checks,'source_sha256':sources,'figure_5':{'matched_futures':92,'paired_survivors':90,'alternative_cash_failures':fail,'zero_axis_points':int(ties.sum()),'quadrants':{label.replace('\n','; '):int(mask.sum()) for mask,label,_ in quadrants}},'simulation_changes':False,'figures':['matched_funding_tradeoff','regret_objectives']}
(ROOT/'results_figures_verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':True,'checks':len(checks),'figure_5':report['figure_5']}))
