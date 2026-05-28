import sys, subprocess, tempfile; sys.path.insert(0,'src')
from pathlib import Path
import numpy as np, soundfile as sf, mido
REPO=Path(__file__).resolve().parents[1]; KIT=REPO/'vendor/drumgizmo/DRSKit/DRSKit_full.xml'; SR=44100
MM={42:'Hihat_closed',44:'Hihat_foot',46:'Hihat_open'}
def midimap(p):
    p.write_text('<midimap>\n'+'\n'.join(f'<map note="{n}" instr="{i}"/>' for n,i in MM.items())+'\n</midimap>\n')
def build(events,p):
    mf=mido.MidiFile();tr=mido.MidiTrack();mf.tracks.append(tr);tpb=mf.ticks_per_beat
    msgs=[]
    for t,n in events:
        on=round(t/0.5*tpb)
        msgs.append((on,mido.Message('note_on',note=n,velocity=110,channel=9)))
        msgs.append((on+tpb//4,mido.Message('note_off',note=n,velocity=0,channel=9)))
    msgs.sort(key=lambda x:x[0]);prev=0
    for tk,m in msgs: m.time=tk-prev;prev=tk;tr.append(m)
    mf.save(str(p))
def render(midi,mm,pref):
    subprocess.run(['drumgizmo','-s','-i','midifile','-I',f'file={midi},midimap={mm}',
        '-o','wavfile','-O',f'file={pref},srate={SR}','-e',str(round(2.5*SR)),str(KIT)],
        check=True,capture_output=True,timeout=300)
def hihat(pref):
    h=sorted(pref.parent.glob(pref.name+'Hihat-*.wav'))[0]; d,_=sf.read(str(h))
    return d.mean(axis=1) if d.ndim>1 else d
def rms(x,a,b): s=x[int(a*SR):int(b*SR)]; return float(np.sqrt(np.mean(s**2))) if len(s) else 0
with tempfile.TemporaryDirectory() as t:
    td=Path(t); mm=td/'mm.xml'; midimap(mm)
    cases={'open_alone':[(0.0,46)],'open_then_closed':[(0.0,46),(0.5,42)],
           'open_then_pedal':[(0.0,46),(0.5,44)],'open_then_open':[(0.0,46),(0.5,46)]}
    base=None
    print(f"{'case':<14}{'RMS[0.62-0.95]s':>16}   verdict")
    for name,ev in cases.items():
        mid=td/f'{name}.mid'; build(ev,mid); pref=td/f'{name}_ch'; render(mid,mm,pref)
        r=rms(hihat(pref),0.62,0.95)
        if name=='open_alone': base=r
        v='(reference)' if name=='open_alone' else ('CHOKES open ✓' if r<base*0.4 else 'open STILL RINGS ✗')
        print(f"{name:<14}{r:>16.5f}   {v}")
