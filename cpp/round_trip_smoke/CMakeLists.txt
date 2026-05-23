# F0-T4b — C++ smoke-test for the L3 round-trip gate.
#
# Loads the model packed by ``src/neural/export_bin.py`` (binary sidecar of the
# JSON export), runs the same operations as ``neural.export.numpy_reference_forward``
# in pure C++17, and writes the output as a raw float32 blob for the Python
# comparator to diff against PyTorch.
#
# No external dependency: the model is a packed binary, the input/output are
# raw float32 blobs. The C++ op-set is the strict RTNeural subset
# (Conv1D causal strided/dilated + ReLU/sigmoid/tanh + additive merge),
# documenting that the F0-T4a topology is implementable on the streaming
# inference target (F0-T4a §8 open item).

cmake_minimum_required(VERSION 3.20)
project(f0t4b_round_trip CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(round_trip_smoke main.cpp)
target_compile_options(round_trip_smoke PRIVATE -O2 -Wall -Wextra -Wpedantic)
