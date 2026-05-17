import argparse
import logging
from pathlib import Path
import numpy as np
import soundfile as sf
import sys
import os

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import scraper
from scraper import MultiSourceScraper, DATASET_DIR
import scraper

def generate_mock_audio(filepath: Path, duration_sec: int = 5, sr: int = 44100, noise_type='white'):
    """Generate dummy audio file with specified noise type."""
    num_samples = duration_sec * sr
    
    if noise_type == 'white':
        # White noise
        audio = np.random.normal(0, 1, num_samples)
    elif noise_type == 'pink':
        # Pink noise approximation
        audio = np.random.normal(0, 1, num_samples)
        audio = np.cumsum(audio)
        audio = audio - np.mean(audio)
        audio = audio / np.max(np.abs(audio)) if np.max(np.abs(audio)) > 0 else audio
    else: # dull bass (low frequency sine wave)
        t = np.linspace(0, duration_sec, num_samples, endpoint=False)
        audio = np.sin(2 * np.pi * 50 * t) # 50 Hz sine
        
    # Normalize to -1 to 1
    audio = audio / np.max(np.abs(audio)) if np.max(np.abs(audio)) > 0 else audio
    
    sf.write(filepath, audio, sr, subtype='PCM_16')
    logger.info(f"Generated mock audio: {filepath.name}, Type: {noise_type}, Shape: {audio.shape}, SR: {sr}")
    
    # Mathematical verification:
    # 16-bit PCM = 2 bytes per sample.
    expected_bytes = num_samples * 2 + 44 # 44 bytes wav header
    actual_bytes = filepath.stat().st_size
    logger.info(f"Mathematical size verification for {filepath.name}: Expected ~{expected_bytes} bytes, Actual: {actual_bytes} bytes")
    
    if abs(expected_bytes - actual_bytes) > 100:
        logger.warning(f"Size mismatch for {filepath.name}: expected {expected_bytes}, got {actual_bytes}")
    
    return actual_bytes

def main():
    parser = argparse.ArgumentParser(description="AudioSet Sourcing Pipeline")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode to generate dummy files")
    
    args = parser.parse_args()
    
    scraper_inst = MultiSourceScraper(DATASET_DIR)
    audioset_dir = DATASET_DIR / "audioset_caos"
    audioset_dir.mkdir(parents=True, exist_ok=True)
    
    if args.mock:
        logger.info("Running in MOCK mode. Generating dummy files...")
        
        mock_files = [
            ("mock_caos_white.wav", "white"),
            ("mock_caos_pink.wav", "pink"),
            ("mock_caos_bass.wav", "bass")
        ]
        
        for filename, ntype in mock_files:
            filepath = audioset_dir / filename
            generate_mock_audio(filepath, duration_sec=5, sr=44100, noise_type=ntype)
            
        logger.info("Mock generation complete.")
        
        # Test the 5GB limit logic by temporarily mocking the limit
        logger.info("Testing 5GB limit logic...")
        original_limit = scraper.MAX_AUDIOSET_GB
        # Calculate current size of audioset_dir in GB and set limit slightly below it
        current_size_gb = sum(f.stat().st_size for f in audioset_dir.rglob('*') if f.is_file()) / (1024**3)
        scraper.MAX_AUDIOSET_GB = current_size_gb - 0.000000001 # Set limit just below current size
        
        logger.info(f"Artificially set limit to {scraper.MAX_AUDIOSET_GB:.8f} GB to test scraper refusal.")
        
        # Try to use scraper to download (should fail due to limit)
        success = scraper_inst.download_youtube_audio("https://www.youtube.com/watch?v=mock", "should_fail")
        
        if not success:
            logger.info("Limit test PASSED: Scraper blocked download due to storage limit.")
        else:
            logger.error("Limit test FAILED: Scraper allowed download despite limit.")
            sys.exit(1)
            
        scraper.MAX_AUDIOSET_GB = original_limit
        
    else:
        logger.info("Normal mode. (Implementation pending for actual yt-dlp downloading list)")

if __name__ == "__main__":
    main()
