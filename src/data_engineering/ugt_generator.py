import mido
import numpy as np
import os

class UGTGenerator:
    """
    OpenPhase Core Engine: Universal Ground Truth Generator.
    Extracts high-precision onset timestamps from MIDI Drum Tracks.
    """
    def __init__(self, sr=44100):
        self.sr = sr

    def extract_onsets(self, midi_path):
        """
        Returns a dictionary of onsets (in samples) grouped by MIDI note.
        """
        mid = mido.MidiFile(midi_path)
        onsets = []
        
        # Absolute time in seconds
        current_time = 0
        for msg in mid:
            current_time += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                # Filter for standard drum map if needed, or take all
                sample_idx = int(current_time * self.sr)
                onsets.append({
                    "sample": sample_idx,
                    "time": current_time,
                    "note": msg.note,
                    "velocity": msg.velocity
                })
        
        return onsets

    def save_ugt(self, onsets, output_path):
        """
        Saves onsets as a numpy array for training.
        """
        # Simple format: [sample_index, midi_note, velocity]
        data = np.array([[o['sample'], o['note'], o['velocity']] for o in onsets])
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        np.save(output_path, data)
        return output_path

if __name__ == "__main__":
    gen = UGTGenerator()
    print("UGT Generator Reconstructed.")
