import argparse
import os
import wave
import struct
import math

def generate_mock_data():
    output_dir = os.path.join('data', 'raw_dataset', 'mdb_drums_sacred')
    os.makedirs(output_dir, exist_ok=True)
    
    sample_rate = 44100
    duration = 30  # seconds
    num_samples = sample_rate * duration
    
    for i in range(3):
        file_path = os.path.join(output_dir, f'mock_sacred_track_{i:02d}.wav')
        
        # Create a stereo wav file
        with wave.open(file_path, 'w') as wav_file:
            nchannels = 2
            sampwidth = 2
            framerate = sample_rate
            nframes = num_samples
            comptype = "NONE"
            compname = "not compressed"
            wav_file.setparams((nchannels, sampwidth, framerate, nframes, comptype, compname))
            
            # Write frames in chunks
            chunk_size = 44100
            for chunk_idx in range(math.ceil(num_samples / chunk_size)):
                frames = bytearray()
                start_sample = chunk_idx * chunk_size
                end_sample = min(start_sample + chunk_size, num_samples)
                
                for sample_idx in range(start_sample, end_sample):
                    t = sample_idx / sample_rate
                    left_val = int(math.sin(2 * math.pi * (440 + i * 100) * t) * 16000)
                    right_val = int(math.sin(2 * math.pi * (880 + i * 100) * t) * 16000)
                    frames.extend(struct.pack('<hh', left_val, right_val))
                
                wav_file.writeframes(frames)
                
        print(f"Created mock file: {file_path} (30s, 44100Hz, Stereo)")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='MDB Drums Sacred Dataset Pipeline')
    parser.add_argument('--mock', action='store_true', help='Generate mock data for blind testing')
    args = parser.parse_args()
    
    if args.mock:
        print("Starting mock generation for Sacred Validation (MDB Drums)...")
        generate_mock_data()
        print("Mock generation complete.")
    else:
        print("Real data sourcing not implemented yet.")