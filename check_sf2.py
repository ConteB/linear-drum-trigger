import sys
import os
import subprocess
import time

def check_sf2(path):
    print(f"--- Checking {os.path.basename(path)} ---")
    # Start fluidsynth in a way that we can talk to it
    proc = subprocess.Popen(["fluidsynth", "-ni", path], 
                            stdin=subprocess.PIPE, 
                            stdout=subprocess.PIPE, 
                            stderr=subprocess.PIPE, 
                            text=True)
    
    # Send commands
    # 'inst 1' lists presets for the first loaded soundfont
    stdout, stderr = proc.communicate(input="inst 1\nquit\n", timeout=10)
    
    # Print lines that look like instruments
    found = False
    for line in stdout.split('\n'):
        if line.strip() and not line.startswith("FluidSynth") and not "Copyright" in line:
            print(f"  {line.strip()}")
            found = True
    if not found:
        print("  No instruments found or output format unrecognized.")

fonts = [
    "lib/soundfonts/remo_natural.sf2",
    "lib/soundfonts/douglas_studio.sf2",
    "lib/soundfonts/sonic_session.sf2",
    "lib/soundfonts/projectsam_close.sf2"
]

for f in fonts:
    if os.path.exists(f):
        check_sf2(f)
