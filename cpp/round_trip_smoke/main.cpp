// F0-T4b — RTNeural-equivalent round-trip smoke test.
//
// Loads the TCN model packed by `src/neural/export_bin.py`, runs the same
// forward pass as `neural.export.numpy_reference_forward` in pure C++17, and
// writes the output as a raw float32 blob. The Python comparator
// (`tools/run_round_trip.py`) diffs this blob against the PyTorch output and
// produces the L3 round-trip verdict.
//
// The op-set is intentionally the strict RTNeural subset:
//   * Conv1D (with stride + dilation, causal left-pad)
//   * elementwise ReLU / sigmoid / tanh
//   * additive merge (residual skip)
//
// F0-T4a §8 open item — residual handling: the trunk's input-skip is
// represented as a residual_kind flag on each `trunk_J_conv2` layer; the C++
// side captures the input of every `trunk_J_conv1` and re-adds it on the
// matching `trunk_J_conv2`. This is option (a) of §8: the residual is part of
// the exported topology, RTNeural runs each conv natively, and the additive
// merge sits outside RTNeural's sequential graph.

#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

constexpr std::uint32_t kMagic = 0x544E504F;  // "OPNT" little-endian
constexpr std::uint32_t kSchemaVersion = 1;

enum class Activation : std::int32_t {
  None = 0,
  ReLU = 1,
  Sigmoid = 2,
  Tanh = 3,
};

enum class Residual : std::int32_t {
  None = 0,
  TrunkInput = 1,
};

struct Layer {
  std::string id;
  std::int32_t in_channels;
  std::int32_t out_channels;
  std::int32_t kernel_size;
  std::int32_t stride;
  std::int32_t dilation;
  std::int32_t causal_left_pad;
  Activation activation;
  Residual residual;
  std::vector<float> weight;  // [out, in, k] row-major
  std::vector<float> bias;    // [out]
};

template <typename T>
T read_pod(std::istream& s) {
  T v{};
  s.read(reinterpret_cast<char*>(&v), sizeof(T));
  if (!s) {
    throw std::runtime_error("EOF reading scalar");
  }
  return v;
}

std::vector<Layer> load_model(const std::string& path) {
  std::ifstream s(path, std::ios::binary);
  if (!s) {
    throw std::runtime_error("cannot open model file: " + path);
  }
  auto magic = read_pod<std::uint32_t>(s);
  if (magic != kMagic) {
    throw std::runtime_error("bad magic — not an OPNT model");
  }
  auto version = read_pod<std::uint32_t>(s);
  if (version != kSchemaVersion) {
    throw std::runtime_error("unsupported schema version: " + std::to_string(version));
  }
  auto n_layers = read_pod<std::uint32_t>(s);
  std::vector<Layer> layers;
  layers.reserve(n_layers);
  for (std::uint32_t i = 0; i < n_layers; ++i) {
    Layer L;
    auto id_len = read_pod<std::uint32_t>(s);
    L.id.resize(id_len);
    if (id_len > 0) {
      s.read(&L.id[0], id_len);
    }
    L.in_channels = read_pod<std::int32_t>(s);
    L.out_channels = read_pod<std::int32_t>(s);
    L.kernel_size = read_pod<std::int32_t>(s);
    L.stride = read_pod<std::int32_t>(s);
    L.dilation = read_pod<std::int32_t>(s);
    L.causal_left_pad = read_pod<std::int32_t>(s);
    L.activation = static_cast<Activation>(read_pod<std::int32_t>(s));
    L.residual = static_cast<Residual>(read_pod<std::int32_t>(s));
    std::size_t n_w = static_cast<std::size_t>(L.out_channels) *
                      static_cast<std::size_t>(L.in_channels) *
                      static_cast<std::size_t>(L.kernel_size);
    L.weight.resize(n_w);
    s.read(reinterpret_cast<char*>(L.weight.data()),
           static_cast<std::streamsize>(n_w * sizeof(float)));
    L.bias.resize(static_cast<std::size_t>(L.out_channels));
    s.read(reinterpret_cast<char*>(L.bias.data()),
           static_cast<std::streamsize>(L.bias.size() * sizeof(float)));
    if (!s) {
      throw std::runtime_error("EOF reading layer " + L.id);
    }
    layers.push_back(std::move(L));
  }
  return layers;
}

struct Tensor2D {
  std::int32_t channels = 0;
  std::int32_t time = 0;
  std::vector<float> data;  // row-major: channels x time

  float& at(std::int32_t c, std::int32_t t) {
    return data[static_cast<std::size_t>(c) * static_cast<std::size_t>(time) +
                static_cast<std::size_t>(t)];
  }
  float at(std::int32_t c, std::int32_t t) const {
    return data[static_cast<std::size_t>(c) * static_cast<std::size_t>(time) +
                static_cast<std::size_t>(t)];
  }
};

Tensor2D conv1d_causal(const Tensor2D& x, const Layer& L) {
  if (x.channels != L.in_channels) {
    throw std::runtime_error("conv1d_causal: channel mismatch at layer " + L.id +
                             " (x has " + std::to_string(x.channels) +
                             ", weight expects " + std::to_string(L.in_channels) + ")");
  }
  const std::int32_t k = L.kernel_size;
  const std::int32_t dil = L.dilation;
  const std::int32_t stride = L.stride;
  const std::int32_t left = (k - 1) * dil;
  const std::int32_t t_pad = x.time + left;
  // t_out = (t_pad - (k-1)*dil - 1) // stride + 1
  const std::int32_t t_out = (t_pad - (k - 1) * dil - 1) / stride + 1;

  Tensor2D y;
  y.channels = L.out_channels;
  y.time = t_out;
  y.data.assign(static_cast<std::size_t>(t_out) * static_cast<std::size_t>(L.out_channels), 0.0f);

  // Iterate output time steps.
  for (std::int32_t n = 0; n < t_out; ++n) {
    const std::int32_t base = n * stride;  // index into the padded series
    for (std::int32_t cout = 0; cout < L.out_channels; ++cout) {
      float acc = L.bias[static_cast<std::size_t>(cout)];
      // weight row [cout, *, *] = L.in_channels * k consecutive entries.
      for (std::int32_t cin = 0; cin < L.in_channels; ++cin) {
        for (std::int32_t j = 0; j < k; ++j) {
          const std::int32_t idx_padded = base + j * dil;
          // The padded series has `left` zeros prepended.
          const std::int32_t idx_x = idx_padded - left;
          float v = 0.0f;
          if (idx_x >= 0 && idx_x < x.time) {
            v = x.at(cin, idx_x);
          }
          // weight row order: [cout, cin, j]
          const std::size_t w_idx =
              static_cast<std::size_t>(cout) * static_cast<std::size_t>(L.in_channels) *
                  static_cast<std::size_t>(k) +
              static_cast<std::size_t>(cin) * static_cast<std::size_t>(k) +
              static_cast<std::size_t>(j);
          acc += L.weight[w_idx] * v;
        }
      }
      y.at(cout, n) = acc;
    }
  }
  return y;
}

float apply_activation(float v, Activation a) {
  switch (a) {
    case Activation::None:
      return v;
    case Activation::ReLU:
      return v < 0.0f ? 0.0f : v;
    case Activation::Sigmoid:
      return 1.0f / (1.0f + std::exp(-v));
    case Activation::Tanh:
      return std::tanh(v);
  }
  return v;
}

void apply_activation_inplace(Tensor2D& x, Activation a) {
  if (a == Activation::None) return;
  for (auto& v : x.data) {
    v = apply_activation(v, a);
  }
}

void add_inplace(Tensor2D& a, const Tensor2D& b) {
  if (a.channels != b.channels || a.time != b.time) {
    throw std::runtime_error("add_inplace: shape mismatch");
  }
  for (std::size_t i = 0; i < a.data.size(); ++i) {
    a.data[i] += b.data[i];
  }
}

bool starts_with(const std::string& s, const std::string& prefix) {
  return s.size() >= prefix.size() && std::memcmp(s.data(), prefix.data(), prefix.size()) == 0;
}

bool ends_with(const std::string& s, const std::string& suffix) {
  return s.size() >= suffix.size() &&
         std::memcmp(s.data() + (s.size() - suffix.size()), suffix.data(), suffix.size()) == 0;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 4) {
    std::cerr << "usage: round_trip_smoke <model.bin> <audio.f32> <out.f32>\n";
    return 2;
  }
  try {
    const std::string model_path = argv[1];
    const std::string audio_path = argv[2];
    const std::string out_path = argv[3];

    auto layers = load_model(model_path);
    std::cerr << "[round_trip_smoke] loaded " << layers.size() << " layers from "
              << model_path << "\n";

    // Read input audio: raw float32, [8, n_sample].
    std::ifstream af(audio_path, std::ios::binary | std::ios::ate);
    if (!af) {
      throw std::runtime_error("cannot open audio: " + audio_path);
    }
    auto size_bytes = af.tellg();
    if (size_bytes % static_cast<std::streamoff>(8 * sizeof(float)) != 0) {
      throw std::runtime_error("audio size is not a multiple of 8 * float32");
    }
    af.seekg(0);
    Tensor2D x;
    x.channels = 8;
    x.time = static_cast<std::int32_t>(size_bytes / static_cast<std::streamoff>(8 * sizeof(float)));
    x.data.resize(static_cast<std::size_t>(8) * static_cast<std::size_t>(x.time));
    af.read(reinterpret_cast<char*>(x.data.data()), size_bytes);
    std::cerr << "[round_trip_smoke] input audio: [8, " << x.time << "]\n";

    // Forward pass.
    Tensor2D trunk_features;  // shared input to all four heads
    bool has_trunk_features = false;
    Tensor2D last_trunk_input;  // captured before each trunk_J_conv1
    bool has_last_trunk_input = false;

    // Capture all head outputs.
    Tensor2D head_onset, head_velocity, head_microtiming, head_hihat;
    bool got_onset = false, got_velocity = false, got_microtiming = false, got_hihat = false;

    auto is_head = [](const std::string& id) {
      return id == "head_onset" || id == "head_velocity" || id == "head_microtiming" ||
             id == "head_hihat";
    };

    for (const auto& L : layers) {
      // Trunk-block input capture.
      if (starts_with(L.id, "trunk_") && ends_with(L.id, "_conv1")) {
        last_trunk_input = x;
        has_last_trunk_input = true;
      }
      // Head fan-out: capture the trunk output on the first head, replay it
      // before each subsequent head.
      if (is_head(L.id)) {
        if (!has_trunk_features) {
          trunk_features = x;
          has_trunk_features = true;
        }
        x = trunk_features;
      }
      x = conv1d_causal(x, L);
      apply_activation_inplace(x, L.activation);
      if (L.residual == Residual::TrunkInput) {
        if (!has_last_trunk_input) {
          throw std::runtime_error("missing residual source for " + L.id);
        }
        add_inplace(x, last_trunk_input);
      }
      if (L.id == "head_onset") { head_onset = x; got_onset = true; }
      if (L.id == "head_velocity") { head_velocity = x; got_velocity = true; }
      if (L.id == "head_microtiming") { head_microtiming = x; got_microtiming = true; }
      if (L.id == "head_hihat") { head_hihat = x; got_hihat = true; }
    }

    if (!(got_onset && got_velocity && got_microtiming && got_hihat)) {
      throw std::runtime_error("missing one or more heads in the exported model");
    }
    if (head_onset.channels != 8 || head_velocity.channels != 8 ||
        head_microtiming.channels != 8 || head_hihat.channels != 1) {
      throw std::runtime_error("head channel counts do not match flat-25 layout");
    }
    const std::int32_t T = head_onset.time;
    if (head_velocity.time != T || head_microtiming.time != T || head_hihat.time != T) {
      throw std::runtime_error("head time axes disagree");
    }

    // Assemble flat-25: cols (3b, 3b+1, 3b+2) per bus + col 24 hihat.
    constexpr std::int32_t TARGET_COLS = 25;
    std::vector<float> flat(static_cast<std::size_t>(T) * static_cast<std::size_t>(TARGET_COLS));
    for (std::int32_t t = 0; t < T; ++t) {
      for (std::int32_t b = 0; b < 8; ++b) {
        flat[static_cast<std::size_t>(t) * TARGET_COLS + 3 * b + 0] = head_onset.at(b, t);
        flat[static_cast<std::size_t>(t) * TARGET_COLS + 3 * b + 1] = head_velocity.at(b, t);
        flat[static_cast<std::size_t>(t) * TARGET_COLS + 3 * b + 2] = head_microtiming.at(b, t);
      }
      flat[static_cast<std::size_t>(t) * TARGET_COLS + 24] = head_hihat.at(0, t);
    }

    std::ofstream of(out_path, std::ios::binary);
    if (!of) {
      throw std::runtime_error("cannot open output: " + out_path);
    }
    of.write(reinterpret_cast<const char*>(flat.data()),
             static_cast<std::streamsize>(flat.size() * sizeof(float)));
    std::cerr << "[round_trip_smoke] wrote [" << T << ", " << TARGET_COLS << "] flat-25 to "
              << out_path << "\n";
    return 0;
  } catch (const std::exception& e) {
    std::cerr << "[round_trip_smoke] ERROR: " << e.what() << "\n";
    return 1;
  }
}
