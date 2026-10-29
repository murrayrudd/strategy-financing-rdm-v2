"""Publication figures from saved outputs; no simulation or fitted changes."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

ROOT=Path(__file__).resolve().parent
MODEL=ROOT/'model/strategy_rdm_review_v2'
if not MODEL.exists():MODEL=ROOT.parent
DATA=MODEL/'results/technical_revision'
OUT=ROOT/'figures';OUT.mkdir(exist_ok=True)
def load(n):return json.loads((DATA/(n+'.json')).read_text())
def select(rs,**kw):return next(x for x in rs if all(x[k]==v for k,v in kw.items()))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold'})
colors=['#224F72','#B25A29']
def save(fig,name):
    for ext in ['png','pdf','svg']:fig.savefig(OUT/(name+'.'+ext),dpi=300,bbox_inches='tight',facecolor='white')
    plt.close(fig)

cash=load('cash_metric_diagnostics')['summary'];policies=[f'{kind}_{m}m' for m in [3,12] for kind in ['common','dual','capped','retire']]
names={'common':'Common','dual':'Dual','capped':'Capped dual','retire':'Retirement'}
labels=[names[p.split('_')[0]]+' '+p.split('_')[1].replace('m',' months') for p in policies]
fig,axes=plt.subplots(1,2,figsize=(9.5,5.7),sharex=True,sharey=True,layout='constrained')
for ax,structure,col in zip(axes,['face','continuation'],colors):
    gs=[select(cash,structure=structure,policy=p,horizon='2033-06-30')['floored'] for p in policies]
    y=np.arange(8);ax.hlines(y,[g['p10'] for g in gs],[g['p90'] for g in gs],color=col,lw=1.8)
    ax.plot([g['median'] for g in gs],y,'o',color=col,ms=5)
    ax.axvline(1,color='#777777',ls='--',lw=.8);ax.set_title(structure.title()+' valuation',pad=12)
    ax.set_xlabel('Residual gain per extra dollar');ax.grid(axis='x',alpha=.18);ax.set_xlim(-.4,10.3)
axes[0].set_yticks(range(8),labels);axes[0].invert_yaxis()
save(fig,'cash_residual')
print('Built the cash allocation figure in PNG, PDF and SVG formats')
