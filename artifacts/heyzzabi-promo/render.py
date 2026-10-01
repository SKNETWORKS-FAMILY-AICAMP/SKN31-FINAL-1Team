import sys, math, subprocess, wave, struct
from pathlib import Path
sys.path.insert(0, '/tmp/heyzzabi-video-libs')
from PIL import Image, ImageDraw, ImageFont
from functools import lru_cache

OUT=Path('/home/playdata/my-project/SKN31-FINAL-1Team/artifacts/heyzzabi-promo')
W,H,FPS=1280,720,30
FONT='/tmp/heyzzabi-NotoSansKR.ttf'
@lru_cache(None)
def font(n):
    f=ImageFont.truetype(FONT,n)
    f.set_variation_by_axes([700 if n>=40 else 450])
    return f
@lru_cache(None)
def label(s,n,c):
    f=font(n); box=f.getbbox(s); im=Image.new('RGBA',(box[2]+4,box[3]-box[1]+8)); ImageDraw.Draw(im).text((2,4-box[1]),s,font=f,fill=c); return im
def txt(im,s,x,y,n=26,c='#eaf2ff',center=False):
    a=label(s,n,c); im.paste(a,(int(x-a.width/2 if center else x),int(y)),a)
def box(d,xy,fill='#14243e',outline='#29425f',r=22): d.rounded_rectangle(tuple(map(int,xy)),r,fill=fill,outline=outline,width=2)
def ease(x): return 1-(1-max(0,min(1,x)))**3
base=Image.new('RGB',(W,H)); p=base.load()
for y in range(H):
    for x in range(W):
        glow=max(0,1-math.hypot((x-950)/1000,(y-240)/650))
        p[x,y]=(int(8+6*glow),int(16+17*glow),int(32+25*glow))

def frame(t):
    im=base.copy(); d=ImageDraw.Draw(im); idx=min(5,int(t//5)); u=t-idx*5
    for j in range(17):
        x=(j*89+t*9)%W; y=100+(j*137)%510
        d.ellipse((x,y,x+2,y+2),fill='#264764')
    box(d,(54,36,96,78),'#2563eb','#2563eb',12); txt(im,'Zz',62,43,21)
    txt(im,'헤이,짜비',111,43,24); txt(im,'HEY ZZABI  /  '+str(idx+1).zfill(2),1060,48,16,'#82a3c9')
    titles=['회의는 끝났는데,','회의록 하나로 시작하세요.','문서에서 실행할 업무까지.','AI가 추천하고, PM이 결정합니다.','팀은 중요한 일에 집중하세요.','회의가 끝나면,']
    subs=['정리할 일은 이제 시작인가요?','흩어진 논의를 다음 단계로 연결합니다.','단계별 검토와 승인으로 이어지는 업무 흐름','추천 결과를 확인하고 최종 승인하세요.','문서와 업무의 흐름을 한곳에서','실행이 시작된다.']
    enter=ease(u/0.7); off=(1-enter)*24
    txt(im,titles[idx],640,132+off,43 if idx==3 else 49,center=True)
    txt(im,subs[idx],640,204+off,27,'#9fb7d4',True)
    if idx==0:
        for j,(s,b) in enumerate([('회의록 정리','쌓여 있는 회의 메모'),('기획서 작성','다시 정리하는 결정사항'),('업무 배분','아직 비어 있는 담당자')]):
            x=130+j*350; y=323+math.sin(u*1.4+j)*9
            box(d,(x,y,x+320,y+192)); txt(im,'0'+str(j+1),x+24,y+20,21,'#f9ab7d'); txt(im,s,x+24,y+65,30); txt(im,b,x+24,y+123,19,'#8fa6c3')
        txt(im,'반복되는 정리, 이제 더 가볍게.',640,572,24,'#b5c9df',True)
    elif idx==1:
        box(d,(320,295,960,542)); txt(im,'회의록',365,322,25)
        for j,w in enumerate([380,470,315]): d.rounded_rectangle((366,378+j*28,366+w,386+j*28),4,fill='#29425f')
        progress=ease((u-0.8)/2.2); d.rounded_rectangle((365,491,915,503),6,fill='#223653')
        if progress>0: d.rounded_rectangle((365,491,365+550*progress,503),6,fill='#54dcdf')
        txt(im,'회의 내용 분석 중' if u<3 else '핵심 논의 · 결정사항 구조화',640,576,24,'#67e1e0',True)
    elif idx==2:
        names=['회의록','기획서','요구사항','업무 생성']
        for j,s in enumerate(names):
            x=95+j*285; active=u>j*.65
            if j<3: d.line((x+235,399,x+280,399),fill='#4bcfda' if u>(j+1)*.65 else '#29425f',width=3)
            box(d,(x,325,x+235,478),'#163447' if active else '#14243e','#4bcfda' if active else '#29425f')
            txt(im,'0'+str(j+1),x+24,345,20,'#67e1e0'); txt(im,s,x+117,396,29,center=True)
            if j in (1,2): txt(im,'검토 · 승인',x+117,501,19,'#9fb7d4',True)
        txt(im,'단계마다 연결되는 AI 업무 지원',640,579,24,'#b5c9df',True)
    elif idx==3:
        for j,(task,skill) in enumerate([('로그인 API 개발','Backend · Python'),('대시보드 화면 구현','Frontend · React')]):
            y=301+j*127; box(d,(175,y,1105,y+108)); txt(im,task,204,y+23,26); txt(im,skill,204,y+64,17,'#9fb7d4')
            txt(im,'AI 추천',705,y+20,17,'#67e1e0'); txt(im,'담당자 '+('A' if j==0 else 'B'),705,y+51,25)
            approved=u>2.1+j*.5; box(d,(925,y+29,1069,y+79),'#17685d' if approved else '#254463',r=14); txt(im,'승인 완료' if approved else '검토 중',997,y+42,20,center=True)
        txt(im,'업무에 맞는 담당자 추천과 사람의 최종 검토',640,579,23,'#b5c9df',True)
    elif idx==4:
        for j,s in enumerate(['할 일','진행 중','완료']):
            x=156+j*330; box(d,(x,290,x+308,548)); txt(im,s,x+22,310,23)
            for k in range(2):
                yy=366+k*80; box(d,(x+18,yy,x+290,yy+63),'#1d3550','#294b69',12)
                txt(im,[['요구사항 검토','담당 업무 확인'],['기능 구현','팀 피드백'],['기획서 승인','업무 배분']][j][k],x+34,yy+18,20)
                d.ellipse((x+263,yy+27,x+273,yy+37),fill=['#78aaff','#59dce1','#78e0b1'][j])
        txt(im,'반복 업무는 줄이고, 협업에 집중하세요.',640,580,24,'#67e1e0',True)
    else:
        box(d,(574,294,706,426),'#2563eb','#4889ff',32); txt(im,'Zz',640,312,70,center=True)
        txt(im,'헤이,짜비',640,449,54,center=True); txt(im,'개발팀을 위한 AI 스마트 그룹웨어',640,536,25,'#9fb7d4',True)
    d.line((56,664,1224,664),fill='#263c55',width=2); d.line((56,664,56+1168*t/30,664),fill='#57d6de',width=3)
    txt(im,'회의록  →  기획서  →  요구사항  →  업무 배분',56,682,15,'#7c9aba')
    txt(im,'HEY ZZABI',1118,682,15,'#7c9aba')
    # Short dip transitions preserve reading time and avoid abrupt cuts.
    fade=min(1,u/.22,(5-u)/.22)
    if fade<1: im=Image.blend(base,im,max(0,fade))
    return im

rate=44100
with wave.open(str(OUT/'music.wav'),'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
    buf=bytearray(); chords=[(130.81,164.81,196),(110,130.81,164.81),(87.31,110,130.81),(98,123.47,146.83)]
    for i in range(rate*30):
        t=i/rate; chord=chords[int(t/3.75)%4]; env=min(1,t/1.3,(30-t)/2)
        v=sum(math.sin(2*math.pi*f*t)*.038 for f in chord)
        beat=t%.46875; note=chord[int(t/.46875)%3]*4
        v+=math.sin(2*math.pi*note*t)*math.exp(-beat*11)*.065
        v+=math.sin(2*math.pi*55*beat)*math.exp(-beat*25)*.06
        buf.extend(struct.pack('<h',int(v*env*32767)))
    w.writeframes(buf)

cmd=['ffmpeg','-y','-loglevel','error','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s','1280x720','-r',str(FPS),'-i','-','-i',str(OUT/'music.wav'),'-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-t','30','-movflags','+faststart',str(OUT/'heyzzabi-promo-30s.mp4')]
proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
for i in range(30*FPS):
    im=frame(i/FPS); proc.stdin.write(im.tobytes())
    if i%150==75: im.save(OUT/f'preview-{i//150+1}.jpg')
    if i%150==0: print(f'Rendered {i//FPS}/30 seconds',flush=True)
proc.stdin.close()
if proc.wait(): raise RuntimeError('ffmpeg failed')
thumb=Image.new('RGB',(960,360))
for j in range(6):
    a=Image.open(OUT/f'preview-{j+1}.jpg').resize((320,180))
    thumb.paste(a,((j%3)*320,(j//3)*180))
thumb.save(OUT/'storyboard.jpg')
print(OUT/'heyzzabi-promo-30s.mp4',flush=True)
