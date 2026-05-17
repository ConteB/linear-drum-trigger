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

## 2. PIPELINE DI TRAINING E DOMAIN ALIGNMENT
- **Dataset Source**: ENST-Drums, StemGMD (Pattern Reali/Sintetici), AudioSet (Rumore/Bleed).
- **Risoluzione Domain Mismatch (Macro vs Micro)**: 
  - **Fase Macro (Mix)**: L'audio viene miscelato in RAM su loop interi di 5-10 secondi per permettere lo sviluppo naturale di riverberi, sustain e interferenze di fase (Pattern-Aware Synthesis).
  - **Fase Micro (Inference-Aligned)**: Sull'audio mixato scorre una finestra mobile di 1024-2048 campioni (l'esatto buffer/look-ahead del VST C++). La rete estrae le feature *solo* da questo frammento e viene addestrata a riconoscere l'attacco all'interno di questi stretti margini temporali.
- **Data Augmentation (Adversarial)**:
  - Sovrapposizione di rumore procedurale e bleed (chitarre/bassi da YouTube) sui loop completi.
  - Pitch-shifting e Time-stretching casuale per variare i BPM dei pattern.
- **Loss Function**: Cross-Entropy pesata (per gestire dataset sbilanciati).

## 3. VINCOLI IMPLEMENTATIVI
- **Inference**: I pesi sono esportati come `static const float[]`.
- **Latenza**: 1024 samples (PDC).
