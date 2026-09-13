/** Streams MP3 when supported; keeps completed audio in memory for gesture/replay retries. */
import { CaptionTimeline, type Alignment, type CaptionWord } from "./captions";
import { emitAvatarAudio } from "./avatar/avatarBus";

export type VoiceEvents = {
  speaking: (active: boolean) => void;
  status: (message: string) => void;
  error: (message: string) => void;
  blocked?: () => void;
  ended?: () => void;
  captions?: (words: CaptionWord[], currentTime: number) => void;
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
  private timeline = new CaptionTimeline();
  conversationId?: string;

  stop() {
    this.controller?.abort();
    this.player.onplaying =
      this.player.onended =
      this.player.onerror =
      this.player.onpause =
      this.player.ontimeupdate =
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
    this.timeline = new CaptionTimeline();
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
      events.ended?.();
    };
    this.player.ontimeupdate = () => events.captions?.(this.timeline.words(), this.player.currentTime);
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
      const timed = response.headers.get("content-type")?.includes("ndjson");
      if (!timed && !response.headers.get("content-type")?.startsWith("audio/"))
        throw new Error(
          "No usable speech was returned. Your text answer is saved.",
        );
      const canStream =
        typeof MediaSource !== "undefined" &&
        MediaSource.isTypeSupported("audio/mpeg") &&
        response.body;
      const chunks: ArrayBuffer[] = [];
      let media: MediaSource | undefined;
      let buffer: SourceBuffer | undefined;
      if (canStream) {
        media = new MediaSource();
        const opened = event(media, "sourceopen", signal);
        const mediaUrl = URL.createObjectURL(media);
        this.urls.push(mediaUrl);
        this.player.src = mediaUrl;
        await opened;
        buffer = media.addSourceBuffer("audio/mpeg");
      }
      let started = false;
      const append = async (bytes: ArrayBuffer) => {
        if (signal.aborted || !bytes.byteLength) return;
        chunks.push(bytes);
        emitAvatarAudio(bytes.slice(0));
        if (buffer) {
          await event(buffer, "updateend", signal, () => buffer!.appendBuffer(bytes));
          if (!started) { started = true; void this.resume(); }
        }
      };
      const reader = response.body?.getReader();
      if (!reader) throw new Error("No speech stream was returned. Your text answer is saved.");
      const decoder = new TextDecoder();
      let pending = "";
      const processLine = async (line: string) => {
        if (!line.trim()) return;
        const chunk = JSON.parse(line) as { audio_base64?: string; alignment?: Alignment; normalized_alignment?: Alignment };
        this.timeline.append(chunk.normalized_alignment ?? chunk.alignment);
        if (chunk.audio_base64) {
          const bytes = Uint8Array.from(atob(chunk.audio_base64), c => c.charCodeAt(0));
          await append(bytes.buffer);
        }
      };
      while (true) {
        const { value, done } = await reader.read();
        if (signal.aborted) return;
        if (done) break;
        if (timed) {
          pending += decoder.decode(value, { stream: true });
          let index: number;
          while ((index = pending.indexOf("\n")) >= 0) {
            const line = pending.slice(0, index); pending = pending.slice(index + 1);
            await processLine(line);
          }
        } else await append(new Uint8Array(value).buffer);
      }
      if (timed) await processLine(pending + decoder.decode());
      if (!chunks.length)
        throw new Error(
          "ElevenLabs returned empty audio. Your text answer is saved.",
        );
      if (media?.readyState === "open") media.endOfStream();
      this.cached = URL.createObjectURL(
        new Blob(chunks, { type: "audio/mpeg" }),
      );
      this.urls.push(this.cached);
      if (!canStream) { this.player.src = this.cached; await this.resume(); }
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
