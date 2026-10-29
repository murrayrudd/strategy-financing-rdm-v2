"""Rebuild print-ready Figures 3, 4, B1 from retained results. No simulations."""
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

# Figure B1: landscape, aligned panels, one common scale and full readable values.
ps=[f'{p}_{m}m' for m in (3,12) for p in names]
labels=[names[p.split('_')[0]]+'  '+p.split('_')[1].replace('m',' months') for p in ps]
metrics=['cash_service','preferred_continuity','common_preservation','joint_success']
cols=['Cash\nservice','Preferred\ncontinuity','Common\nbacking','Joint\nsuccess']
fig=plt.figure(figsize=(10,6.8));rows=[]
for i,(h,s) in enumerate([(h,s) for h in ['2031-06-30','2033-06-30'] for s in ['face','continuation']]):
 row,col=divmod(i,2);ax=fig.add_axes([.205+col*.385,.56-row*.405,.355,.29])
 a=np.array([[select(base,phase='main',horizon=h,structure=s,policy=p)[m]/2000*100 for m in metrics] for p in ps])
 assert a.shape==(8,4) and np.all((a>=0)&(a<=100))
 im=ax.imshow(a,cmap='Greys',vmin=0,vmax=100,aspect='auto',interpolation='nearest')
 for iy,p in enumerate(ps):
  for ix,m in enumerate(metrics):
   val=a[iy,ix];ax.text(ix,iy,f'{val:.1f}',ha='center',va='center',fontsize=11,color='white' if val>=60 else 'black')
   rows.append(dict(horizon=h,valuation=s,policy=p,objective=m,percent=val))
 ax.set_title(f'{chr(65+i)}  June {h[:4]} · {s.title()} valuation',loc='left',pad=10,fontsize=12)
 ax.set_xticks(range(4),cols,fontsize=10);ax.set_yticks(range(8),labels if col==0 else ['']*8,fontsize=11)
 ax.tick_params(length=0,pad=7);ax.set_xticks(np.arange(-.5,4,1),minor=True);ax.set_yticks(np.arange(-.5,8,1),minor=True);ax.grid(which='minor',color='white',linewidth=.65);ax.tick_params(which='minor',length=0)
 for spine in ax.spines.values():spine.set_visible(False)
 ax.axhline(3.5,color='white',lw=2)
fig.text(.205,.965,'Objective attainment across policies and horizons',fontsize=15,weight='bold',va='top')
fig.text(.205,.915,'Percent of 2,000 exploratory futures · baseline annual allowance',fontsize=11,va='top')
cax=fig.add_axes([.31,.07,.48,.015]);cbar=fig.colorbar(im,cax=cax,orientation='horizontal',ticks=[0,25,50,75,100]);cbar.ax.tick_params(labelsize=9,length=3);cbar.outline.set_linewidth(.5)
fig.text(.205,.006,'Darker cells indicate higher attainment; these design shares are not probabilities.',fontsize=9)
csvout('Figure_B1',rows);save(fig,'Figure_B1_landscape')
