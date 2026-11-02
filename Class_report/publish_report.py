from pathlib import Path
import json,csv,re,html
from PIL import Image,ImageDraw,ImageFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image as RLImage,KeepTogether
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
pdfmetrics.registerFont(TTFont('Times-Roman','C:/Windows/Fonts/times.ttf'))
pdfmetrics.registerFont(TTFont('Times-Bold','C:/Windows/Fonts/timesbd.ttf'))
pdfmetrics.registerFont(TTFont('Times-Italic','C:/Windows/Fonts/timesi.ttf'))
O=Path(__file__).resolve().parent;R=O.parent
(O/'figures').mkdir(exist_ok=True)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',23);small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',19)
rs=list(csv.DictReader((R/'results/model.csv').open()))
im=Image.new('RGB',(1500,560),'white');d=ImageDraw.Draw(im);left,top,right,bottom=100,55,1450,465
for y in range(0,101,20):
 yy=bottom-y/100*(bottom-top);d.line((left,yy,right,yy),fill='#dddddd');d.text((45,yy-12),str(y),font=small,fill='black')
max_t=float(rs[-1]['time_s'])/60
for val in range(0,int(max_t)+1,20):
 x=left+val/max_t*(right-left);d.text((x-10,bottom+12),str(val),font=small,fill='black')
def points(key):return [(left+float(r['time_s'])/60/max_t*(right-left),bottom-float(r[key])/100*(bottom-top)) for r in rs[::8]]
d.polygon(points('scenario_soc_max_pct')+list(reversed(points('scenario_soc_min_pct'))),fill='#dcebef')
d.line(points('soc_pct'),fill='#126a89',width=2)
y=bottom-.2*(bottom-top);d.line((left,y,right,y),fill='#bd7040',width=2)
d.text((100,10),'Conditional usable-window state (%) - historical Australian input',font=font,fill='black');d.text((600,520),'Session time (min)',font=font,fill='black')
im.save(O/'figures/energy_trace.png')
ds=[json.loads(p.read_text()) for p in (R/'results/ml_experiments').glob('*.json')];ds.sort(key=lambda x:(x['evaluation_mode']!='within_track',x['train_event'],x['test_event']))
im=Image.new('RGB',(1500,690),'white');d=ImageDraw.Draw(im);d.text((30,12),'Held-out operating-state macro-F1 (%)',font=font,fill='black')
for i,x in enumerate(ds):
 y=70+i*61;lab=x['train_event'].replace(' Grand Prix','')+' to '+x['test_event'].replace(' Grand Prix','');v=100*x['metrics']['macro_f1'];d.text((25,y+7),lab,font=font,fill='black');d.rectangle((360,y,360+v*10,y+35),fill='#126a89' if x['evaluation_mode']=='within_track' else '#bd7040');d.text((375+v*10,y+7),f'{v:.2f}',font=font,fill='black')
d.text((360,640),'Blue: temporal holdout     Orange: cross-track transfer',font=font,fill='black');im.save(O/'figures/ml_scores.png')
src=(O/'Project_Report.md').read_text(encoding='utf-8').replace('conditional usable-window state and recorded speed','conditional usable-window state and scenario spread')
src=src.replace('energy history. Figure 2','energy history and limited scenario spread. Figure 2')
src=src.replace('histogram gradient-boosting classifier','histogram-based gradient-boosting classifier')
(O/'Project_Report.md').write_text(src,encoding='utf-8')
styles=getSampleStyleSheet();styles['Normal'].fontName='Times-Roman';styles['Normal'].fontSize=10;styles['Normal'].leading=13;styles['Normal'].spaceAfter=7
for nm in ['Heading1','Heading2','Heading3']:styles[nm].fontName='Times-Bold';styles[nm].textColor=colors.black
cell=ParagraphStyle('cell',parent=styles['Normal'],fontSize=7.4,leading=9,spaceAfter=1,wordWrap='CJK')
def clean(s):
 s=s.replace('–','-').replace('—','-').replace('−','-').replace('→',' to ').replace('≤','<=').replace('≥','>=').replace('×',' x ').replace('²','^2').replace('³','^3').replace('φ','phi')
 return html.escape(s)
flow=[];lines=src.splitlines();i=0
while i<len(lines):
 line=lines[i].strip()
 if not line:i+=1;continue
 if line.startswith('|'):
  rows=[]
  while i<len(lines) and lines[i].strip().startswith('|'):
   q=lines[i].strip()
   if not re.match(r'^\|[\s|:-]+\|$',q):rows.append([Paragraph(clean(c.strip()),cell) for c in q.strip('|').split('|')])
   i+=1
  n=len(rows[0]);tb=Table(rows,colWidths=[475/n]*n,repeatRows=1,hAlign='LEFT');tb.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf1f4')),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#bbbbbb')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));flow.extend([tb,Spacer(1,10)]);continue
 if line.startswith('!['):
  m=re.match(r'!\[(.*?)\]\((.*?)\)',line);im=Image.open(O/m[2]);flow.append(RLImage(str(O/m[2]),width=475,height=475*im.height/im.width));flow.append(Paragraph(clean(m[1]),styles['Caption'] if 'Caption' in styles else styles['Normal']))
 elif line.startswith('#'):
  n=len(line)-len(line.lstrip('#'));flow.append(Paragraph(clean(line[n:].strip()),styles['Heading'+str(min(n,3))]))
 else:flow.append(Paragraph(clean(line),styles['Normal']))
 i+=1
def page(c,doc):
 c.setFont('Times-Roman',9);c.drawRightString(535,30,str(doc.page))
pdf=SimpleDocTemplate(str(O/'Project_Report.pdf'),pagesize=(595.28,841.89),rightMargin=60,leftMargin=60,topMargin=48,bottomMargin=48,title='Mathematics-Guided ERS State Estimation and Energy Deployment Optimization for Formula 1')
grouped=[];j=0
while j<len(flow):
 item=flow[j]
 if isinstance(item,Paragraph) and item.getPlainText().startswith('Study '):
  block=[item];j+=1
  while j<len(flow) and not (isinstance(flow[j],Paragraph) and flow[j].style.name.startswith('Heading')):
   block.append(flow[j]);j+=1
  grouped.append(KeepTogether(block))
 else:grouped.append(item);j+=1
pdf.build(grouped,onFirstPage=page,onLaterPages=page)
print('PDF created')
