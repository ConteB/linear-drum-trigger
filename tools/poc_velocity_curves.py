"""How does the SAME MIDI velocity render to loudness across kits? (F0-T19 velocity)"""
import sys, re, subprocess, tempfile; sys.path.insert(0,'src')
from pathlib import Path
import numpy as np, soundfile as sf, mido
REPO=Path(__file__).resolve().parents[1]; SR=44100
KITS={
 'DRSKit':      ('vendor/drumgizmo/DRSKit/DRSKit_full.xml','vendor/drumgizmo/DRSKit/Midimap_full.xml'),
 'MuldjordKit': ('vendor/drumgizmo/MuldjordKit3/MuldjordKit3.xml','vendor/drumgizmo/MuldjordKit3/Midimap.xml'),
 'CrocellKit':  ('vendor/drumgizmo/CrocellKit/CrocellKit_full.xml','vendor/drumgizmo/CrocellKit/Midimap_full.xml'),
}
VELS=[16,32,48,64,80,96,112,127]
MAPRE=re.compile(r'note="(\d+)"\s+instr="([^"]+)"')
def snare_note(mm):
    m={int(n):i for n,i in MAPRE.findall(Path(mm).read_text())}
    for n,i in m.items():
        if i=='Snare': return n
    for n,i in m.items():
        if 'snare' in i.lower() and 'rim' not in i.lower() and 'rest' not in i.lower(): return n
    return None
def midi(note,vel,p):
    mf=mido.MidiFile();tr=mido.MidiTrack();mf.tracks.append(tr)
    tr.append(mido.Message('note_on',note=note,velocity=vel,channel=9,time=0))
    tr.append(mido.Message('note_off',note=note,velocity=0,channel=9,time=mf.ticks_per_beat))
    mf.save(str(p))
def render_peak(kit_xml,mm,note,vel,td):
    mid=td/f'v{vel}.mid'; midi(note,vel,mid); pref=td/f'v{vel}_ch'
    subprocess.run(['drumgizmo','-s','-i','midifile','-I',f'file={mid},midimap={mm}',
        '-o','wavfile','-O',f'file={pref},srate={SR}','-e',str(round(1.5*SR)),str(REPO/kit_xml)],
        check=True,capture_output=True,timeout=300)
    best=0.0
    for w in pref.parent.glob(pref.name+'*.wav'):
        d,_=sf.read(str(w))
        if d.ndim>1: d=d.mean(axis=1)
        seg=d[:int(0.5*SR)]
        best=max(best,float(np.sqrt(np.mean(seg**2))) if len(seg) else 0.0)
    return best
curves={}
with tempfile.TemporaryDirectory() as t:
    td=Path(t)
    for kit,(kx,mm) in KITS.items():
        sn=snare_note(REPO/mm)
        if sn is None: print(f"{kit}: no snare note"); continue
        kd=td/kit; kd.mkdir(exist_ok=True)
        curves[kit]=[render_peak(kx,REPO/mm,sn,v,kd) for v in VELS]
        print(f"{kit}: snare note={sn}")
print(f"{'vel':>4} " + "".join(f"{k:>12}" for k in curves))
for i,v in enumerate(VELS):
    print(f"{v:>4} " + "".join(f"{curves[k][i]:>12.4f}" for k in curves))
print("\nNormalized to each kit's vel=127 peak (CURVE SHAPE (RMS energy)):")
print(f"{'vel':>4} " + "".join(f"{k:>12}" for k in curves))
for i,v in enumerate(VELS):
    print(f"{v:>4} " + "".join(f"{curves[k][i]/curves[k][-1]:>12.2f}" for k in curves))
