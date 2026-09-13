/** Streams MP3 when supported; keeps completed audio in memory for gesture/replay retries. */
import { emitAvatarAudio } from "./avatar/avatarBus";

export type VoiceEvents = {
  speaking: (active: boolean) => void;
  status: (message: string) => void;
  error: (message: string) => void;
  blocked?: () => void;
};
function event(
  target: EventTarget,
  name: string,
  signal: AbortSignal,
  start?: () => void,
) {
  return new Promise<void>((resolve, reject) => {
    const clean = () => {
      target.removeEventListener(name, done);
      target.removeEventListener("error", fail);
      signal.removeEventListener("abort", abort);
    };
    const done = () => {
      clean();
      resolve();
    };
    const fail = () => {
      clean();
      reject(new Error("Audio could not be decoded."));
    };
    const abort = () => {
      clean();
      reject(new DOMException("Stopped", "AbortError"));
    };
    target.addEventListener(name, done, { once: true });
    target.addEventListener("error", fail, { once: true });
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    else if (start) {
      try {
        start();
      } catch (error) {
        clean();
        reject(error);
      }
    }
  });
}

export class TwinVoice {
  private player = new Audio();
  private controller?: AbortController;
  private urls: string[] = [];
  private cached?: string;
  private events?: VoiceEvents;
  conversationId?: string;

  stop() {
    this.controller?.abort();
    this.player.onplaying =
      this.player.onended =
      this.player.onerror =
      this.player.onpause =
        null;
    this.player.pause();
    this.player.removeAttribute("src");
    this.player.load();
    this.urls.forEach((url) => URL.revokeObjectURL(url));
    this.urls = [];
    this.cached = undefined;
    this.conversationId = undefined;
    this.events?.speaking(false);
    this.events = undefined;
  }

  async resume() {
    if (this.cached && (this.player.ended || this.player.error))
      this.player.src = this.cached;
    if (this.player.ended) this.player.currentTime = 0;
    try {
      await this.player.play();
    } catch (error) {
      if ((error as Error).name === "NotAllowedError") {
        this.events?.status("Tap to hear your twin’s answer.");
        this.events?.blocked?.();
      } else if ((error as Error).name !== "AbortError") {
        this.events?.speaking(false);
        this.events?.error(
          "Speech could not play. Your text answer is saved below.",
        );
      }
    }
  }

  async play(id: string, url: string, events: VoiceEvents) {
    this.stop();
    this.conversationId = id;
    this.events = events;
    const controller = new AbortController();
    this.controller = controller;
    const { signal } = controller;
    this.player.onplaying = () => {
      events.speaking(true);
      events.status("Your twin is speaking…");
    };
    this.player.onended = () => {
      events.speaking(false);
      events.status("");
    };
    this.player.onpause = () => events.speaking(false);
    this.player.onerror = () => {
      if (!signal.aborted) {
        if (!this.cached) this.conversationId = undefined;
        events.speaking(false);
        events.error(
          "Speech was interrupted. Your text answer is saved below.",
        );
      }
    };
    events.status("Preparing your twin’s voice…");
    try {
      const response = await fetch(url, { credentials: "include", signal });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : "ElevenLabs is unavailable. Your text answer is saved.",
        );
      }
      if (!response.headers.get("content-type")?.startsWith("audio/"))
        throw new Error(
          "No usable speech was returned. Your text answer is saved.",
        );
      const canStream =
        typeof MediaSource !== "undefined" &&
        MediaSource.isTypeSupported("audio/mpeg") &&
        response.body;
      console.log("[avatar-debug] voice canStream:", canStream);
      if (!canStream) {
        console.warn(
          "[avatar-debug] MediaSource streaming unavailable -- falling back to a plain <audio> blob. " +
            "emitAvatarAudio() is never called on this path, so the avatar face/body will NOT move.",
        );
        const blob = await response.blob();
        if (!blob.size)
          throw new Error(
            "ElevenLabs returned empty audio. Your text answer is saved.",
          );
        if (signal.aborted) return;
        this.cached = URL.createObjectURL(blob);
        this.urls.push(this.cached);
        this.player.src = this.cached;
        await this.resume();
        return;
      }
      const media = new MediaSource();
      const opened = event(media, "sourceopen", signal);
      const mediaUrl = URL.createObjectURL(media);
      this.urls.push(mediaUrl);
      this.player.src = mediaUrl;
      await opened;
      const buffer = media.addSourceBuffer("audio/mpeg");
      const reader = response.body!.getReader();
      const chunks: ArrayBuffer[] = [];
      let started = false;
      while (true) {
        const { value, done } = await reader.read();
        if (signal.aborted) return;
        if (done) break;
        const bytes = new Uint8Array(value).buffer;
        chunks.push(bytes);
        console.log("[avatar-debug] emitAvatarAudio chunk bytes:", bytes.byteLength);
        emitAvatarAudio(bytes.slice(0));
        await event(buffer, "updateend", signal, () =>
          buffer.appendBuffer(bytes),
        );
        if (!started) {
          started = true;
          void this.resume();
        }
      }
      if (!chunks.length)
        throw new Error(
          "ElevenLabs returned empty audio. Your text answer is saved.",
        );
      if (media.readyState === "open") media.endOfStream();
      this.cached = URL.createObjectURL(
        new Blob(chunks, { type: "audio/mpeg" }),
      );
      this.urls.push(this.cached);
    } catch (error) {
      if (signal.aborted) return;
      this.player.pause();
      this.conversationId = undefined;
      events.speaking(false);
      events.error(
        (error as Error).message ||
          "Speech is unavailable. Your text answer is saved.",
      );
    }
  }
}
