import os
import random
from src.data_engineering.batch_generator import BatchGenerator

# Setup
orchestrator = BatchGenerator()
orchestrator.out_dir = "data/temp/demo_listening_session"
os.makedirs(orchestrator.out_dir, exist_ok=True)

# Resources
sf2_standard = "lib/soundfonts/fluid_gm.sf2"
sf2_fat = "lib/soundfonts/SGM-V2.01.sf2"
sf2_crispy = "lib/soundfonts/Arachno_v1.0.sf2"
sf2_studio = "lib/soundfonts/douglas_studio.sf2"
noise_pink = "data/raw_dataset/audioset_caos/mock_caos_pink.wav"

# Real Drummer MIDI Selection (E-GMD)
midi_files = [
    "data/raw_dataset/egmd/e-gmd-v1.0.0/drummer8/eval_session/2_funk-groove2_105_beat_4-4_53.midi",
    "data/raw_dataset/egmd/e-gmd-v1.0.0/drummer8/eval_session/8_rock-groove8_65_beat_4-4_2.midi",
    "data/raw_dataset/egmd/e-gmd-v1.0.0/drummer8/eval_session/10_soul-groove10_102_beat_4-4_1.midi",
    "data/raw_dataset/egmd/e-gmd-v1.0.0/drummer8/eval_session/3_soul-groove3_86_beat_4-4_16.midi"
]

# DRUM MAP
KICK = [35, 36]
SNARE = [38, 40]

print(f"🚀 Generazione sessione di ascolto in: {orchestrator.out_dir}\n")

# Scenario 1: Full Kit - Real Funk Performance (Clean & Professional)
orchestrator.run_scenario("01_Funk_RealFeel_Studio", midi_files[0], [sf2_studio])

# Scenario 2: Isolated Kick - Deep Fat Kick from Rock Performance
orchestrator.run_scenario("02_Rock_OnlyKick_Fat", midi_files[1], [sf2_fat], notes=KICK)

# Scenario 3: Isolated Snare - Crispy Snare with Heavy Pink Noise
orchestrator.run_scenario("03_Soul_OnlySnare_Noisy", midi_files[2], [sf2_crispy], noise_pink, snr=8, notes=SNARE)

# Scenario 4: Hybrid Blend - Soul Groove (SGM for Body + Arachno for Attack)
orchestrator.run_scenario("04_Soul_Hybrid_Mix", midi_files[3], [sf2_fat, sf2_crispy])

# Scenario 5: Full Chaos - Funk with heavy noise and Standard Kit
orchestrator.run_scenario("05_Funk_Chaos_Extreme", midi_files[0], [sf2_standard], noise_pink, snr=5)

print("\n✅ Batch pronto per l'ascolto.")
