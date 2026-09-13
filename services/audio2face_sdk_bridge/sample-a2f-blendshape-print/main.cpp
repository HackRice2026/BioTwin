// SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: MIT
//
// Real-audio-in, real-named-ARKit-blendshapes-out bridge: reads raw 16kHz
// mono float32 PCM from stdin until EOF (one full utterance), runs it
// through the actual Audio2Face-3D regression model + blendshape solver,
// and writes one JSON line per output frame to stdout. Meant to be run as
// a subprocess from a Python service exactly the way avatar_face_service
// already shells out to ffmpeg -- this is the "one shot, whole utterance"
// version, not a truly incremental/low-latency stream (see this
// directory's README for what a lower-latency version would need).

#include "audio2face/audio2face.h"
#include "audio2x/cuda_utils.h"

#include <cstdint>
#include <cstring>
#include <iostream>
#include <memory>
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

struct Destroyer {
  template <typename T> void operator()(T *obj) const {
    obj->Destroy();
  }
};
template <typename T> using UniquePtr = std::unique_ptr<T, Destroyer>;
template <typename T> UniquePtr<T> ToUniquePtr(T* ptr) { return UniquePtr<T>(ptr); }

std::vector<float> readAllStdinAsFloatPcm() {
  // Raw little-endian float32 PCM, 16kHz mono -- whatever produced this
  // stream is expected to already have resampled/decoded to that format
  // (our Python side already does this with ffmpeg for the other
  // services, so it's cheap to keep doing it there instead of teaching
  // this program to parse compressed audio too).
  std::vector<uint8_t> raw((std::istreambuf_iterator<char>(std::cin)), std::istreambuf_iterator<char>());
  std::vector<float> samples(raw.size() / sizeof(float));
  std::memcpy(samples.data(), raw.data(), samples.size() * sizeof(float));
  return samples;
}

int main(int argc, char** argv) {
  std::string modelJsonPath = argc > 1 ? argv[1]
      : TEST_DATA_DIR "_data/generated/audio2face-sdk/samples/data/mark/model.json";

  constexpr int deviceID = 0;
  CHECK_RESULT(nva2x::SetCudaDeviceIfNeeded(deviceID));

  // Explicitly calling ->Destroy() on the bundle (directly, or implicitly
  // via a UniquePtr wrapper) hung indefinitely after all real inference
  // and output was already complete -- reproduced twice, confirmed via
  // `ps` that the process was genuinely stuck, not just a slow SSH pipe.
  // outModelInfo/outBlendshapeSolveModelInfo are optional and unused here
  // anyway (pose names come from the solver itself, via
  // GetExecutorSkinSolver below). Simplest correct fix for a short-lived,
  // one-shot CLI process: don't wrap any of these in RAII, don't call
  // Destroy() on anything, just let the OS reclaim everything when the
  // process exits. Fine here; would NOT be fine in a long-lived process
  // creating many bundles (that would leak for real).
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

  const auto audioBuffer = readAllStdinAsFloatPcm();
  CHECK_ERROR(!audioBuffer.empty());
  CHECK_RESULT(
    bundle->GetAudioAccumulator(0).Accumulate(
      nva2x::HostTensorFloatConstView{audioBuffer.data(), audioBuffer.size()}, bundle->GetCudaStream().Data()
      )
    );
  CHECK_RESULT(bundle->GetAudioAccumulator(0).Close());

  std::vector<float> emptyEmotion;
  auto& emotionAccumulator = bundle->GetEmotionAccumulator(0);
  emptyEmotion.resize(emotionAccumulator.GetEmotionSize(), 0.0f);
  CHECK_RESULT(emotionAccumulator.Accumulate(
    0, nva2x::HostTensorFloatConstView{emptyEmotion.data(), emptyEmotion.size()}, bundle->GetCudaStream().Data()
    ));
  CHECK_RESULT(emotionAccumulator.Close());

  while (nva2x::GetNbReadyTracks(bundle->GetExecutor()) > 0) {
    CHECK_RESULT(bundle->GetExecutor().Execute(nullptr));
  }

  std::cerr << "Done. " << callbackData.frameIndex << " frames processed." << std::endl;
  // No explicit teardown -- see the comment where `bundle` was created.
  // All real output is already flushed to stdout above; exit immediately.
  std::cout.flush();
  _exit(0);
}
