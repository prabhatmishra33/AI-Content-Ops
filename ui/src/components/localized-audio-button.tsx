"use client";

import { useMemo, useState } from "react";

type Props = {
  locale?: string;
  textParts: Array<string | undefined | null>;
  className?: string;
  iconOnly?: boolean;
};

export function LocalizedAudioButton({ locale, textParts, className, iconOnly = false }: Props) {
  const [speaking, setSpeaking] = useState(false);
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;

  const speakableText = useMemo(
    () =>
      textParts
        .map((p) => (typeof p === "string" ? p.trim() : ""))
        .filter(Boolean)
        .join(". "),
    [textParts]
  );

  const onToggleSpeak = () => {
    if (!supported || !speakableText) return;
    const synth = window.speechSynthesis;

    if (speaking) {
      synth.cancel();
      setSpeaking(false);
      return;
    }

    const utterance = new SpeechSynthesisUtterance(speakableText);
    if (locale) utterance.lang = locale;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    setSpeaking(true);
    synth.cancel();
    synth.speak(utterance);
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
