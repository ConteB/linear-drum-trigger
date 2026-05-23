"""Neural module — F0-T4b TCN mini-prototype.

Owns the model (F0-T4a topology), the loss, the data-loader (Gold sample triple
→ tensors with F0-T4a §4 canonical slot mapping), the onset/timing metrics for
the L3 threshold (F0-T4a §7), and the RTNeural export (F0-T8 spec, smoke-tested
in F0-T4b as part of the L3 round-trip).
"""
