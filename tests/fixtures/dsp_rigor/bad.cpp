// bad.cpp — RT-UNSAFE DSP fixture for F0-T6 audit gate.
//
// Two audio-thread regions (one heuristic, one explicit) each containing
// canonical violations of the Zero-Allocation mandate. The auditor must
// produce one finding per violation site below.

#include <iostream>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

class BadProcessor {
public:
    void processBlock(float* const* channelData, int numChannels, int numSamples) {
        // Violation: heap allocation in hot path.
        float* scratch = new float[numSamples];

        // Violation: vector::push_back can reallocate.
        std::vector<float> events;
        events.push_back(0.0f);

        // Violation: vector::emplace_back idem.
        events.emplace_back(1.0f);

        // Violation: std::cout is blocking I/O.
        std::cout << "processing block" << std::endl;

        // Violation: mutex lock — priority inversion risk.
        std::lock_guard<std::mutex> guard(mtx_);

        // Violation: throw allocates the exception object.
        if (numChannels < 1) {
            throw std::runtime_error("no channels");
        }

        // Violation: delete pairs with the new above.
        delete[] scratch;
    }

    void tick(float input) {
        // @audio_thread
        // Violation: std::string append allocates.
        std::string s;
        s.append("tick: ");

        // Violation: smart pointer construction allocates.
        auto buf = std::make_unique<float[]>(64);

        // Violation: printf is blocking I/O.
        printf("tick %f\n", input);

        // Violation: DBG (juce::Logger) — allocates + blocks.
        // (Simulated as a function-like form; this fixture is not compiled —
        // its sole purpose is to feed the F0-T6 grep gate.)
        DBG("debug message");
        // @audio_thread_end

        // Outside scope — should NOT be flagged.
        auto safeAlloc = new float[10];
        delete[] safeAlloc;
    }

private:
    std::mutex mtx_;
};
