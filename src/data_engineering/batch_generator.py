import os
import random
import mido
import numpy as np
import soundfile as sf
import json
from datetime import datetime
from src.data_engineering.midi_renderer import MidiRenderer
from src.data_engineering.augmentation_engine import AugmentationEngine
from src.data_engineering.ugt_generator import UGTGenerator

class BatchGenerator:
    # [LINEAR ENGINEERING STANDARD] - Unified Drum Classes
    DRUM_CLASSES = {
        "Kick": [35, 36],
        "Snare": [38, 40],
        "HH": [42, 44, 46, 49, 51],
        "Others": [] # Filled dynamically
    }

    def __init__(self, base_dir="."):
        self.base_dir = base_dir
        self.renderer = MidiRenderer()
        self.augmenter = AugmentationEngine()
        self.ugt_gen = UGTGenerator()
        self.out_dir = os.path.join(base_dir, "data/temp/augmentation_comparison")
        os.makedirs(self.out_dir, exist_ok=True)

    def filter_midi(self, input_midi, output_midi, allowed_notes):
        mid = mido.MidiFile(input_midi)
        new_mid = mido.MidiFile()
        for track in mid.tracks:
            new_track = mido.MidiTrack()
            for msg in track:
                if msg.type in ['note_on', 'note_off']:
                    if msg.note in allowed_notes:
                        new_track.append(msg)
                else:
                    new_track.append(msg)
            new_mid.tracks.append(new_track)
        new_mid.save(output_midi)

    def get_all_notes_in_midi(self, midi_path):
        mid = mido.MidiFile(midi_path)
        notes = set()
        for msg in mid:
            if msg.type == 'note_on':
                notes.add(msg.note)
        return notes

    def run_scenario(self, name, midi_path, sf2_list, noise_path=None, snr=20, notes=None):
        """
        Unified Scenario Executor for Drum-Trigger Pipeline (Recovery Patch).
        """
        print(f"  [SCENARIO] {name}...")
        active_midi = midi_path
        if notes:
            active_midi = os.path.join(self.out_dir, f"tmp_{name}_filtered.midi")
            self.filter_midi(midi_path, active_midi, notes)
        if len(sf2_list) == 1:
            self.run_s1_s2(name, active_midi, sf2_list[0], noise_path, snr)
        else:
            h_map = {"Kick": sf2_list[0], "Snare": sf2_list[1] if len(sf2_list) > 1 else sf2_list[0], "HH": sf2_list[0], "Others": sf2_list[0]}
            self.run_s3_hybrid(name, active_midi, h_map, noise_path, snr)
        if notes and os.path.exists(active_midi):
            os.remove(active_midi)

    def run_s1_s2(self, strategy_id, midi_path, sf2_path, noise_path=None, snr=20):
        """
        S1: Standard Full Kit Rendering
        S2: Full Kit with specific naming/tracking
        """
        midi_name = os.path.basename(midi_path).replace(".midi", "")
        sf2_name = os.path.basename(sf2_path).replace(".sf2", "")
        prefix = f"{strategy_id}_{sf2_name}_{midi_name}"
        
        clean_path = os.path.join(self.out_dir, f"{prefix}_clean.wav")
        self.renderer.render(midi_path, sf2_path, clean_path)
        
        final_path = os.path.join(self.out_dir, f"{prefix}.wav")
        if noise_path:
            self.augmenter.process_and_save(clean_path, noise_path, final_path, snr_db=snr)
        else:
            data = self.augmenter.load_audio(clean_path)
            # Normalization mandated by Linear
            max_val = np.max(np.abs(data))
            if max_val > 0:
                data = data / max_val * 0.89
            sf.write(final_path, data, 44100)

        # Meta Data DNA
        meta = {
            "source_midi": os.path.basename(midi_path),
            "strategy": strategy_id,
            "sf2": sf2_name,
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S")
        }
        with open(final_path.replace(".wav", ".meta.json"), 'w') as f:
            json.dump(meta, f, indent=4)

    def run_s3_hybrid(self, hybrid_name, midi_path, components_map, noise_path=None, snr=20):
        """
        S3: Hybridization. Each drum class uses a different SF2.
        components_map: {"Kick": "sf2_path", "Snare": "sf2_path", ...}
        """
        midi_name = os.path.basename(midi_path).replace(".midi", "")
        prefix = f"S3_{hybrid_name}_{midi_name}"
        
        all_notes = self.get_all_notes_in_midi(midi_path)
        mapped_notes = []
        for c in ["Kick", "Snare", "HH"]:
            mapped_notes.extend(self.DRUM_CLASSES[c])
        
        others_notes = [n for n in all_notes if n not in mapped_notes]
        
        temp_waves = []
        max_len = 0
        
        # 1. Split MIDI and Render each component
        render_plan = [
            ("Kick", self.DRUM_CLASSES["Kick"]),
            ("Snare", self.DRUM_CLASSES["Snare"]),
            ("HH", self.DRUM_CLASSES["HH"]),
            ("Others", others_notes)
        ]
        
        actual_components_meta = []

        for name, notes in render_plan:
            if not notes: continue
            
            sf2 = components_map.get(name)
            if not sf2: continue
            
            tmp_midi = os.path.join(self.out_dir, f"tmp_{hybrid_name}_{name}.midi")
            self.filter_midi(midi_path, tmp_midi, notes)
            
            tmp_wav = os.path.join(self.out_dir, f"tmp_{hybrid_name}_{name}.wav")
            self.renderer.render(tmp_midi, sf2, tmp_wav)
            
            data = self.augmenter.load_audio(tmp_wav)
            temp_waves.append(data)
            max_len = max(max_len, len(data))
            
            actual_components_meta.append({
                "class": name,
                "sf2": os.path.basename(sf2)
            })
            
            # Clean up intermediate files
            os.remove(tmp_midi)
            os.remove(tmp_wav)

        # 2. Mix
        mixed = np.zeros(max_len)
        for data in temp_waves:
            mixed[:len(data)] += data
            
        # 3. Finalize
        clean_path = os.path.join(self.out_dir, f"{prefix}_clean.wav")
        sf.write(clean_path, mixed, 44100)
        
        final_path = os.path.join(self.out_dir, f"{prefix}.wav")
        if noise_path:
            self.augmenter.process_and_save(clean_path, noise_path, final_path, snr_db=snr)
        else:
            # Normalization
            max_val = np.max(np.abs(mixed))
            if max_val > 0:
                mixed = mixed / max_val * 0.89
            sf.write(final_path, mixed, 44100)

        # 4. Meta Data DNA
        meta = {
            "source_midi": os.path.basename(midi_path),
            "augmentation_strategy": "S-3 (Hybridization)",
            "hybrid_name": hybrid_name,
            "components": actual_components_meta,
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S")
        }
        with open(final_path.replace(".wav", ".meta.json"), 'w') as f:
            json.dump(meta, f, indent=4)
            
        return final_path

if __name__ == "__main__":
    # Restoration Test Logic
    gen = BatchGenerator()
    test_midi = "data/raw_dataset/egmd/e-gmd-v1.0.0/drummer8/eval_session/8_rock-groove8_65_beat_4-4_2.midi"
    sf2_fluid = "lib/soundfonts/FluidR3_GS.sf2"
    sf2_arachno = "lib/soundfonts/Arachno_v1.0.sf2"
    sf2_sgm = "lib/soundfonts/SGM-V2.01.sf2"
    
    if os.path.exists(test_midi):
        # Test S1
        gen.run_s1_s2("S1", test_midi, sf2_arachno)
        
        # Test S3 Hybrid
        h_map = {
            "Kick": sf2_fluid,
            "Snare": sf2_arachno,
            "HH": sf2_sgm,
            "Others": sf2_fluid
        }
        gen.run_s3_hybrid("Hybrid_A_Restored", test_midi, h_map)
        print("\n✅ Restoration successful. S1 and S3 strategies operational.")
