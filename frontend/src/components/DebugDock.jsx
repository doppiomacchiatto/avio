import { useEffect } from "react";
import { Group, Panel, Separator, usePanelRef } from "react-resizable-panels";
import { setDebugOpen, useDebugLogCount, useDebugOpen } from "../debugLog";
import DebugLogView from "./DebugLogView";

const STORAGE_KEY = "avio.debug.height";
const HEADER_HEIGHT = 28;   // the h-7 header of DebugLogView, all that shows while collapsed
const DEFAULT_HEIGHT = 200;
const MIN_HEIGHT = 96;
const MAX_HEIGHT = "70%";
const MAIN_MIN_HEIGHT = 160;

const SEPARATOR_STATES = [
  "data-[separator=hover]:bg-blue-500 data-[separator=active]:bg-blue-500 data-[separator=focus]:bg-blue-500",
  "dark:data-[separator=hover]:bg-blue-500 dark:data-[separator=active]:bg-blue-500 dark:data-[separator=focus]:bg-blue-500",
].join(" ");

function storedHeight() {
  try {
    const n = parseInt(localStorage.getItem(STORAGE_KEY), 10);
    return Number.isFinite(n) && n >= MIN_HEIGHT ? n : DEFAULT_HEIGHT;
  } catch { return DEFAULT_HEIGHT; }
}

function rememberHeight(px) {
  try { localStorage.setItem(STORAGE_KEY, String(Math.round(px))); } catch { /* storage unavailable */ }
}

// The page (children) above, the debug log below a draggable divider. The log panel is always mounted
// and collapses to its header, so opening or closing it never remounts the page. The 🐞 button in the
// header, the log's own title bar and any logged error open it (debugLog.js holds the open state).
// Dragging it below its minimum collapses it. Its height is remembered between launches.
export default function DebugDock({ tab, children }) {
  const open = useDebugOpen();
  const panelRef = usePanelRef();

  // The store is the source of truth: follow it.
  useEffect(() => {
    const p = panelRef.current;
    if (!p) return;
    // resize, not expand: a panel that started collapsed has no earlier size to expand back to.
    if (open && p.isCollapsed()) p.resize(storedHeight());
    if (!open && !p.isCollapsed()) p.collapse();
  }, [open, panelRef]);

  // A drag can collapse or expand the panel too: tell the store.
  function onResize(size) {
    const collapsed = size.inPixels <= HEADER_HEIGHT + 1;
    if (collapsed === open) setDebugOpen(!collapsed);
  }

  function onLayoutChanged(_layout, meta) {
    const p = panelRef.current;
    if (meta?.isUserInteraction && p && !p.isCollapsed()) rememberHeight(p.getSize().inPixels);
  }

  return (
    <Group orientation="vertical" className="flex-1 min-h-0 w-full" onLayoutChanged={onLayoutChanged}>
      <Panel id="page" minSize={MAIN_MIN_HEIGHT} className="h-full flex flex-col overflow-hidden">
        {children}
      </Panel>
      <Separator
        title="Drag to resize the debug log"
        className={`h-1 shrink-0 focus:outline-none transition-colors bg-gray-300 dark:bg-gray-600 ${SEPARATOR_STATES}`}
      />
      <Panel
        id="debug"
        panelRef={panelRef}
        collapsible
        collapsedSize={HEADER_HEIGHT}
        defaultSize={open ? storedHeight() : HEADER_HEIGHT}
        minSize={MIN_HEIGHT}
        maxSize={MAX_HEIGHT}
        groupResizeBehavior="preserve-pixel-size"
        onResize={onResize}
        className="h-full overflow-hidden"
      >
        <DebugLogView tab={tab} open={open} onToggle={() => setDebugOpen((o) => !o)} />
      </Panel>
    </Group>
  );
}

/** The 🐞 header button: opens or closes the dock. Owns its own subscription so App does not re-render per entry. */
export function DebugDockButton({ className }) {
  const count = useDebugLogCount();
  const open = useDebugOpen();
  return (
    <button
      onClick={() => setDebugOpen((o) => !o)}
      aria-pressed={open}
      className={className}
      title={open ? "Hide the debug log" : "Show the debug log"}
    >
      🐞 Debug{count > 0 ? ` (${count})` : ""}
    </button>
  );
}
