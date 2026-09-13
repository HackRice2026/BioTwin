// SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: MIT
//
// Real, named ARKit-style blendshape weights from the actual Audio2Face-3D
// regression model + its blendshape solver, printed to stdout as CSV
// (frame,name,value) so this can be verified/consumed without needing a
// custom binary protocol yet. Built to answer one question: does this
// SDK's own blendshape-solve path actually produce named, ARKit-compatible
// output on real audio -- not the raw per-character geometry path used by
// the other samples.

#include "audio2face/audio2face.h"
#include "audio2x/cuda_utils.h"

#include <cstdint>
#include "AudioFile.h"

#include <any>
#include <iostream>
#include <memory>
#include <vector>

#define CHECK_RESULT(func)                                                     \
  {                                                                            \
    std::error_code error = (func);                                            \
    if (error) {                                                               \
      std::cout << "Error (" << __LINE__ << "): Failed to execute: " << #func; \
      std::cout << ", Reason: "<< error.message() << std::endl;                \
      exit(1);                                                                 \
    }                                                                          \
  }

#define CHECK_ERROR(expression)                                                \
  {                                                                            \
    if (!(expression)) {                                                       \
      std::cout << "Error (" << __LINE__ << "): " << #expression;              \
      std::cout << " is NULL" << std::endl;                                    \
      exit(1);                                                                 \
    }                                                                          \
  }

struct Destroyer {
  template <typename T> void operator()(T *obj) const {
    obj->Destroy();
  }
};
template <typename T> using UniquePtr = std::unique_ptr<T, Destroyer>;
template <typename T> UniquePtr<T> ToUniquePtr(T* ptr) { return UniquePtr<T>(ptr); }

std::vector<float> loadAudio() {
  constexpr std::string_view audioFilePath = TEST_DATA_DIR "sample-data/audio_4sec_16k_s16le.wav";
  AudioFile<float> audioFile;
  std::cout << "Loading audio file: " << audioFilePath << std::endl;
  CHECK_ERROR(audioFile.load(audioFilePath.data()));
  audioFile.printSummary();
  CHECK_ERROR(audioFile.getSampleRate() == 16000);
  return audioFile.samples[0];
}

int main(void) {
  std::cout << "================================================" << std::endl;
  std::cout << "    Audio2Face SDK -- real named blendshape print" << std::endl;
  std::cout << "================================================" << std::endl;

  constexpr int deviceID = 0;
  CHECK_RESULT(nva2x::SetCudaDeviceIfNeeded(deviceID));

  constexpr char filename[] = TEST_DATA_DIR "_data/generated/audio2face-sdk/samples/data/mark/model.json";
  nva2f::IRegressionModel::IGeometryModelInfo* modelInfoPtr = nullptr;
  nva2f::IRegressionModel::IBlendshapeSolveModelInfo* blendshapeInfoPtr = nullptr;
  auto bundle = ToUniquePtr(
    nva2f::ReadRegressionBlendshapeSolveExecutorBundle(
      1,
      filename,
      nva2f::IGeometryExecutor::ExecutionOption::Skin,
      /*useGpuSolver=*/false,
      60, 1,
      &modelInfoPtr,
      &blendshapeInfoPtr
      )
    );
  CHECK_ERROR(bundle);
  auto modelInfo = ToUniquePtr(modelInfoPtr);
  auto blendshapeInfo = ToUniquePtr(blendshapeInfoPtr);

  // Real, verified blendshape names -- pulled straight from the solver this
  // bundle just built, not assumed from the bs_skin.npz inspection done
  // separately in Python.
  nva2f::IBlendshapeSolver* skinSolver = nullptr;
  CHECK_RESULT(nva2f::GetExecutorSkinSolver(bundle->GetExecutor(), 0, &skinSolver));
  CHECK_ERROR(skinSolver);
  const int numPoses = skinSolver->NumBlendshapePoses();
  std::cout << "# solver reports " << numPoses << " named blendshape poses:" << std::endl;
  std::vector<std::string> poseNames;
  for (int i = 0; i < numPoses; ++i) {
    poseNames.push_back(skinSolver->GetPoseName(i));
    std::cout << "#   [" << i << "] " << poseNames.back() << std::endl;
  }

  struct CallbackData {
    std::size_t frameIndex = 0;
    const std::vector<std::string>* names;
  };
  CallbackData callbackData;
  callbackData.names = &poseNames;

  auto callback = [](void* userdata, const nva2f::IBlendshapeExecutor::HostResults& results, std::error_code errorCode) {
    auto& data = *static_cast<CallbackData*>(userdata);
    if (errorCode) {
      std::cout << "Error in results callback: " << errorCode.message() << std::endl;
      return;
    }
    // Only print a handful of frames -- this is a verification run, not a full export.
    if (data.frameIndex % 20 == 0) {
      std::cout << "frame " << data.frameIndex << ":";
      for (std::size_t i = 0; i < results.weights.Size() && i < data.names->size(); ++i) {
        float value = results.weights.Data()[i];
        if (value > 0.05f) {
          std::cout << " " << (*data.names)[i] << "=" << value;
        }
      }
      std::cout << std::endl;
    }
    data.frameIndex++;
  };
  CHECK_RESULT(bundle->GetExecutor().SetResultsCallback(callback, &callbackData));

  const auto audioBuffer = loadAudio();
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

  std::cout << "Done. " << callbackData.frameIndex << " frames processed." << std::endl;
  return 0;
}
