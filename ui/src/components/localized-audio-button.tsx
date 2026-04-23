"use client";

import { useMemo, useRef, useState } from "react";

type Props = {
  locale?: string;
  textParts: Array<string | undefined | null>;
  className?: string;
  iconOnly?: boolean;
};

export function LocalizedAudioButton({ locale, textParts, className, iconOnly = false }: Props) {
  const [speaking, setSpeaking] = useState(false);
  const cancelRequestedRef = useRef(false);
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;

  const speakableText = useMemo(
    () =>
      textParts
        .map((p) => (typeof p === "string" ? p.trim() : ""))
        .filter(Boolean)
        .join(". "),
    [textParts]
  );

  const splitIntoChunks = (text: string, maxLen = 220): string[] => {
    const normalized = text.replace(/\s+/g, " ").trim();
    if (!normalized) return [];
    const parts = normalized.split(/(?<=[.!?।])\s+/);
    const chunks: string[] = [];
    let current = "";
    for (const p of parts) {
      if (!p) continue;
      if (!current) {
        current = p;
        continue;
      }
      if (`${current} ${p}`.length <= maxLen) {
        current = `${current} ${p}`;
      } else {
        chunks.push(current);
        current = p;
      }
    }
    if (current) chunks.push(current);
    return chunks;
  };

  const pickVoice = (localeValue: string | undefined): SpeechSynthesisVoice | null => {
    if (!localeValue) return null;
    const synth = window.speechSynthesis;
    const voices = synth.getVoices();
    if (!voices.length) return null;
    const target = localeValue.toLowerCase();
    const exact = voices.find((v) => v.lang.toLowerCase() === target);
    if (exact) return exact;
    const base = target.split("-")[0];
    const baseMatch = voices.find((v) => v.lang.toLowerCase().startsWith(`${base}-`) || v.lang.toLowerCase() === base);
    return baseMatch ?? null;
  };

  const speakChunk = (synth: SpeechSynthesis, text: string, localeValue: string | undefined) =>
    new Promise<void>((resolve, reject) => {
      const utterance = new SpeechSynthesisUtterance(text);
      const voice = pickVoice(localeValue);
      if (voice) {
        utterance.voice = voice;
        utterance.lang = voice.lang;
      } else if (localeValue) {
        utterance.lang = localeValue;
      }
      utterance.onend = () => resolve();
      utterance.onerror = () => reject(new Error("Speech synthesis failed"));
      synth.speak(utterance);
    });

  const onToggleSpeak = async () => {
    if (!supported || !speakableText) return;
    const synth = window.speechSynthesis;

    if (speaking) {
      cancelRequestedRef.current = true;
      synth.cancel();
      setSpeaking(false);
      return;
    }

    setSpeaking(true);
    cancelRequestedRef.current = false;
    synth.cancel();
    synth.resume();

    try {
      const chunks = splitIntoChunks(speakableText);
      for (const chunk of chunks) {
        if (cancelRequestedRef.current) break;
        // eslint-disable-next-line no-await-in-loop
        await speakChunk(synth, chunk, locale);
      }
    } catch {
      // no-op: fallback is handled by stopping speaking state
    } finally {
      setSpeaking(false);
    }
  };

  return (
    <button
      type="button"
      className={`btn-secondary ${className ?? ""}`}
      disabled={!supported || !speakableText}
      onClick={onToggleSpeak}
      aria-label={speaking ? "Stop audio" : "Play audio"}
      title={!supported ? "Audio playback is not supported in this browser." : !speakableText ? "No localized text available yet." : ""}
    >
      <span className={`inline-flex items-center ${iconOnly ? "" : "gap-2"}`}>
        {iconOnly ? (
          speaking ? (
            <svg aria-hidden="true" className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
              <rect height="14" rx="1.5" width="14" x="5" y="5" />
            </svg>
          ) : (
            <svg aria-hidden="true" className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7-11-7Z" />
            </svg>
          )
        ) : (
          <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24">
            <path d="M4 10v4h4l5 4V6L8 10H4Z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
            <path d="M16 9a4 4 0 0 1 0 6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
            <path d="M18.5 6.5a8 8 0 0 1 0 11" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
          </svg>
        )}
        {iconOnly ? null : speaking ? "Stop Audio" : "Listen"}
      </span>
    </button>
  );
}
