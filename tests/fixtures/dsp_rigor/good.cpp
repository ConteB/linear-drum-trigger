// good.cpp — RT-safe DSP fixture for F0-T6 audit gate.
//
// Two audio-thread regions:
//   1) The JUCE-style `processBlock` (auto-scoped by heuristic).
//   2) An explicit `// @audio_thread` block inside `tick()`.
//
// Both follow the Zero-Allocation mandate (no new/malloc, no vector::push_back,
// no std::string ops, no I/O, no mutex, no throw). The auditor must produce
// ZERO findings on this file.

#include <array>

class TcnProcessor {
public:
    TcnProcessor() : buffer_{} {}

    // JUCE-style audio callback — auto-scoped by heuristic.
    void processBlock(float* const* channelData, int numChannels, int numSamples) {
        for (int ch = 0; ch < numChannels; ++ch) {
            for (int i = 0; i < numSamples; ++i) {
                // Pre-allocated array indexed by sample — no allocation.
                buffer_[i % kBufferSize] = channelData[ch][i];
                channelData[ch][i] = applyGain(channelData[ch][i]);
            }
        }
    }

    void tick(float input) {
        // @audio_thread
        // Explicit region — auto-scoped by marker.
        const float gain = applyGain(input);
        accumulator_ += gain;
        // @audio_thread_end

        // Outside the scope — allocations OK (setup-time, not RT).
        // (No alloc here anyway, but the gate should ignore this line.)
        outOfScope_ = "this string is fine because we are out of scope";
    }

private:
    static constexpr int kBufferSize = 256;
    std::array<float, kBufferSize> buffer_;
    float accumulator_{0.0f};
    const char* outOfScope_{nullptr};

    float applyGain(float x) const {
        return x * 0.5f;
    }
};
