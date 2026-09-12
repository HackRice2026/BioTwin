import { api } from "./api";

/** Permission-gated recording fallback; raw audio is used only to transcribe the question. */
export function recordQuestion(callbacks: {
  recording: (active: boolean) => void;
  transcribing: (active: boolean) => void;
  question: (text: string) => void;
  error: (message: string) => void;
}) {
  const controller = new AbortController();
  let recorder: MediaRecorder | undefined;
  let stream: MediaStream | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const release = () => {
    clearTimeout(timer);
    stream?.getTracks().forEach((track) => track.stop());
  };
  const stop = () => {
    if (recorder?.state === "recording") recorder.stop();
  };
  const abort = () => {
    controller.abort();
    stop();
    release();
  };
  void (async () => {
    try {
      if (
        !navigator.mediaDevices?.getUserMedia ||
        typeof MediaRecorder === "undefined"
      )
        throw new Error(
          "Microphone recording is unavailable in this browser. Type your question below.",
        );
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (controller.signal.aborted) {
        release();
        return;
      }
      const mimeType = [
        "audio/webm;codecs=opus",
        "audio/mp4",
        "audio/ogg;codecs=opus",
      ].find((type) => MediaRecorder.isTypeSupported(type));
      if (!mimeType)
        throw new Error(
          "This browser has no supported recording format. Type your question below.",
        );
      recorder = new MediaRecorder(stream, { mimeType });
      const chunks: Blob[] = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data);
      };
      recorder.onerror = () => {
        if (!controller.signal.aborted) {
          callbacks.recording(false);
          callbacks.error(
            "Microphone recording failed. Type your question or try again.",
          );
          abort();
        }
      };
      recorder.onstop = async () => {
        release();
        if (controller.signal.aborted) return;
        callbacks.recording(false);
        callbacks.transcribing(true);
        const timeout = setTimeout(() => {
          callbacks.transcribing(false);
          callbacks.error(
            "Transcription timed out. Try again or type your question.",
          );
          controller.abort();
        }, 30000);
        try {
          const blob = new Blob(chunks, { type: mimeType });
          if (!blob.size || blob.size > 5 * 1024 * 1024)
            throw new Error(
              "The recording was empty or too large. Try a shorter question.",
            );
          const form = new FormData();
          form.append("audio", blob, "question.audio");
          const response = await api<{ question: string }>(
            "/api/twin/transcribe",
            { method: "POST", body: form, signal: controller.signal },
          );
          if (!controller.signal.aborted) callbacks.question(response.question);
        } catch (error) {
          if (!controller.signal.aborted)
            callbacks.error((error as Error).message);
        } finally {
          clearTimeout(timeout);
          if (!controller.signal.aborted) callbacks.transcribing(false);
        }
      };
      recorder.start();
      callbacks.recording(true);
      timer = setTimeout(stop, 30000);
    } catch (error) {
      release();
      if (!controller.signal.aborted) {
        callbacks.recording(false);
        callbacks.error(
          (error as Error).message ||
            "Microphone access was denied. Type your question instead.",
        );
      }
    }
  })();
  return { stop, abort };
}
