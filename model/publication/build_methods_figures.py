"""Publication figures for the integrated study, drawn from its stated design."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT=Path(__file__).resolve().parent/'figures'
OUT.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'svg.fonttype':'none','pdf.fonttype':42})
INK='#26343B'; EDGE='#627780'; PALE='#F1F5F6'; TEAL='#287780'

def setup(height,ymax):
    fig,ax=plt.subplots(figsize=(6.5,height))
    fig.subplots_adjust(left=.01,right=.99,bottom=.02,top=.99)
    ax.set(xlim=(0,10),ylim=(0,ymax));ax.axis('off')
    return fig,ax

def box(ax,x,y,w,h,title,body='',fs=9):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.025,rounding_size=0.06',
                 facecolor=PALE,edgecolor=EDGE,linewidth=.8))
    if body:
        ax.text(x+w/2,y+h*.73,title,ha='center',va='center',fontsize=fs,fontweight='bold',color=INK)
        ax.text(x+w/2,y+h*.32,body,ha='center',va='center',fontsize=fs-.5,color=INK,linespacing=1.25)
    else:
        ax.text(x+w/2,y+h/2,title,ha='center',va='center',fontsize=fs,color=INK,linespacing=1.3)

def arrow(ax,start,end,style='-',color=EDGE,connectionstyle='arc3'):
    ax.add_patch(FancyArrowPatch(start,end,arrowstyle='-|>',mutation_scale=9,
                  lw=.95,color=color,linestyle=style,connectionstyle=connectionstyle))

def save(fig,name):
    for ext in ['png','pdf','svg']:
        fig.savefig(OUT/(name+'.'+ext),dpi=300,facecolor='white')
    plt.close(fig)

fig,ax=setup(4.95,7.7)
box(ax,.3,6.4,4.4,1.05,'Observed information','Filed balances and contracts\nHistorical Bitcoin returns')
box(ax,5.3,6.4,4.4,1.05,'Explicit assumptions','External paths and financing access\nInstitutional settings and screens')
box(ax,.3,4.8,4.4,1.05,'Candidate policies','Financing and allocation rules\nLiquidity targets')
box(ax,5.3,4.8,4.4,1.05,'Matched futures','Same external conditions\nfor each compared policy')
arrow(ax,(2.5,6.37),(6.1,5.88))
arrow(ax,(7.5,6.37),(7.5,5.88))
box(ax,2.7,3.35,4.6,.9,'Dated corporate simulation','Transactions, balances, and claims')
arrow(ax,(2.5,4.77),(3.8,4.28));arrow(ax,(7.5,4.77),(6.2,4.28))
box(ax,2.7,1.95,4.6,.95,'Compare attainment and regret','Payment and shareholder objectives')
arrow(ax,(5,3.32),(5,2.93))
box(ax,.3,.25,2.8,1.05,'Identify vulnerabilities','Failure regions\nand transaction traces',fs=8.5)
box(ax,3.6,.25,2.8,1.05,'Freeze refinement','Protect preferred\ndistribution capacity',fs=8.5)
box(ax,6.9,.25,2.8,1.05,'Challenge evaluation','Test the fixed rule\non separate futures',fs=8.5)
arrow(ax,(3.35,1.92),(1.7,1.33));arrow(ax,(3.13,.78),(3.57,.78));arrow(ax,(6.43,.78),(6.87,.78))
ax.plot([8.3,8.3],[1.33,2.42],color=EDGE,lw=.95)
arrow(ax,(8.3,2.42),(7.33,2.42))
save(fig,'rdm_framework')

fig,ax=setup(4.65,7.1)
ax.text(.25,6.85,'A  Opening, evaluation dates, and closure extensions',fontsize=10,fontweight='bold',color=INK)
x0=.65;x31=5.55;x32=6.53;x33=7.51;x34=8.49
ax.plot([x0,x33],[5.55,5.55],lw=1.7,color=INK)
for x in [x0,x31,x33]:ax.plot(x,5.55,'o',ms=5,color=INK)
ax.text(x0,5.9,'June 2026\nOpening state',ha='left',va='bottom',fontsize=9,color=INK)
ax.text(x31,5.9,'June 2031\nFive-year endpoint',ha='center',va='bottom',fontsize=9,color=INK)
ax.text(x33+.25,5.9,'June 2033\nBeyond note maturities',ha='center',va='bottom',fontsize=9,color=INK)
ax.text(x0,4.95,'Documentary cutoff\nOctober 23, 2026',ha='left',va='top',fontsize=8.5,color=EDGE)
ax.plot([x31,x31],[5.5,4.7],lw=1,color=TEAL)
arrow(ax,(x31,4.7),(x32,4.7),color=TEAL)
ax.text((x31+x32)/2,4.38,'Issuance closed\nto June 2032',ha='center',va='top',fontsize=8.6,color=TEAL)
ax.plot([x33,x33],[5.5,3.7],lw=1,color=TEAL)
arrow(ax,(x33,3.7),(x34,3.7),color=TEAL)
ax.text(9.65,3.4,'Issuance closed to June 2034',ha='right',va='top',fontsize=8.6,color=TEAL)
ax.text(.25,2.75,'B  Recurring financing process',fontsize=10,fontweight='bold',color=INK)
for x,title in zip([.3,2.75,5.2,7.65],['Obligations\nand balances','Funding and\nallocation','Commitments\nand settlement','Payments and\nupdated balances']):
    box(ax,x,1.15,2.05,1.1,title,fs=8.7)
for x in [2.35,4.8,7.25]:arrow(ax,(x+.03,1.7),(x+.37,1.7))
ax.plot([8.675,8.675,1.325],[1.12,.65,.65],color=EDGE,lw=.95)
arrow(ax,(1.325,.65),(1.325,1.12))
ax.text(5,.25,'Updated resources and claims shape the next decision',ha='center',fontsize=8.7,color=EDGE)
save(fig,'study_timing')
print('Created two Methods figures as PNG, SVG, and PDF.')
