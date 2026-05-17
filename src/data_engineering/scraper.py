import os
import logging
from pathlib import Path
import yt_dlp
import requests

# Configurazione Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configurazione Percorsi e Limiti da Protocollo PTW-001
DATASET_DIR = Path("./data/raw_dataset")
MAX_STORAGE_GB = 50.0 
MAX_AUDIOSET_GB = 5.0 # Hard limit fissato a 5GB per i rumori spuri

def check_storage_limit(directory: Path, limit_gb: float) -> bool:
    """Verifica che la directory non superi il limite di storage indicato."""
    if not directory.exists():
        return True
    
    total_size = sum(f.stat().st_size for f in directory.rglob('*') if f.is_file())
    total_gb = total_size / (1024 ** 3)
    
    if total_gb >= limit_gb:
        logger.error(f"CRITICO: Limite di storage raggiunto ({total_gb:.2f}GB / {limit_gb}GB). Arresto scraper.")
        return False
    
    logger.info(f"Storage attuale: {total_gb:.2f}GB / {limit_gb}GB")
    return True

class MultiSourceScraper:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.freesound_api_key = os.getenv("FREESOUND_API_KEY", "")
        
    def download_youtube_audio(self, url: str, output_filename: str):
        """Scarica l'audio da un video YouTube (utile per AudioSet) via yt-dlp."""
        if not check_storage_limit(self.data_dir, MAX_STORAGE_GB):
            return False
            
        audioset_dir = self.data_dir / "audioset_caos"
        audioset_dir.mkdir(parents=True, exist_ok=True)
        if not check_storage_limit(audioset_dir, MAX_AUDIOSET_GB):
            logger.warning(f"Limite locale di {MAX_AUDIOSET_GB}GB per AudioSet raggiunto. Download annullato.")
            return False
            
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '44100',
            }],
            'outtmpl': str(audioset_dir / f"{output_filename}.%(ext)s"),
            'quiet': False,
            'no_warnings': True
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info(f"Download yt-dlp avviato: {url}")
                ydl.download([url])
                return True
        except Exception as e:
            logger.error(f"Errore download yt-dlp: {e}")
            return False

    def search_and_download_freesound(self, query: str, limit: int = 10):
        """Cerca e scarica sample da Freesound tramite API."""
        if not self.freesound_api_key:
            logger.warning("Freesound API Key mancante. Salto il download da Freesound.")
            return False
            
        if not check_storage_limit(self.data_dir, MAX_STORAGE_GB):
            return False

        logger.info(f"Ricerca Freesound avviata per: '{query}'")
        # Implementazione futura: API call verso https://freesound.org/apiv2/search/text/
        # Richiede OAuth2 o Token per il download HQ.
        return True

if __name__ == "__main__":
    logger.info("Multi-Source Scraper Inizializzato.")
    scraper = MultiSourceScraper(DATASET_DIR)
    
    # Placeholder per l'avvio della pipeline di scraping
    # scraper.download_youtube_audio("https://www.youtube.com/watch?v=...", "audioset_sample_01")
