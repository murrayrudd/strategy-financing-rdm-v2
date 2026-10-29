"""Rebuild the corrected print figure from retained results. No simulations."""
from pathlib import Path
import json, csv, hashlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from matplotlib.ticker import StrMethodFormatter

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'figures'; OUT.mkdir(exist_ok=True)
PRE=ROOT/'preview'; PRE.mkdir(exist_ok=True)
DATA=ROOT/'source_data'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.titlesize':12,
 'axes.titleweight':'bold','axes.labelsize':11,'xtick.labelsize':10,'ytick.labelsize':11,
 'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.7,
 'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','hatch.linewidth':.65,
 'savefig.facecolor':'white'})
def load(name):return json.loads((DATA/(name+'.json')).read_text())
def select(rows,**kw):
 r=[x for x in rows if all(x[k]==v for k,v in kw.items())]
 assert len(r)==1,(kw,len(r))
 return r[0]
def save(fig,name):
 fig.canvas.draw()
 renderer=fig.canvas.get_renderer()
 for t in fig.findobj(matplotlib.text.Text):
  if not t.get_visible() or not t.get_text():continue
  b=t.get_window_extent(renderer)
  assert b.x0>=-1 and b.y0>=-1 and b.x1<=fig.bbox.width+1 and b.y1<=fig.bbox.height+1,(name,t.get_text(),b)
 for ext in ['png','pdf','svg']:fig.savefig(OUT/(name+'.'+ext),dpi=600)
 fig.savefig(PRE/(name+'.png'),dpi=135)
 plt.close(fig)
def csvout(name,rows):
 with (DATA/(name+'.csv')).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
base=load('robustness_summary')
counts=load('capacity_outcome_counts');reg=load('capacity_regret_common_domain')
names={'common':'Common','dual':'Dual','capped':'Capped dual','retire':'Retirement'}
kw=dict(phase='main',horizon='2033-06-30',structure='continuation')

# Figure 3: distinct grayscale values plus hatching, exact counts inside bars.
ps=[f'{p}_{m}m' for p in names for m in (3,12)]
rows=[]
for p in ps:
 r=select(base,**kw,policy=p)
 vals=[r['joint_success'],r['cash_service']-r['joint_success'],r['n']-r['cash_service']]
 assert sum(vals)==r['n']==2000 and min(vals)>=0
 rows.append(dict(policy=p,joint_success=vals[0],cash_only=vals[1],cash_failure=vals[2]))
csvout('Payment_Outcomes',rows)
fig,ax=plt.subplots(figsize=(7.2,5.3));fig.subplots_adjust(left=.26,right=.95,bottom=.32,top=.84)
left=np.zeros(8);y=np.arange(8)
for key,col,hatch in [('joint_success','.20',''),('cash_only','.80',''),('cash_failure','white','////')]:
 v=np.array([r[key] for r in rows])
 ax.barh(y,v,left=left,height=.65,color=col,edgecolor='black',lw=.55,hatch=hatch)
 for yi,x,n in zip(y,left,v):
  ax.text(x+n/2,yi,f'{n:,}',ha='center',va='center',fontsize=9,
   color='white' if key=='joint_success' else 'black',
   bbox=dict(facecolor='white',edgecolor='none',pad=.6) if hatch else None)
 left+=v
ax.set_yticks(y,[names[p.split('_')[0]]+'  '+p.split('_')[1].replace('m',' months') for p in ps],fontsize=10);ax.invert_yaxis()
ax.set_xlim(0,2000);ax.set_xticks(np.arange(0,2001,500));ax.xaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}'))
ax.set_xlabel('Futures (2,000 per policy)');ax.tick_params(axis='y',length=0,pad=7);ax.spines['left'].set_visible(False)
for cut in [1.5,3.5,5.5]:ax.axhline(cut,color='.88',lw=.7,zorder=0)
fig.text(.245,.965,'Payment and investor outcomes',weight='bold',fontsize=13,va='top')
fig.text(.245,.915,'June 2033 · continuation valuation · annual allowance',fontsize=9,va='top')
fig.legend(handles=[Patch(facecolor='.20',edgecolor='black',label='All three objectives met'),Patch(facecolor='.80',edgecolor='black',label='Cash service; at least one investor objective unmet'),Patch(facecolor='white',edgecolor='black',hatch='////',label='Cash service fails')],loc='upper left',bbox_to_anchor=(.25,.18),frameon=False,fontsize=8,labelspacing=.45,handlelength=2.2)
save(fig,'Payment_Outcomes')

