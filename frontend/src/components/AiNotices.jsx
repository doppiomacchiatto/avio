import { useEffect, useState } from "react";

// Shown while waiting for the first token, so a long wait does not look like a hang. A local model
// (Ollama) may be loading; a cloud reasoning model may be thinking before its first word.
// Mount it only while waiting so the timer restarts for every request.
export function SlowHint({ after = 8, dark = false, local = false }) {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const t0 = Date.now();
    const id = setInterval(() => setSecs(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);
  if (secs < after) return null;
  return (
    <p className={`text-xs mt-1 ${dark ? "text-amber-300" : "text-amber-600 dark:text-amber-400"}`}>
      Still waiting for the model ({secs}s).{" "}
      {local
        ? "The first request to a local model can take a minute or two while it loads."
        : "Reasoning models can take a minute or two before the first word."}
      {" "}You can press Stop to cancel.
    </p>
  );
}

// Replaces the Send button while a reply is streaming. `onStop` is the panel's stopReply().
export function StopButton({ onStop, className = "", children = "■ Stop" }) {
  return (
    <button
      onClick={onStop}
      title="Stop this reply. What has arrived so far is kept."
      className={`shrink-0 bg-red-600 hover:bg-red-500 text-white font-semibold transition-colors ${className}`}
    >
      {children}
    </button>
  );
}

// Under a reply the user stopped. The text above is what arrived before Stop, so it may end mid-sentence.
export function StoppedNotice({ dark = false }) {
  return (
    <p className={`text-[11px] leading-snug ${dark ? "text-amber-300" : "text-amber-600 dark:text-amber-400"}`}>
      ■ Stopped by you. This answer is incomplete.
    </p>
  );
}

// "Skills used" line under an AI reply: what the backend really injected into the prompt, so
// there is no need to ask the model (its answer to "is the skill loaded?" proves nothing).
// Renders nothing for messages that carry no skills info (errors, old messages).
export function SkillsUsed({ skills, dark = false }) {
  if (!Array.isArray(skills)) return null;
  return (
    <p className={`text-[11px] leading-snug ${dark ? "text-slate-400" : "text-slate-400 dark:text-gray-500"}`}
       title="The Salesforce guidance Avio added to this request">
      🧠 Skills used: {skills.length ? skills.join(", ") : "none"}
    </p>
  );
}

// Shown under a reply that stopped because the model hit its token limit.
export function TruncatedNotice({ onContinue, disabled = false, dark = false }) {
  return (
    <div className={`flex items-center gap-3 rounded-lg border px-3 py-2 text-xs ${
      dark ? "border-amber-700 bg-amber-950/50 text-amber-200"
           : "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-200"
    }`}>
      <span className="flex-1">
        ⚠ The model hit its reply limit, so this answer is incomplete. Code above may be cut off.
      </span>
      <button
        onClick={onContinue}
        disabled={disabled}
        className="shrink-0 px-2.5 py-1 rounded bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white font-medium"
      >
        Continue
      </button>
    </div>
  );
}
