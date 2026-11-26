import { useEffect } from "react";
import DebugLogView from "./DebugLogView";

// The debug log over the startup org picker, where the bottom dock is covered. Everywhere else the
// log lives in the dock (DebugDock.jsx); this shows the same entries in the same view.
export default function DebugLogModal({ onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] backdrop-blur-sm" onClick={onClose}>
      <div
        role="dialog"
        aria-label="Debug log"
        className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-3xl mx-4 h-[70vh] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <DebugLogView onClose={onClose} />
      </div>
    </div>
  );
}
