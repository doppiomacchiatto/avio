import { useRef } from "react";
import Draggable from "react-draggable";

// Put this class on the element the card is dragged by (its header).
export const GUIDE_HANDLE = "avio-guide-handle";

/**
 * A small card that floats over a tab (the "How to use" guides) and can be dragged anywhere
 * inside that tab by its GUIDE_HANDLE header. It keeps its normal CSS position (for example
 * absolute top-3 right-3) as the starting point. The tab's container must be position: relative.
 */
export default function DraggableGuide({ className, children }) {
  const nodeRef = useRef(null);
  return (
    <Draggable nodeRef={nodeRef} handle={`.${GUIDE_HANDLE}`} cancel="button" bounds="parent">
      <div ref={nodeRef} className={className}>{children}</div>
    </Draggable>
  );
}
