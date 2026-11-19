import { Group, Panel, Separator, usePanelRef } from "react-resizable-panels";
import { useSessionState } from "../sessionStore";

const STORAGE_KEY = "avio.ai.panelWidth";
const DEFAULT_WIDTH = 480;
const MIN_WIDTH = 320;
const MAX_WIDTH = "70%";
const MAIN_MIN_WIDTH = 240;

// The library reports the divider's state in data-separator (its hit area is wider than the bar, so CSS
// :hover is not enough). The dark: copies are needed because dark:bg-gray-700 would otherwise win.
const SEPARATOR_STATES = [
  "data-[separator=hover]:bg-blue-500 data-[separator=active]:bg-blue-500 data-[separator=focus]:bg-blue-500",
  "dark:data-[separator=hover]:bg-blue-500 dark:data-[separator=active]:bg-blue-500 dark:data-[separator=focus]:bg-blue-500",
].join(" ");

function storedWidth() {
  try {
    const n = parseInt(localStorage.getItem(STORAGE_KEY), 10);
    return Number.isFinite(n) ? n : DEFAULT_WIDTH;
  } catch { return DEFAULT_WIDTH; }
}

// The Apex Runner and SOQL Runner layout: the page (children) on the left and, while `open`, the AI
// panel (`ai`) on the right of a draggable divider. Both runners use one width, which is kept in
// pixels when the window is resized and remembered between launches. Double-click the divider to reset it.
export default function AiSplit({ open, ai, children }) {
  const [width, setWidth] = useSessionState("ai.panelWidth", storedWidth);
  const aiRef = usePanelRef();

  function remember(px) {
    const w = Math.round(px);
    setWidth(w);
    try { localStorage.setItem(STORAGE_KEY, String(w)); } catch { /* storage unavailable */ }
  }

  // Only a width the user chose is remembered, not one forced by a small window.
  function onLayoutChanged(_layout, meta) {
    if (meta?.isUserInteraction && aiRef.current) remember(aiRef.current.getSize().inPixels);
  }

  function reset() {
    aiRef.current?.resize(DEFAULT_WIDTH);
    remember(DEFAULT_WIDTH);
  }

  return (
    <Group orientation="horizontal" className="flex-1 min-w-0 h-full" onLayoutChanged={onLayoutChanged}>
      <Panel id="main" minSize={MAIN_MIN_WIDTH} className="h-full flex flex-col overflow-hidden">
        {children}
      </Panel>
      {open && (
        <>
          <Separator
            disableDoubleClick
            onDoubleClick={reset}
            title="Drag to resize the AI panel. Double-click to reset."
            className={`w-1.5 shrink-0 focus:outline-none transition-colors bg-gray-300 dark:bg-gray-700 ${SEPARATOR_STATES}`}
          />
          <Panel
            id="ai"
            panelRef={aiRef}
            defaultSize={width}
            minSize={MIN_WIDTH}
            maxSize={MAX_WIDTH}
            groupResizeBehavior="preserve-pixel-size"
            className="h-full flex flex-col overflow-hidden"
          >
            {ai}
          </Panel>
        </>
      )}
    </Group>
  );
}
