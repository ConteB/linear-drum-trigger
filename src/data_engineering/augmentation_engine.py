import os
import numpy as np
import librosa
import soundfile as sf
import json
import random
from pathlib import Path

class AugmentationEngine:
    """
    OpenPhase Core Engine: Audio Augmentation for Drum Triggering.
    Focus: Noise injection, Gain normalization, and Metadata tracking.
    """
    def __init__(self, sr=44100):
        self.sr = sr

    def load_audio(self, path):
        data, _ = librosa.load(path, sr=self.sr, mono=True)
        return data

    def add_stochastic_noise(self, clean_audio, noise_audio, snr_range=(5, 30)):
        """
        [LAYER 3] - Random SNR noise injection.
        """
        snr_db = random.uniform(snr_range[0], snr_range[1])
        return self.add_noise(clean_audio, noise_audio, snr_db), snr_db

    def process_and_save(self, input_path, noise_path, output_path, snr_db=20, snr_range=None):
        clean = self.load_audio(input_path)
        noise = self.load_audio(noise_path)
        
        actual_snr = snr_db
        if snr_range:
            augmented, actual_snr = self.add_stochastic_noise(clean, noise, snr_range)
        else:
            augmented = self.add_noise(clean, noise, snr_db)
        
        # [LINEAR MANDATE] - Normalization to -1 dBFS
        max_val = np.max(np.abs(augmented))
        if max_val > 0:
            augmented = augmented / max_val * 0.89  # ~ -1dBFS
            
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        sf.write(output_path, augmented, self.sr)
        
        # Save Metadata (DNA Preservation)
        meta = {
            "source": input_path,
            "noise_source": noise_path,
            "applied_snr_db": actual_snr,
            "sr": self.sr
        }
        with open(output_path.replace(".wav", ".meta.json"), 'w') as f:
            json.dump(meta, f, indent=4)
            
        return output_path

if __name__ == "__main__":
    engine = AugmentationEngine()
    print("Augmentation Engine Reconstructed.")
