import { useEffect, useRef, useState } from "react";
import { api, post, type OfflineBundle, type Session } from "./api";
import type { Conversation } from "./contracts";
import { TwinVoice } from "./voice";
import { recordQuestion } from "./microphone";

export type Reply = {
  id?: string;
  answer: string;
  mode: string;
  notice?: string | null;
  created_at?: string;
  reply_id?: string;
  voice_configured?: boolean;
};
type Turn = {
  id: string;
  question: string;
  answer?: string | null;
  created_at: string;
  reply?: Reply;
};
type History = { conversations: Conversation[]; next_before: string | null };

export function useTwinConversation({
  open,
  online,
  bundle,
  session,
  accountKey,
}: {
  open: boolean;
  online: boolean;
  bundle: OfflineBundle | null;
  session: Session | null;
  accountKey: number;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [voiceNotice, setVoiceNotice] = useState("");
  const [voiceError, setVoiceError] = useState(false);
  const voice = useRef<TwinVoice | null>(null);
  const epoch = useRef(0);
  const busy = useRef(false);
  const speechRequest = useRef(0);
  const recognition = useRef<any>(null);
  const recording = useRef<ReturnType<typeof recordQuestion> | null>(null);
  const askController = useRef<AbortController | null>(null);
  const openNow = useRef(open);
  openNow.current = open;

  function stopSpeaking() {
    speechRequest.current++;
    voice.current?.stop();
    setSpeaking(false);
    setVoiceNotice("");
  }
  function reset() {
    epoch.current++;
    busy.current = false;
    askController.current?.abort();
    recognition.current?.abort();
    recognition.current = null;
    recording.current?.abort();
    stopSpeaking();
    setTurns([]);
    setQuestion("");
    setAsking(false);
    setListening(false);
    setTranscribing(false);
    setNextBefore(null);
    setHistoryError("");
    setHistoryBusy(false);
  }
  useEffect(() => {
    reset();
  }, [accountKey]);
  useEffect(
    () => () => {
      epoch.current++;
      speechRequest.current++;
      askController.current?.abort();
      recognition.current?.abort();
      recording.current?.abort();
      voice.current?.stop();
    },
    [],
  );
  useEffect(() => {
    if (!open) {
      stopSpeaking();
      recognition.current?.abort();
      recording.current?.abort();
      setListening(false);
      setTranscribing(false);
    }
  }, [open]);

  async function loadHistory(before?: string) {
    if (!online || !session) return;
    const currentEpoch = epoch.current;
    setHistoryBusy(true);
    setHistoryError("");
    try {
      const history = await api<History>(
        `/api/twin/conversations${before ? `?before=${encodeURIComponent(before)}` : ""}`,
      );
      if (currentEpoch !== epoch.current) return;
      const incoming = history.conversations.map((row): Turn => ({
        ...row,
        answer:
          row.answer ??
          "No completed answer was saved for this question. Please ask again.",
        reply: row.answer
          ? {
              ...row,
              answer: row.answer,
              voice_configured: session.voice_configured,
            }
          : undefined,
      }));
      setTurns((previous) => {
        const merged = new Map(incoming.map((row) => [row.id, row]));
        for (const row of previous)
          if (!merged.has(row.id) || row.reply?.reply_id)
            merged.set(row.id, row);
        return [...merged.values()].sort(
          (a, b) =>
            a.created_at.localeCompare(b.created_at) ||
            a.id.localeCompare(b.id),
        );
      });
      setNextBefore(history.next_before);
    } catch {
      if (currentEpoch === epoch.current)
        setHistoryError(
          "Saved conversations are unavailable. Your current conversation is still visible.",
        );
    } finally {
      if (currentEpoch === epoch.current) setHistoryBusy(false);
    }
  }
  useEffect(() => {
    if (open) void loadHistory();
  }, [open, online, session?.user.id, accountKey]);

  async function speak(reply: Reply) {
    if (!online || !reply.voice_configured || !reply.id) {
      setVoiceError(true);
      setVoiceNotice(
        "Speech is unavailable. Your text answer is available below.",
      );
      return;
    }
    setVoiceError(false);
    if (voice.current?.conversationId === reply.id) {
      await voice.current.resume();
      return;
    }
    stopSpeaking();
    const request = ++speechRequest.current;
    const currentEpoch = epoch.current;
    setVoiceNotice("Preparing your twin’s voice…");
    try {
      // Renew the short-lived ticket for older transcripts and failed/expired audio requests.
      const ticket = reply.reply_id
        ? { reply_id: reply.reply_id }
        : await post<{ reply_id: string }>(
            `/api/twin/conversations/${encodeURIComponent(reply.id)}/speech`,
          );
      reply.reply_id = undefined;
      if (request !== speechRequest.current || currentEpoch !== epoch.current)
        return;
      if (!voice.current) voice.current = new TwinVoice();
      await voice.current.play(reply.id, `/api/voice/${ticket.reply_id}`, {
        speaking: setSpeaking,
        status: setVoiceNotice,
        error: (message) => {
          setVoiceError(true);
          setVoiceNotice(message);
        },
      });
    } catch (error) {
      if (request !== speechRequest.current || currentEpoch !== epoch.current)
        return;
      setSpeaking(false);
      setVoiceError(true);
      setVoiceNotice(
        (error as Error).message ||
          "Speech is unavailable. Your text answer is saved.",
      );
    }
  }

  async function ask(text: string) {
    text = text.trim();
    if (!text || busy.current) return;
    busy.current = true;
    const currentEpoch = epoch.current;
    stopSpeaking();
    recognition.current?.abort();
    recording.current?.abort();
    setListening(false);
    setTranscribing(false);
    setQuestion("");
    setAsking(true);
    const id = crypto.randomUUID();
    setTurns((rows) => [
      ...rows,
      { id, question: text, created_at: new Date().toISOString() },
    ]);
    const controller = new AbortController();
    askController.current = controller;
    const timeout = setTimeout(() => controller.abort(), 35000);
    try {
      let reply: Reply;
      if (!online && bundle) {
        const key = /recover|predict/i.test(text)
          ? "recovery"
          : /sleep/i.test(text)
            ? "sleep"
            : /plan|nap|workout/i.test(text)
              ? "plan"
              : "readiness";
        reply = {
          answer: `Offline example: ${bundle.answers[key] ?? "Reconnect to ask about your personal measurements."}`,
          mode: "offline",
          notice:
            "This public offline example is not saved to your personal transcript.",
        };
      } else {
        reply = await api<Reply>("/api/twin/ask", {
          method: "POST",
          body: JSON.stringify({ question: text, request_id: id }),
          signal: controller.signal,
        });
      }
      if (currentEpoch !== epoch.current) return;
      setTurns((rows) =>
        rows.map((row) =>
          row.id === id
            ? {
                ...row,
                answer: reply.answer,
                reply,
                created_at: reply.created_at ?? row.created_at,
              }
            : row,
        ),
      );
      if (reply.voice_configured) {
        if (openNow.current) void speak(reply);
      } else {
        setVoiceError(true);
        setVoiceNotice(
          online
            ? "ElevenLabs is unavailable. Your text answer is saved."
            : "Voice needs an internet connection.",
        );
      }
    } catch (error) {
      if (currentEpoch !== epoch.current) return;
      setTurns((rows) =>
        rows.map((row) =>
          row.id === id
            ? {
                ...row,
                answer: `Your twin is unavailable. ${(error as Error).name === "AbortError" ? "The response timed out. Reopen the conversation to check saved history, or try again." : (error as Error).message}`,
              }
            : row,
        ),
      );
    } finally {
      clearTimeout(timeout);
      if (currentEpoch === epoch.current) {
        busy.current = false;
        setAsking(false);
      }
    }
  }

  function startRecording() {
    const currentEpoch = epoch.current;
    recording.current?.abort();
    recording.current = recordQuestion({
      recording: (active) => {
        if (currentEpoch === epoch.current) setListening(active);
      },
      transcribing: (active) => {
        if (currentEpoch === epoch.current) setTranscribing(active);
      },
      question: (text) => {
        if (currentEpoch === epoch.current) {
          setTranscribing(false);
          void ask(text);
        }
      },
      error: (message) => {
        if (currentEpoch === epoch.current) {
          setTranscribing(false);
          setVoiceError(true);
          setVoiceNotice(message);
        }
      },
    });
  }
  function microphone() {
    if (listening) {
      recognition.current?.stop();
      recording.current?.stop();
      return;
    }
    const Recognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;
    if (!Recognition) {
      stopSpeaking();
      setVoiceError(false);
      startRecording();
      return;
    }
    stopSpeaking();
    setVoiceError(false);
    const currentEpoch = epoch.current;
    const input = new Recognition();
    recognition.current = input;
    input.lang = "en-US";
    input.interimResults = false;
    input.continuous = false;
    input.onstart = () => {
      if (currentEpoch === epoch.current) setListening(true);
    };
    input.onend = () => {
      if (currentEpoch === epoch.current) setListening(false);
    };
    input.onresult = (event: any) => {
      if (currentEpoch !== epoch.current) return;
      const text = event.results[0]?.[0]?.transcript?.trim();
      if (text) void ask(text);
    };
    input.onerror = (event: any) => {
      if (currentEpoch !== epoch.current || event.error === "aborted") return;
      setListening(false);
      if (event.error === "network") {
        startRecording();
        return;
      }
      setVoiceError(true);
      setVoiceNotice(
        "Microphone input was unavailable. You can type your question.",
      );
    };
    try {
      input.start();
    } catch {
      setVoiceError(true);
      setVoiceNotice(
        "Microphone input could not start. Type your question below.",
      );
    }
  }
  const messages = turns.flatMap((turn) => [
    {
      key: `${turn.id}:user`,
      role: "user",
      text: turn.question,
      created_at: turn.created_at,
      reply: undefined as Reply | undefined,
    },
    ...(turn.answer
      ? [
          {
            key: `${turn.id}:twin`,
            role: "twin",
            text: turn.answer,
            created_at: turn.created_at,
            reply: turn.reply,
          },
        ]
      : []),
  ]);
  return {
    messages,
    question,
    setQuestion,
    asking: asking || transcribing,
    transcribing,
    speaking,
    listening,
    historyBusy,
    historyError,
    nextBefore,
    voiceNotice,
    voiceError,
    ask,
    speak,
    microphone,
    stopSpeaking,
    reset,
    loadHistory,
  };
}
