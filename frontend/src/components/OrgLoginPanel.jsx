import { useEffect, useRef, useState } from "react";
import { api, apiQuiet } from "../api/client";
import { debugLog } from "../debugLog";

const LABELS = {
  production: "Production",
  test: "Sandbox / test",
};

// First-run login: shown when the sf CLI has no authenticated org. The backend runs
// `sf org login web --instance-url <url> --alias <alias>`; this panel only picks the org type
// and shows progress. `onLoggedIn(alias)` is called once the CLI reports success.
export default function OrgLoginPanel({ onLoggedIn, onRefresh, onBack }) {
  const [options, setOptions] = useState([]);
  const [kind, setKind]       = useState("production");
  const [job, setJob]         = useState({ state: "idle" });
  const [command, setCommand] = useState("");
  const [error, setError]     = useState("");
  const [showCmd, setShowCmd] = useState(false);
  const alive = useRef(true);
  const done  = useRef(false);

  useEffect(() => {
    alive.current = true;
    api("/api/org-login/options").then((d) => alive.current && setOptions(d.options || [])).catch(() => {});
    apiQuiet("/api/org-login").then((j) => {   // a login may already be waiting (panel was re-mounted)
      if (alive.current && j?.state === "running") { setJob(j); setKind(j.type || "production"); }
    }).catch(() => {});
    return () => { alive.current = false; };
  }, []);

  // Poll while a login is waiting in the browser.
  useEffect(() => {
    if (job.state !== "running") return;
    const id = setInterval(async () => {
      try {
        const j = await apiQuiet("/api/org-login");
        if (!alive.current) return;
        setJob(j);
        if (j.state === "success" && !done.current) {
          done.current = true;
          debugLog(`[OrgLogin] logged in${j.username ? ` as ${j.username}` : ""} (alias ${j.alias})`, "done");
          onLoggedIn?.(j.alias);
        } else if (j.state === "error") {
          debugLog(`[OrgLogin] failed: ${j.message}`, "error");
        }
      } catch { /* backend busy: try again on the next tick */ }
    }, 1500);
    return () => clearInterval(id);
  }, [job.state, onLoggedIn]);

  const chosen = options.find((o) => o.type === kind);
  const running = job.state === "running";

  async function start() {
    setError(""); done.current = false;
    try {
      const j = await api("/api/org-login", { method: "POST", body: JSON.stringify({ type: kind }) });
      setCommand(j.command || "");
      setJob(j);
    } catch (e) {
      const m = String(e?.message || e);
      setError(m.includes("Could not find") ? "The Salesforce CLI (sf) was not found. Install it, then try again." : m.split("\n")[0]);
    }
  }

  async function cancel() {
    try { setJob(await api("/api/org-login/cancel", { method: "POST" })); } catch { /* ignore */ }
  }

  return (
    <div className="flex flex-col gap-3 text-sm">
      <div className="text-center text-gray-500 dark:text-gray-400">
        <p className="font-medium text-gray-700 dark:text-gray-200">
          {onBack ? "Log in to another org" : "No Salesforce org is logged in yet."}
        </p>
        <p className="text-xs mt-0.5">Log in with your browser. Avio never sees your password.</p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {(options.length ? options : [{ type: "production" }, { type: "test" }]).map((o) => (
          <button
            key={o.type}
            type="button"
            disabled={running}
            onClick={() => setKind(o.type)}
            className={`px-3 py-2.5 rounded-xl border-2 text-left transition-colors disabled:opacity-60 ${
              kind === o.type
                ? "border-blue-600 bg-blue-50 dark:bg-blue-900/30"
                : "border-gray-200 dark:border-gray-600 hover:border-blue-300 dark:hover:border-blue-500"
            }`}
          >
            <div className="font-medium text-gray-900 dark:text-white">{LABELS[o.type]}</div>
            <div className="text-[11px] text-gray-400">alias {o.alias || (o.type === "production" ? "avio-prod" : "avio-dev")}</div>
          </button>
        ))}
      </div>

      {chosen && (
        <p className="text-xs text-gray-500 dark:text-gray-400 break-all">
          Login URL: <span className="font-mono">{chosen.url}</span>
          {chosen.custom && <span className="ml-1 text-amber-600 dark:text-amber-400">(from your config)</span>}
        </p>
      )}

      {running ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800">
            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin shrink-0" />
            <p className="text-xs text-blue-700 dark:text-blue-300">
              Finish logging in in the browser window that opened. This page continues by itself.
            </p>
          </div>
          <button onClick={cancel} className="w-full py-2 text-xs rounded-xl border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
            Cancel login
          </button>
        </div>
      ) : (
        <button
          onClick={start}
          className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-semibold transition-colors"
        >
          {job.state === "error" || job.state === "cancelled" ? "Try again" : "Log in with browser"}
        </button>
      )}

      {job.state === "success" && (
        <p className="text-xs text-green-700 dark:text-green-400 text-center">✓ Logged in{job.username ? ` as ${job.username}` : ""}. Loading your org…</p>
      )}
      {job.state === "error" && (
        <p className="text-xs text-red-600 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2 whitespace-pre-wrap">{job.message}</p>
      )}
      {job.state === "cancelled" && <p className="text-xs text-gray-500 text-center">Login cancelled.</p>}
      {error && <p className="text-xs text-red-600 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2 whitespace-pre-wrap">{error}</p>}

      {onBack && !running && (
        <button type="button" onClick={onBack} className="text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-200 underline self-start">
          ← Back to my orgs
        </button>
      )}

      <div className="text-xs text-gray-500 dark:text-gray-400">
        <button type="button" onClick={() => setShowCmd((v) => !v)} className="underline hover:text-gray-700 dark:hover:text-gray-200">
          {showCmd ? "Hide" : "Prefer a terminal, or the browser can't open?"}
        </button>
        {showCmd && (
          <div className="mt-2 flex flex-col gap-2">
            <code className="block bg-gray-900 text-green-400 px-3 py-2 rounded font-mono break-all">
              {command || (chosen ? `sf org login web --instance-url ${chosen.url} --alias ${chosen.alias}` : "sf org login web")}
            </code>
            <p>Run it, then check again.</p>
            <button type="button" onClick={onRefresh} className="self-start px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700">
              ↻ Check for orgs
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
