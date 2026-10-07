import { useEffect, useRef, useState } from "react";

export default function MultiSelect({ ariaLabel, options, values, onChange, placeholder = "Select…" }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const containerRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selected = options.filter((option) => values.includes(option.value));
  const filtered = options.filter((option) => option.label.toLowerCase().includes(query.toLowerCase()));

  function toggle(value) {
    onChange(values.includes(value) ? values.filter((v) => v !== value) : [...values, value]);
  }

  return (
    <div ref={containerRef} style={{ position: "relative", display: "grid", gap: 8 }}>
      {selected.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {selected.map((option) => (
            <span key={option.value} className="tag tag-outline" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              {option.label}
              <button
                type="button" aria-label={`Remove ${option.label}`} onClick={() => toggle(option.value)}
                style={{ background: "none", border: "none", cursor: "pointer", padding: 0, lineHeight: 1, color: "inherit" }}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <button
        type="button" className="input" aria-label={ariaLabel} aria-expanded={open}
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer", width: "100%" }}
        onClick={() => { setOpen((current) => !current); setQuery(""); }}
      >
        <span style={{ color: "var(--color-text-muted)" }}>{selected.length ? `${selected.length} selected` : placeholder}</span>
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="card elev-md" style={{ position: "absolute", top: "100%", left: 0, right: 0, zIndex: 60, padding: 8, marginTop: 4, maxHeight: 280, display: "flex", flexDirection: "column" }}>
          <input
            type="text" className="input" aria-label={`Search ${ariaLabel}`} placeholder="Search…"
            value={query} autoFocus onChange={(event) => setQuery(event.target.value)}
          />
          <div style={{ overflowY: "auto", marginTop: 8 }}>
            {filtered.length === 0 && <p className="card-body" style={{ padding: "8px 4px" }}>No matches</p>}
            {filtered.map((option) => (
              <label key={option.value} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 4px", cursor: "pointer", fontSize: 14 }}>
                <input type="checkbox" checked={values.includes(option.value)} onChange={() => toggle(option.value)} />
                {option.label}
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
