import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";

// react-rnd is only loaded the first time a floating panel opens.
const Rnd = lazy(() => import("react-rnd").then((m) => ({ default: m.Rnd })));

// Put this class on the element the panel is dragged by (usually its header).
export const DRAG_HANDLE = "avio-drag-handle";

const MARGIN = 16;
// The card itself is not clipped (overflow stays visible) so the resize handles, which sit
// half outside its edges and rounded corners, can still be grabbed. The content is clipped instead.
// Clicks on these never start a drag, even inside the header.
const NO_DRAG = "button, a, input, textarea, select, [data-no-drag]";

function initialBox(width, height) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const w = Math.min(width, vw - MARGIN * 2);
  const h = height === "auto" ? "auto" : Math.min(height, vh - MARGIN * 2);
  const y = h === "auto" ? Math.round(vh * 0.15) : Math.round((vh - h) / 2);
  return { x: Math.round((vw - w) / 2), y: Math.max(MARGIN, y), width: w, height: h };
}

function ResizeGrip() {
  return <div className="absolute top-0.5 left-0.5 w-2 h-2 border-r-2 border-b-2 border-slate-400/70 dark:border-gray-500 pointer-events-none" />;
}

/**
 * A modal that can be dragged by its DRAG_HANDLE element and, when `resizable`, resized from
 * any edge (with a grip in the bottom-right corner). Esc closes it.
 *
 * - width / height: starting size in px, clamped to the window. height "auto" fits the content
 *   (use it with resizable={false}).
 * - backdrop: Tailwind classes for the dimmed backdrop, or false for no backdrop. Without one the
 *   rest of the app stays usable while the panel is open.
 * - closeOnBackdrop: clicking the backdrop closes the panel.
 * - className: classes for the panel card (background, border, rounded corners).
 */
export default function FloatingPanel({
  onClose,
  children,
  label,
  width = 640,
  height = 560,
  minWidth = 320,
  minHeight = 200,
  resizable = true,
  backdrop = "bg-black/50 backdrop-blur-sm",
  closeOnBackdrop = true,
  className = "bg-white dark:bg-gray-900 rounded-2xl shadow-2xl",
}) {
  const [box] = useState(() => initialBox(width, height));
  const rndRef = useRef(null);

  // Keep the latest onClose without re-adding the key listener on every render.
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onCloseRef.current?.(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // When the panel first appears: move focus into it, and centre an auto-height panel once its
  // real height is known.
  const panelRef = useCallback((node) => {
    if (!node) return;
    node.focus({ preventScroll: true });
    if (box.height !== "auto") return;
    requestAnimationFrame(() => {
      const y = Math.max(MARGIN, Math.round((window.innerHeight - node.offsetHeight) / 2));
      rndRef.current?.updatePosition({ x: box.x, y });
    });
  }, [box]);

  // Close only when the click both starts and ends on the backdrop. A drag or resize that ends
  // with the mouse outside the panel also fires a click on the backdrop, and must not close it.
  const pressedBackdrop = useRef(false);
  const onBackdropClick = (e) => {
    if (pressedBackdrop.current && e.target === e.currentTarget) onClose?.();
    pressedBackdrop.current = false;
  };

  return (
    <div
      className={`fixed inset-0 z-50 ${backdrop || "pointer-events-none"}`}
      onMouseDown={(e) => { pressedBackdrop.current = e.target === e.currentTarget; }}
      onClick={backdrop && closeOnBackdrop ? onBackdropClick : undefined}
    >
      <Suspense fallback={null}>
        <Rnd
          ref={rndRef}
          default={box}
          minWidth={Math.min(minWidth, box.width)}
          minHeight={box.height === "auto" ? undefined : Math.min(minHeight, box.height)}
          bounds="parent"
          dragHandleClassName={DRAG_HANDLE}
          cancel={NO_DRAG}
          enableResizing={resizable}
          resizeHandleComponent={resizable ? { bottomRight: <ResizeGrip /> } : undefined}
          className={className}
          style={{ pointerEvents: "auto" }}
        >
          <div
            ref={panelRef}
            role="dialog"
            aria-modal={backdrop ? "true" : undefined}
            aria-label={label}
            tabIndex={-1}
            className="flex flex-col h-full min-h-0 overflow-hidden rounded-[inherit] outline-none"
          >
            {children}
          </div>
        </Rnd>
      </Suspense>
    </div>
  );
}
