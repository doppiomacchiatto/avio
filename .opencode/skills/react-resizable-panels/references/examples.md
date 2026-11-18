# react-resizable-panels: examples

Copied from the library's documentation sources (`src/routes/examples/` in
https://github.com/bvaughn/react-resizable-panels, commit `4221da1b3e2ea23727cef552e4c5aea540774515`,
version 4.24.0, MIT license, © Brian Vaughn). The code is unchanged apart from removing some import lines,
the files' type declarations and their lint comments. The notes above each example are Avio's.

All imports come from `"react-resizable-panels"`.

## Two panels with a divider

`orientation` defaults to `"horizontal"`. Without a `Separator` the panel edges are still draggable, but a
`Separator` is recommended because it makes the divider reachable from the keyboard.

```jsx
<Group>
  <Panel>left</Panel>
  <Separator />
  <Panel>right</Panel>
</Group>
```

## Vertical

A vertical group needs a height (here a minimum height class).

```jsx
<Group className="min-h-30" orientation="vertical">
  <Panel>top</Panel>
  <Panel>bottom</Panel>
</Group>
```

## Minimum and maximum size

Numbers are pixels.

```jsx
<Group>
  <Panel minSize={100} maxSize={200}>left</Panel>
  <Separator />
  <Panel>right</Panel>
</Group>
```

Strings with `%` are percentages of the group.

```jsx
<Group>
  <Panel minSize="10%">left</Panel>
  <Separator />
  <Panel minSize="10%">middle</Panel>
  <Separator />
  <Panel minSize="10%">right</Panel>
</Group>
```

## A panel that keeps its pixel width when the window is resized

This is what `AiSplit` uses for the AI panel. At least one panel in the group must keep the default
(`preserve-relative-size`).

```jsx
<Group>
  <Panel groupResizeBehavior="preserve-pixel-size">
    left
  </Panel>
  <Separator />
  <Panel>main</Panel>
</Group>
```

## A fixed-size element beside resizable panels

An element that is not a `Panel` keeps its own size.

```jsx
<Group>
  <Panel>left</Panel>
  <Separator />
  <Panel>right</Panel>
  <div className="w-45">Fixed sized element</div>
</Group>
```

## Collapsible panel

A collapsible panel collapses when it is dragged below its `minSize`. `collapsedSize` defaults to 0.

```jsx
<Group>
  <Panel collapsible minSize={100} />
  <Separator />
  <Panel />
</Group>
```

```jsx
<Group>
  <Panel collapsible collapsedSize={35} minSize={100} />
  <Separator />
  <Panel />
</Group>
```

## Panels that come and go

Render the panel and its separator together in a fragment, and give every panel an `id`.

```jsx
<Group>
  {hideLeftPanel || (
    <>
      <Panel id="left">left panel</Panel>
      <Separator />
    </>
  )}
  <Panel id="center">center panel</Panel>
  {hideRightPanel || (
    <>
      <Separator />
      <Panel id="right">right panel</Panel>
    </>
  )}
</Group>
```

## Nested groups

```jsx
<Group orientation="horizontal">
  <Panel>
    <Folders />
  </Panel>
  <Panel>
    <Group orientation="vertical">
      <Panel>
        <MessageList />
      </Panel>
      <Panel>
        <ReadingPane />
      </Panel>
    </Group>
  </Panel>
</Group>
```

## Remembering a layout between launches

`useDefaultLayout` saves the group's layout (percentages by panel id). The `id` must be unique per layout.

```jsx
import { useDefaultLayout } from "react-resizable-panels";

const { defaultLayout, onLayoutChanged } = useDefaultLayout({
  id: "unique-layout-id"
});

<Group defaultLayout={defaultLayout} onLayoutChanged={onLayoutChanged} {...rest} />
```

With conditional panels, tell it which panels are rendered at mount so it restores the matching layout.

```jsx
const { defaultLayout, onLayoutChanged } = useDefaultLayout({
  id: "unique-layout-id",
  // This set of ids must match the Panels rendered during mount,
  // or the default layout will not be restored
  panelIds: showLeftPanel ? ["left", "right"] : ["right"],
  storage: localStorage
});

<Group defaultLayout={defaultLayout} onLayoutChanged={onLayoutChanged}>
  {showLeftPanel && (
    <>
      <Panel id="left">left</Panel>
      <Separator />
    </>
  )}
  <Panel id="right">right</Panel>
</Group>
```

## Imperative API: one panel

`panelRef` gives `collapse()`, `expand()`, `getSize()` (`{ asPercentage, inPixels }`), `isCollapsed()` and
`resize(size)`. `onResize` receives the same size object.

```jsx
import { useState } from "react";
import { Group, Panel, Separator, usePanelRef } from "react-resizable-panels";

function ExampleComponent() {
  const ref = usePanelRef();
  const [isCollapsed, setIsCollapsed] = useState(false);

  const toggle = () => {
    const panel = ref.current;
    if (panel?.isCollapsed()) {
      panel.expand();
    } else {
      panel?.collapse();
    }
  };

  return (
    <Group>
      <Panel
        collapsible
        minSize="10%"
        onResize={(size) => setIsCollapsed(size.inPixels === 0)}
        panelRef={ref}
      >
        left
      </Panel>
      <button onClick={toggle}>{isCollapsed ? "expand" : "collapse"}</button>
      <Separator />
      <Panel>right</Panel>
    </Group>
  );
}
```

(The button label in the original is an arrow character; it is written as text here.)

## Imperative API: the whole group

`groupRef` gives `getLayout()` and `setLayout(layout)`, both as percentages by panel id.

```jsx
import { Group, Panel, Separator, useGroupRef } from "react-resizable-panels";

function ExampleComponent() {
  const ref = useGroupRef();

  const maximizeLeftPanel = () => {
    ref.current?.setLayout({ left: 75, right: 25 });
  };

  return (
    <Group groupRef={ref}>
      <Panel id="left">
        <button onClick={maximizeLeftPanel}>maximize</button>
      </Panel>
      <Separator />
      <Panel id="right">...</Panel>
    </Group>
  );
}
```

## Styling the divider

The separator reports its state in `data-separator`:

```html
<div data-separator="disabled" />
<div data-separator="inactive" />
<div data-separator="hover" />
<div data-separator="active" />
<div data-separator="focus" />
```

```jsx
<Separator
  className="
    bg-slate-600
    [&[data-separator='hover']]:bg-slate-500
    [&[data-separator='active']]:bg-slate-400
    [&[data-separator='focus']]:bg-sky-400
  "
/>
```

## A divider that cannot be dragged

```jsx
<Group>
  <Panel>left</Panel>
  <Separator disabled />
  <Panel>right</Panel>
</Group>
```
