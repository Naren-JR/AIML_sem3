from pathlib import Path
import json,re,csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
O=Path(__file__).resolve().parent;R=O.parent
(O/'figures').mkdir(exist_ok=True)
rows=list(csv.DictReader((R/'results/model.csv').open()))
t=[float(r['time_s'])/60 for r in rows]
fig,ax=plt.subplots(figsize=(9,3.6))
ax.fill_between(t,[float(r['scenario_soc_min_pct']) for r in rows],[float(r['scenario_soc_max_pct']) for r in rows],alpha=.2,color='#126a89',label='Three-scenario spread')
ax.plot(t,[float(r['soc_pct']) for r in rows],color='#126a89',lw=.8,label='Reserve-aware baseline')
ax.axhline(20,color='#a64b24',ls='--',lw=.8,label='Imposed reserve')
ax.set(xlabel='Session time (min)',ylabel='Modeled usable-window state (%)',ylim=(0,105));ax.legend(fontsize=8,ncol=3);ax.grid(alpha=.2);fig.tight_layout();fig.savefig(O/'figures/energy_trace.png',dpi=180);plt.close(fig)
ds=[json.loads(p.read_text()) for p in (R/'results/ml_experiments').glob('*.json')]
ds.sort(key=lambda d:(d['evaluation_mode']!='within_track',d['train_event'],d['test_event']))
fig,ax=plt.subplots(figsize=(9,4.5));labels=[d['train_event'].replace(' Grand Prix','')+' to '+d['test_event'].replace(' Grand Prix','') for d in ds]
ax.barh(labels,[100*d['metrics']['macro_f1'] for d in ds],color=['#126a89' if d['evaluation_mode']=='within_track' else '#bd7040' for d in ds]);ax.invert_yaxis();ax.set(xlim=(0,100),xlabel='Held-out macro-F1 (%)');ax.grid(axis='x',alpha=.2);fig.tight_layout();fig.savefig(O/'figures/ml_scores.png',dpi=180);plt.close(fig)
src=(O/'Project_Report.md').read_text(encoding='utf-8').replace('conditional energy history and recorded speed','conditional energy history').replace('conditional usable-window state and recorded speed','conditional usable-window state and scenario spread')
src=src.replace('the historical race’s conditional energy history','the historical race’s conditional energy history')
(O/'Project_Report.md').write_text(src,encoding='utf-8')
doc=Document();s=doc.sections[0];s.page_width=Inches(8.27);s.page_height=Inches(11.69);s.top_margin=Inches(.8);s.bottom_margin=Inches(.8);s.left_margin=s.right_margin=Inches(.75)
normal=doc.styles['Normal'];normal.font.name='Times New Roman';normal.font.size=Pt(11);normal.paragraph_format.space_after=Pt(6);normal.paragraph_format.line_spacing=1.1
for name,size in [('Heading 1',16),('Heading 2',13),('Heading 3',11)]:
 st=doc.styles[name];st.font.name='Times New Roman';st.font.size=Pt(size);st.font.color.rgb=RGBColor(0,0,0)
 st.paragraph_format.keep_with_next=True
footer=s.footer.paragraphs[0];footer.alignment=2
field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE');footer._p.append(field)
lines=src.splitlines();i=0
while i<len(lines):
 line=lines[i].strip()
 if not line:i+=1;continue
 if line.startswith('|'):
  group=[]
  while i<len(lines) and lines[i].strip().startswith('|'):
   ls=lines[i].strip()
   if not re.match(r'^\|[\s|:-]+\|$',ls):group.append([c.strip() for c in ls.strip('|').split('|')])
   i+=1
  tab=doc.add_table(rows=0,cols=len(group[0]));tab.style='Table Grid'
  for ri,row in enumerate(group):
   cells=tab.add_row().cells
   for c,val in zip(cells,row):
    c.text=val
    for p in c.paragraphs:
     p.paragraph_format.space_after=Pt(3)
     for run in p.runs:run.font.size=Pt(8 if len(row)>5 else 9);run.bold=ri==0
   pr=tab.rows[-1]._tr.get_or_add_trPr();pr.append(OxmlElement('w:cantSplit'))
   if ri==0:pr.append(OxmlElement('w:tblHeader'))
  doc.add_paragraph();continue
 if line.startswith('!['):
  m=re.match(r'!\[(.*?)\]\((.*?)\)',line);doc.add_picture(str(O/m[2]),width=Inches(6.6));p=doc.add_paragraph(m[1]);p.style='Caption'
 elif line.startswith('#'):
  n=len(line)-len(line.lstrip('#'));doc.add_heading(line[n:].strip(),min(n,3))
 else:doc.add_paragraph(line)
 i+=1
doc.core_properties.title='Mathematics-Guided ERS State Estimation and Energy Deployment Optimization for Formula 1'
doc.save(O/'Project_Report.docx')
print('DOCX created; paragraphs',len(doc.paragraphs),'tables',len(doc.tables))
