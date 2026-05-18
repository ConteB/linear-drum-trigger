import os
import subprocess
import logging
from pathlib import Path

# [LINEAR DSP MANDATE] - Sample Rate Consistency
DEFAULT_SR = 44100

class MidiRenderer:
    """
    OpenPhase Core Engine: MIDI to Audio synthesis using FluidSynth.
    Reliability Level: HIGH (Subprocess isolation)
    """
    def __init__(self, fluidsynth_path="fluidsynth", sr=DEFAULT_SR):
        self.fluidsynth_path = fluidsynth_path
        self.sr = sr
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
        self.logger = logging.getLogger("MidiRenderer")

    def render(self, midi_path, sf2_path, output_path):
        """
        Renders a MIDI file to WAV using a specific SoundFont.
        """
        if not os.path.exists(midi_path):
            raise FileNotFoundError(f"MIDI not found: {midi_path}")
        if not os.path.exists(sf2_path):
            raise FileNotFoundError(f"SoundFont not found: {sf2_path}")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        cmd = [
            self.fluidsynth_path,
            "-F", output_path,
            "-r", str(self.sr),
            "-g", "1.0",  # Default gain
            "-i",         # Ignore MIDI program change (force drums)
            sf2_path,
            midi_path
        ]

        self.logger.info(f"Rendering {os.path.basename(midi_path)} with {os.path.basename(sf2_path)}...")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"FluidSynth Error: {e.stderr}")
            return False

if __name__ == "__main__":
    # Smoke Test Logic
    renderer = MidiRenderer()
    # Test path resolution based on existing project structure
    test_midi = "data/temp/probe.midi"
    test_sf2 = "lib/soundfonts/fluid_gm.sf2"
    test_out = "data/temp/smoke_test/reconstruction_test.wav"
    
    if os.path.exists(test_midi) and os.path.exists(test_sf2):
        success = renderer.render(test_midi, test_sf2, test_out)
        print(f"Reconstruction Smoke Test: {'SUCCESS' if success else 'FAILED'}")
