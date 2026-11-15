// Small dropdown for choosing which saved AI connection a panel uses (see connections.js).
// Hidden until there are two or more connections, so single-provider users never see it.
export default function ConnectionPicker({ connections, defaultId, selected, onChange, disabled = false, dark = true }) {
  if (!connections || connections.length < 2) return null;
  const def = connections.find((c) => c.id === defaultId);
  const cls = dark
    ? "bg-slate-800 text-slate-100 border-slate-600"
    : "bg-white dark:bg-gray-800 text-slate-700 dark:text-gray-100 border-slate-300 dark:border-gray-600";
  return (
    <select
      value={selected}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      title="Which AI connection this panel uses (add or edit connections in ⚙ Settings)"
      className={`max-w-[11rem] text-xs border rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-400 disabled:opacity-50 ${cls}`}
    >
      <option value="">Default{def ? ` (${def.label})` : ""}</option>
      {connections.map((c) => (
        <option key={c.id} value={c.id}>
          {c.label}{c.requires_key && !c.key_set ? " — no key" : ""}
        </option>
      ))}
    </select>
  );
}
