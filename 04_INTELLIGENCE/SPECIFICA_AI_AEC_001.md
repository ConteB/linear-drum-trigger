# SPECIFICA AI-AEC: Architettura Classificatore Neurale (001)

**Persona:** Physics and Mathematics Expert
**Target:** 1D-CNN Inference (C++/VST)

## 1. ARCHITETTURA DEL MODELLO (L-AEC)
Il modello analizza frame di 1024 campioni (~23ms) estratti con finestra di Hanning.

### Input Vector (Features)
- **MFCC (13 coeffs)**: Caratterizzazione timbrica fondamentale.
- **Spectral Centroid**: Baricentro spettrale per distinguere Kick (basso) da Snare (medio-alto).
- **Spectral Flatness**: Per distinguere toni puri da rumore bianco (es. piatti/rullante).
- **Onset Strength**: Derivata dell'energia per la precisione temporale.

### Neural Layers
1. **Input Layer**: [N x T] (Features x Time-steps).
2. **Conv1D Layer**: 16 filtri (kernel size 3) + BatchNorm + ReLU.
3. **Pooling Layer**: MaxPool1D per la riduzione della dimensionalità.
4. **Dense Layer (Bottleneck)**: 32 neuroni.
5. **Output Layer (Softmax)**: Probabilità su 8 classi (Kick, Snare, Clap, Rim, HH, Tom, Perc, Ghost).

## 2. PIPELINE DI TRAINING (AUTOMATED WILD-SOURCING)
- **Dataset Source**: Freesound.org, AudioSet (Google), Kaggle.
- **Data Augmentation (Adversarial)**:
  - Iniezione di artefatti di separazione (Pre-echo, low-pass brickwall).
  - Pitch-shifting e Time-stretching casuale (+/- 10%).
  - Iniezione di rumore rosa e ambientale a bassi livelli.
- **Loss Function**: Cross-Entropy pesata (per gestire dataset sbilanciati).

## 3. VINCOLI IMPLEMENTATIVI
- **Inference**: I pesi sono esportati come `static const float[]`.
- **Latenza**: 1024 samples (PDC).
