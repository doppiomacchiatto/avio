---
name: react-resizable-panels
description: Resizable layouts in Avio's frontend with the react-resizable-panels library (Group, Panel, Separator, hooks, imperative API). Use when adding, changing or debugging a resizable or collapsible panel, a draggable divider, or a remembered panel size, and before writing any drag-to-resize code by hand.
---

# react-resizable-panels in Avio

Avio uses `react-resizable-panels` (version in `frontend/package.json`, 4.24.0 when this was written) for
resizable areas. Do not hand-write pointer-event resize code, and do not add another resize or split-pane
library: extend what is here.

## Read this before writing code

**The API names in this version are `Group`, `Panel` and `Separator`.** This version does not export
`PanelGroup` or `PanelResizeHandle`, and has no `direction` or `autoSaveId` props. If you remember those
names, they are from an older major version: check the types before using anything from memory.

Sources of truth, in this order:

1. `frontend/node_modules/react-resizable-panels/README.md`: the full API reference for the installed
   version (props of every component, then "Imperative APIs"). It is 82 KB: search it for the heading
   (`### Group`, `### Panel`, `### Separator`, `### PanelImperativeHandle`...), do not read it whole.
2. `frontend/node_modules/react-resizable-panels/dist/react-resizable-panels.d.ts`: exact signatures,
   including the hooks (`useDefaultLayout`, `usePanelRef`, `useGroupRef`...). Search it by name.
3. `references/examples.md` in this skill: short examples for the cases Avio is likely to need.
4. The guides. **The documentation site (react-resizable-panels.vercel.app) is a client-rendered app: fetching
   a page returns an empty shell.** Read the guide sources on GitHub instead, pinned to the commit of the
   installed version (`npm view react-resizable-panels@<version> gitHead` prints it;
   `4221da1b3e2ea23727cef552e4c5aea540774515` for 4.24.0):
   - guide text: `https://raw.githubusercontent.com/bvaughn/react-resizable-panels/<commit>/src/routes/<Name>Route.tsx`
   - example code: `https://raw.githubusercontent.com/bvaughn/react-resizable-panels/<commit>/src/routes/examples/<Name>.tsx`

   Useful guide names: `LayoutBasics`, `SizeConstraints`, `FixedSizePanels`, `CollapsiblePanels`,
   `ConditionalPanels`, `NestedGroups`, `GroupResizeBehavior`, `PanelResizeBehavior`, `Overflow`,
   `CustomStyles`, `PersistentLayouts`, `PersistentLayoutsConditionalPanels`, `UseDefaultLayout`,
   `UsePanelRef`, `UseGroupRef`.

The library also has `Grid` (two-dimensional) and `Workspace` (draggable tabsets) components. Avio does not
use them; read the README sections before considering them.

## How Avio uses it today

`frontend/src/components/AiSplit.jsx` is the only place. It lays out the Apex Runner and the SOQL Runner:
the page on the left (`children`) and, while `open`, the AI panel (`ai`) on the right of a `Separator`.

```jsx
<AiSplit open={aiOpen} ai={<AiPanel ... />}>
  ...the editor side...
</AiSplit>
```

What it does, and why:

- **One width for both runners, in pixels.** The AI `Panel` gets `defaultSize={width}` (a number, so pixels)
  and `groupResizeBehavior="preserve-pixel-size"`, so it keeps its width when the window is resized. The main
  panel keeps the default `preserve-relative-size` (a group needs at least one such panel).
- **Limits.** AI panel `minSize={320}`, `maxSize="70%"`; main panel `minSize={240}`.
- **Remembering.** The width lives in the session store (`ai.panelWidth`) and in `localStorage`
  (`avio.ai.panelWidth`). It is saved from the Group's `onLayoutChanged` only when
  `meta.isUserInteraction` is true, so a width forced by a small window is not remembered. The library's own
  `useDefaultLayout` is not used here: it saves percentages per group, and the two runners' groups have
  different widths (the SOQL Runner has the objects sidebar), so it would not give the same pixel width in both.
- **Reset.** The `Separator` has `disableDoubleClick` and its own `onDoubleClick`, which calls
  `panelRef.resize(480)`. The built-in double-click resets a panel to its `defaultSize`, which here is the
  remembered width, not 480.
- **Divider colours.** The `Separator` is styled from its `data-separator` state (see below), with `dark:`
  copies of each state class.

## Rules that are easy to get wrong

- **Sizes:** a number is pixels; a string without a unit is a percentage (`"50"` = 50%); other units need the
  unit (`"70%"`, `"20rem"`, `"50vh"`). This applies to `defaultSize`, `minSize`, `maxSize`, `collapsedSize`
  and `panelRef.resize()`.
- **Layouts are percentages.** `onLayoutChanged`, `groupRef.getLayout()` and `setLayout()` use a map of panel
  id to percentage. For pixels use `panelRef.getSize().inPixels` or the `Panel`'s `onResize`.
- **`Panel` and `Separator` must be direct DOM children of their `Group`.** A React fragment is fine; a
  wrapper `div` is not. A plain element between panels is allowed and stays a fixed size.
- **`Panel`'s `className` goes on an inner `div`,** not on the flex item the library sizes. Put layout classes
  for the content there (`h-full flex flex-col overflow-hidden`). Do not try to set the panel's width with CSS.
- **Conditionally rendered panels need an `id`,** and so do panels in any group whose layout is saved.
- **`onLayoutChange` fires on every pointer move; `onLayoutChanged` fires once on release.** Save from
  `onLayoutChanged`. Both also fire for non-user changes (mount, window resize, imperative calls): check
  `meta.isUserInteraction` before treating a size as the user's choice.
- **Styling a `Separator`:** it carries `data-separator="inactive" | "hover" | "active" | "focus" | "disabled"`.
  Style from that attribute, not from CSS `:hover`: the hit area is wider than the element
  (`resizeTargetMinimumSize` on the Group). In Tailwind: `data-[separator=hover]:bg-blue-500`. Avio uses
  `darkMode: "class"`, so a `dark:bg-*` base colour has the same specificity as the state class and comes
  later in the CSS: add `dark:data-[separator=hover]:...` copies or the state colour is lost in dark mode.
- **A `Group` sets its own inline flex styles.** The README says they cannot be overridden through `style`,
  except `overflow`. Size the group through its parent or with classes (`flex-1 min-w-0 h-full`, as `AiSplit`
  does). A vertical group needs a height: see the `GroupExplicitHeight` and `LayoutBasicsVertical` examples.
- **Tabs unmount in Avio.** `App.jsx` renders only the active tab, so a group's layout is lost on a tab switch
  unless it is stored (session store for the session, `localStorage` for the next launch), as `AiSplit` does.

## Adding another resizable area

1. Read the matching example in `references/examples.md`, then the README section for each prop you use.
2. If it is another AI-style side panel, reuse `AiSplit`. Otherwise build it with `Group`/`Panel`/`Separator`
   in its own component under `frontend/src/components/`, following the patterns in `AiSplit.jsx`.
3. For remembering a layout that is not shared between tabs, `useDefaultLayout({ id, storage: localStorage })`
   is enough (pass `panelIds` when panels are conditional).
4. Check both themes, a narrow window, the keyboard (arrow keys on the focused separator) and a tab switch.

## Testing

`e2e_panel.mjs` (Playwright, in `%TEMP%\opencode\aitest\pw\`, outside the repo and so possibly missing) drives
the real app: equal width in both runners, drag both ways, limits, reset, keyboard, divider colours in both
themes, window resize, close and reopen, reload. It needs the backend on port 7893 with an isolated `APPDATA`
and `vite --port 5199`; its header comment says how. Extend it when `AiSplit` changes.
