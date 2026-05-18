import os
import wave
import glob

datasets = {
    "ENST-Drums (Raw)": "data/raw_dataset/enst_drums/*.wav",
    "ENST-Drums (Slices)": "data/processed_dataset/enst_slices/*.wav",
    "StemGMD (Raw)": "data/raw_dataset/stemgmd/*.wav",
    "StemGMD (Slices)": "data/processed_dataset/stemgmd_slices/*.wav",
    "AudioSet Caos": "data/raw_dataset/audioset_caos/*.wav",
    "MDB Drums Sacred": "data/raw_dataset/mdb_drums_sacred/*.wav"
}

def analyze_wav(filepath):
    try:
        with wave.open(filepath, 'rb') as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            duration = nframes / float(framerate)
            return f"CH: {channels}, SR: {framerate}Hz, BitDepth: {sampwidth*8}bit, Dur: {duration:.2f}s"
    except Exception as e:
        return f"Error: {e}"

print("=== DATASET AUDIT REPORT ===\n")
for name, pattern in datasets.items():
    print(f"--- {name} ---")
    files = sorted(glob.glob(pattern))
    if not files:
        print("No files found.\n")
        continue
    
    print(f"Total files: {len(files)}")
    # Analyze up to 3 files as samples
    for f in files[:3]:
        info = analyze_wav(f)
        print(f"  {os.path.basename(f)}: {info}")
    print()
