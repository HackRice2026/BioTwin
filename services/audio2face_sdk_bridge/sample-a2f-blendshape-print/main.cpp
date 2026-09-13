// SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: MIT
//
// One-shot bridge: loads the Audio2Face-3D regression model + blendshape
// solver, reads exactly ONE utterance of raw 16kHz mono float32 PCM from
// stdin (a 4-byte little-endian uint32 byte count, then that many bytes),
// runs inference, writes one JSON line per output frame to stdout, then
// exits.
//
// Deliberately single-utterance, not long-lived: earlier attempts tried
// to reuse one bundle across multiple utterances in the same process,
// three different ways --
//   1. Reset() the executor + accumulators between utterances (a real,
//      documented per-track reset, not a hack).
//   2. Never reset at all, just keep accumulating one continuous stream.
//   3. Discard the whole bundle and build a genuinely fresh one (new
//      executor, new solver, new accumulators) per utterance, in the
//      same process.
// All three reproducibly made the SECOND utterance's blendshape weights
// come back as NaN from frame 0 onward, even attempt 3, where nothing
// from the first utterance's objects was touched or reused. That points
// to some process-global GPU/allocator state this SDK doesn't expose a
// way to reset (checked and ruled out: the accumulators' own Reset(),
// the blendshape solver's Reset() and Wait(), and cublasCreate()'s
// return status on every handle created along this path all check out
// individually). See docs/AVATAR_IMPLEMENTATION_PLAN.md for the full
// investigation.
//
// The practical fix lives one level up, in the Python service: run a
// small pool of these processes, each handling exactly one utterance
// and then discarded and replaced -- the one configuration that has
// actually produced correct output every time it's been tried.

#include "audio2face/audio2face.h"
#include "audio2x/cuda_utils.h"

#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>
#include <unistd.h>

#define CHECK_RESULT(func)                                                     \
  {                                                                            \
    std::error_code error = (func);                                            \
    if (error) {                                                               \
      std::cerr << "Error (" << __LINE__ << "): Failed to execute: " << #func; \
      std::cerr << ", Reason: "<< error.message() << std::endl;                \
      return 1;                                                                \
    }                                                                          \
  }

#define CHECK_ERROR(expression)                                                \
  {                                                                            \
    if (!(expression)) {                                                       \
      std::cerr << "Error (" << __LINE__ << "): " << #expression;              \
      std::cerr << " is NULL" << std::endl;                                    \
      return 1;                                                                \
    }                                                                          \
  }

// Reads exactly `count` bytes from stdin into `dest`. Returns false on EOF.
bool readExact(char* dest, std::size_t count) {
  std::size_t got = 0;
  while (got < count) {
    std::cin.read(dest + got, static_cast<std::streamsize>(count - got));
    std::streamsize n = std::cin.gcount();
    if (n <= 0) return false;
    got += static_cast<std::size_t>(n);
  }
  return true;
}

int main(int argc, char** argv) {
  std::string modelJsonPath = argc > 1 ? argv[1]
      : TEST_DATA_DIR "_data/generated/audio2face-sdk/samples/data/mark/model.json";

  constexpr int deviceID = 0;
  CHECK_RESULT(nva2x::SetCudaDeviceIfNeeded(deviceID));

  // Not RAII-wrapped, never Destroy()'d -- explicitly destroying these was
  // found (see docs/AVATAR_IMPLEMENTATION_PLAN.md) to hang or segfault the
  // process during SDK cleanup. Exiting via _exit() instead lets the OS
  // reclaim everything without running that teardown path at all.
  nva2f::IRegressionModel::IGeometryModelInfo* modelInfoPtr = nullptr;
  nva2f::IRegressionModel::IBlendshapeSolveModelInfo* blendshapeInfoPtr = nullptr;
  auto* bundle = nva2f::ReadRegressionBlendshapeSolveExecutorBundle(
      1,
      modelJsonPath.c_str(),
      nva2f::IGeometryExecutor::ExecutionOption::Skin,
      /*useGpuSolver=*/false,
      60, 1,
      &modelInfoPtr,
      &blendshapeInfoPtr
      );
  CHECK_ERROR(bundle);

  nva2f::IBlendshapeSolver* skinSolver = nullptr;
  CHECK_RESULT(nva2f::GetExecutorSkinSolver(bundle->GetExecutor(), 0, &skinSolver));
  CHECK_ERROR(skinSolver);
  const int numPoses = skinSolver->NumBlendshapePoses();
  std::vector<std::string> poseNames;
  for (int i = 0; i < numPoses; ++i) poseNames.push_back(skinSolver->GetPoseName(i));

  struct CallbackData {
    std::size_t frameIndex = 0;
    const std::vector<std::string>* names;
  };
  CallbackData callbackData;
  callbackData.names = &poseNames;

  auto callback = [](void* userdata, const nva2f::IBlendshapeExecutor::HostResults& results, std::error_code errorCode) {
    auto& data = *static_cast<CallbackData*>(userdata);
    if (errorCode) {
      std::cerr << "Error in results callback: " << errorCode.message() << std::endl;
      return;
    }
    std::cout << "{\"frame\":" << data.frameIndex << ",\"weights\":{";
    bool first = true;
    for (std::size_t i = 0; i < results.weights.Size() && i < data.names->size(); ++i) {
      float value = results.weights.Data()[i];
      if (value <= 0.01f) continue;
      if (!first) std::cout << ",";
      first = false;
      std::cout << "\"" << (*data.names)[i] << "\":" << value;
    }
    std::cout << "}}" << std::endl;
    data.frameIndex++;
  };
  CHECK_RESULT(bundle->GetExecutor().SetResultsCallback(callback, &callbackData));

  std::cerr << "ready" << std::endl;  // Python side waits for this line before sending audio.

  uint32_t byteCount = 0;
  if (readExact(reinterpret_cast<char*>(&byteCount), sizeof(byteCount)) && byteCount > 0) {
    std::vector<uint8_t> raw(byteCount);
    if (readExact(reinterpret_cast<char*>(raw.data()), byteCount)) {
      std::vector<float> audioBuffer(raw.size() / sizeof(float));
      std::memcpy(audioBuffer.data(), raw.data(), audioBuffer.size() * sizeof(float));

      if (!audioBuffer.empty()) {
        auto& audioAccumulator = bundle->GetAudioAccumulator(0);
        CHECK_RESULT(
          audioAccumulator.Accumulate(
            nva2x::HostTensorFloatConstView{audioBuffer.data(), audioBuffer.size()}, bundle->GetCudaStream().Data()
            )
          );
        CHECK_RESULT(audioAccumulator.Close());

        auto& emotionAccumulator = bundle->GetEmotionAccumulator(0);
        std::vector<float> emptyEmotion(emotionAccumulator.GetEmotionSize(), 0.0f);
        CHECK_RESULT(emotionAccumulator.Accumulate(
          0, nva2x::HostTensorFloatConstView{emptyEmotion.data(), emptyEmotion.size()}, bundle->GetCudaStream().Data()
          ));
        CHECK_RESULT(emotionAccumulator.Close());

        while (nva2x::GetNbReadyTracks(bundle->GetExecutor()) > 0) {
          CHECK_RESULT(bundle->GetExecutor().Execute(nullptr));
        }
        CHECK_RESULT(bundle->GetExecutor().Wait(0));
      }
    }
  }

  std::cout << "{\"utterance_done\":true}" << std::endl;
  std::cerr << "Done. " << callbackData.frameIndex << " total frames processed." << std::endl;
  std::cout.flush();
  _exit(0);
}
