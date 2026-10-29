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

# Figure 3: distribution screens use fill, hatching and line style; statistics use shape.
ps=['common_12m','retire_12m','retire_protected_12m'];labels=['Common','Retirement','Protected retirement']
fig,axes=plt.subplots(2,1,figsize=(7.2,6.5));fig.subplots_adjust(left=.25,right=.96,bottom=.20,top=.86,hspace=1.00)
rows=[]
for j,mode in enumerate(['calendar_allowance','no_exogenous_allowance']):
 y=np.arange(3)+(j-.5)*.30
 gs=[select(reg,**kw,distribution_mode=mode,policy=p) for p in ps]
 v=[select(counts,**kw,distribution_mode=mode,policy=p)['joint_success'] for p in ps]
 med=[r['floored_median_regret_per_share'] for r in gs];upper=[r['floored_p90_regret_per_share'] for r in gs]
 assert all(r['n']==110 for r in gs)
 axes[0].barh(y,v,height=.26,color='.25' if j==0 else 'white',edgecolor='black',hatch='' if j==0 else '////',lw=.7)
 for yi,n in zip(y,v):axes[0].text(n+1,yi,str(n),va='center',fontsize=10)
 axes[1].hlines(y,med,upper,color='black',lw=1.25,linestyle='solid' if j==0 else 'dashed')
 for vs,mark in [(med,'o'),(upper,'D')]:axes[1].plot(vs,y,ls='',marker=mark,ms=6,mec='black',mfc='black' if j==0 else 'white',mew=1,zorder=3)
 for p,n,m,u in zip(ps,v,med,upper):rows.append(dict(policy=p,screen=mode,joint_success=n,shared_survivors=110,median_regret=m,p90_regret=u))
csvout('Figure_3',rows)
for ax in axes:
 ax.set_yticks(range(3),labels);ax.set_ylim(2.5,-.5);ax.grid(axis='x',color='.88',lw=.6);ax.set_axisbelow(True);ax.tick_params(axis='y',length=0,pad=7);ax.spines['left'].set_visible(False)
axes[0].set_title('A  Joint success across 125 futures',loc='left',pad=12);axes[0].set_xlim(0,80);axes[0].set_xlabel('Futures meeting all three objectives')
axes[1].set_title('B  Regret among 110 shared survivors',loc='left',pad=12);axes[1].set_xlim(-1.5,42);axes[1].set_xticks([0,10,20,30,40]);axes[1].set_xlabel('Common residual regret ($ per share)')
fig.text(.25,.975,'Distribution constraints and policy comparisons',weight='bold',fontsize=12,va='top')
fig.text(.25,.937,'June 2033 · continuation valuation · 12-month liquidity targets',fontsize=9,va='top')
legend_style=dict(loc='upper center',bbox_to_anchor=(.5,-.30),frameon=False,fontsize=8,ncol=2,columnspacing=1.4,handlelength=2.2,handletextpad=.6,borderaxespad=0,labelspacing=.6)
axes[0].legend(handles=[Patch(facecolor='.25',edgecolor='black',label='Annual allowance'),Patch(facecolor='white',edgecolor='black',hatch='////',label='No added allowance')],**legend_style)
axes[1].legend(handles=[Line2D([],[],color='black',ls='solid',marker='o',mfc='black',ms=4,label='Annual allowance'),Line2D([],[],marker='o',color='black',ls='',ms=4,label='Median'),Line2D([],[],color='black',ls='dashed',marker='o',mfc='white',ms=4,label='No added allowance'),Line2D([],[],marker='D',color='black',ls='',ms=4,label='90th percentile')],**legend_style)
save(fig,'Figure_3_Policy_Comparisons')
