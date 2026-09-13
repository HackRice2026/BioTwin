/**
 * Gemini Live: one WebSocket carrying your voice out and the twin's voice back.
 *
 * The socket goes to our own server, not to Google. Ephemeral tokens are refused
 * by this project ("unregistered callers"), and the only other way to reach Gemini
 * from a browser is to ship it the API key, which would publish the key to anyone
 * who opens devtools. So the server relays, holds the key, and sends the setup --
 * including the grounding -- before this file's first frame. Nothing here decides
 * what the twin may say; it only moves audio.
 *
 * Two sample rates, because the API uses two: microphone audio goes up as 16 kHz
 * signed 16-bit PCM, and the model's speech comes back as 24 kHz of the same. They
 * are not interchangeable; playing the reply at the capture rate is what makes a
 * voice sound slowed down.
 */
type Session = {
  model: string;
  voice: string;
  input_sample_rate: number;
  output_sample_rate: number;
  input_mime_type: string;
};

/** The relay lives on the same origin, so it follows the page's scheme. */
function relayUrl() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/ws/twin/live`;
}

export type LiveState = "idle" | "connecting" | "listening" | "speaking" | "error";

type Handlers = {
  onState: (state: LiveState, detail?: string) => void;
  /** Transcript text, when the model returns any alongside the audio. */
  onText?: (text: string) => void;
};

const CHUNK = 2048;

export class GeminiLive {
  private socket: WebSocket | null = null;
  private capture: AudioContext | null = null;
  private playback: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: ScriptProcessorNode | null = null;
  /** When the next reply chunk should start, so consecutive chunks play gapless. */
  private playhead = 0;
  private session: Session | null = null;
  private closing = false;

  constructor(private handlers: Handlers) {}

  get active() {
    return this.socket !== null;
  }

  async start() {
    if (this.socket) return;
    this.closing = false;
    this.handlers.onState("connecting");

    let stream: MediaStream;
    try {
      // Ask for the microphone first: a declined permission should not leave a
      // live Gemini session open and billing.
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch {
      this.handlers.onState(
        "error",
        "Microphone access was declined. Allow it in the browser to talk to your twin.",
      );
      return;
    }
    this.stream = stream;

    const socket = new WebSocket(relayUrl());
    socket.binaryType = "arraybuffer";
    this.socket = socket;

    socket.onmessage = (event) => void this.receive(event);
    socket.onerror = () => {
      if (!this.closing) this.handlers.onState("error", "The live connection dropped.");
    };
    socket.onclose = (event) => {
      if (this.closing) return;
      this.teardown();
      this.handlers.onState(
        event.code === 1000 ? "idle" : "error",
        event.code === 1000 ? undefined : event.reason || "The live connection closed.",
      );
    };
  }

  stop() {
    this.closing = true;
    try {
      this.socket?.close(1000, "done");
    } catch {
      /* already gone */
    }
    this.teardown();
    this.handlers.onState("idle");
  }

  private async openMicrophone(session: Session) {
    const capture = new AudioContext({ sampleRate: session.input_sample_rate });
    this.capture = capture;
    const source = capture.createMediaStreamSource(this.stream!);
    // ScriptProcessor rather than an AudioWorklet: a worklet needs its own module
    // file, and the artifact of that extra build step is not worth it for a mono
    // 16 kHz downmix.
    const node = capture.createScriptProcessor(CHUNK, 1, 1);
    this.node = node;
    node.onaudioprocess = (event) => {
      if (this.socket?.readyState !== WebSocket.OPEN) return;
      const input = event.inputBuffer.getChannelData(0);
      this.socket.send(
        JSON.stringify({
          realtimeInput: {
            audio: { mimeType: session.input_mime_type, data: toBase64Pcm16(input) },
          },
        }),
      );
    };
    source.connect(node);
    // Connected to the destination with no gain: some browsers stop pulling audio
    // through a ScriptProcessor that terminates nowhere.
    const silent = capture.createGain();
    silent.gain.value = 0;
    node.connect(silent);
    silent.connect(capture.destination);
    this.handlers.onState("listening");
  }

  private async receive(event: MessageEvent) {
    const raw =
      typeof event.data === "string"
        ? event.data
        : new TextDecoder().decode(event.data as ArrayBuffer);
    let message: Record<string, any>;
    try {
      message = JSON.parse(raw);
    } catch {
      return;
    }

    // The relay speaks first, with the rates Gemini expects; capture starts only
    // once those are known, so nothing is encoded at the wrong sample rate.
    if (message.ready) {
      this.session = message.ready as Session;
      void this.openMicrophone(this.session);
      return;
    }
    if (message.setupComplete) return;
    if (message.error) {
      this.handlers.onState("error", message.error.message ?? "Gemini reported an error.");
      return;
    }

    const content = message.serverContent;
    if (!content) return;

    // The user started talking over the reply: drop what is queued so the twin
    // stops mid-sentence like a person would, instead of finishing its turn.
    if (content.interrupted) {
      this.resetPlayback();
      this.handlers.onState("listening");
      return;
    }

    for (const part of content.modelTurn?.parts ?? []) {
      if (part.text) this.handlers.onText?.(part.text);
      const audio = part.inlineData?.data;
      if (audio) this.play(audio, this.session?.output_sample_rate ?? 24000);
    }
    if (content.turnComplete) this.handlers.onState("listening");
  }

  private play(base64: string, rate: number) {
    const playback =
      this.playback ?? (this.playback = new AudioContext({ sampleRate: rate }));
    const pcm = fromBase64Pcm16(base64);
    const buffer = playback.createBuffer(1, pcm.length, rate);
    // set() rather than copyToChannel: the latter's typed-array generic rejects
    // a Float32Array whose backing buffer TypeScript cannot prove is unshared.
    buffer.getChannelData(0).set(pcm);
    const source = playback.createBufferSource();
    source.buffer = buffer;
    source.connect(playback.destination);
    // Queue against a playhead rather than playing on arrival: chunks land faster
    // than real time, and starting each one immediately overlaps them into noise.
    const startAt = Math.max(playback.currentTime, this.playhead);
    source.start(startAt);
    this.playhead = startAt + buffer.duration;
    this.handlers.onState("speaking");
  }

  private resetPlayback() {
    void this.playback?.close();
    this.playback = null;
    this.playhead = 0;
  }

  private teardown() {
    this.node?.disconnect();
    this.node = null;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    void this.capture?.close();
    this.capture = null;
    this.resetPlayback();
    this.session = null;
    this.socket = null;
  }
}

/** Float32 [-1,1] to base64 signed 16-bit little-endian PCM. */
export function toBase64Pcm16(input: Float32Array): string {
  const out = new DataView(new ArrayBuffer(input.length * 2));
  for (let i = 0; i < input.length; i++) {
    // Clamp before scaling: a sample above 1 would wrap to a loud negative click.
    const clamped = Math.max(-1, Math.min(1, input[i]));
    out.setInt16(i * 2, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
  }
  let binary = "";
  const bytes = new Uint8Array(out.buffer);
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

/** base64 signed 16-bit little-endian PCM back to Float32 [-1,1]. */
export function fromBase64Pcm16(base64: string): Float32Array {
  const binary = atob(base64);
  const view = new DataView(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i++) view.setUint8(i, binary.charCodeAt(i));
  const samples = new Float32Array(binary.length / 2);
  for (let i = 0; i < samples.length; i++) {
    samples[i] = view.getInt16(i * 2, true) / 0x8000;
  }
  return samples;
}
