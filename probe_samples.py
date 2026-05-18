import subprocess
import re

def probe_kit(kit_path, midi_path):
    print(f"Probing {kit_path}...")
    cmd = ["fluidsynth", "-ni", "-v", kit_path, midi_path]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        current_note = None
        mapping = {}
        
        for line in proc.stdout:
            # Look for noteon
            noteon_match = re.search(r'noteon\s+9\s+(\d+)', line)
            if noteon_match:
                current_note = int(noteon_match.group(1))
                continue
            
            # Look for sample loading/playing in verbose mode
            # fluidsynth: debug: Playing sample '...'
            sample_match = re.search(r"Playing sample '([^']+)'", line)
            if sample_match and current_note is not None:
                sample_name = sample_match.group(1)
                if current_note not in mapping:
                    mapping[current_note] = []
                if sample_name not in mapping[current_note]:
                    mapping[current_note].append(sample_name)
        
        proc.wait()
        return mapping
    except Exception as e:
        print(f"Error probing {kit_path}: {e}")
        return {}

if __name__ == "__main__":
    kits = [
        "lib/soundfonts/remo_natural.sf2",
        "lib/soundfonts/douglas_studio.sf2",
        "lib/soundfonts/sonic_session.sf2",
        "lib/soundfonts/projectsam_close.sf2"
    ]
    midi = "data/temp/probe.midi"
    
    for kit in kits:
        mapping = probe_kit(kit, midi)
        print(f"\nResults for {kit}:")
        for note in sorted(mapping.keys()):
            print(f"  Note {note}: {', '.join(mapping[note])}")
