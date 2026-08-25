import { useEffect, useRef, useState } from "react";

export default function SearchableSelect({ ariaLabel, options, value, onChange, placeholder = "Select…", onAddNew, addNewLabel }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const containerRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selected = options.find((option) => option.value === value);
  const filtered = options.filter((option) => option.label.toLowerCase().includes(query.toLowerCase()));

  function handleSelect(option) {
    onChange(option.value);
    setOpen(false);
    setQuery("");
  }

  function handleToggle() {
    setOpen((current) => !current);
    setQuery("");
  }

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      <button
        type="button"
        className="input"
        aria-label={ariaLabel}
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer", width: "100%" }}
        onClick={handleToggle}
      >
        <span>{selected ? selected.label : placeholder}</span>
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="card elev-md" style={{ position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 50, padding: 8, maxHeight: 280, display: "flex", flexDirection: "column" }}>
          <input
            type="text"
            className="input"
            aria-label={`Search ${ariaLabel}`}
            placeholder="Search…"
            value={query}
            autoFocus
            onChange={(event) => setQuery(event.target.value)}
          />
          <div style={{ overflowY: "auto", marginTop: 8 }}>
            {filtered.length === 0 && <p className="card-body" style={{ padding: "8px 4px" }}>No matches</p>}
            {filtered.map((option) => (
              <button
                key={option.value ?? "__all__"}
                type="button"
                className={`btn btn-block ${option.value === value ? "btn-primary" : ""}`}
                style={{ justifyContent: "flex-start", marginTop: 4 }}
                onClick={() => handleSelect(option)}
              >
                {option.label}
              </button>
            ))}
            {onAddNew && (
              <button
                type="button"
                className="btn btn-block btn-ghost"
                style={{ justifyContent: "flex-start", marginTop: 4 }}
                onClick={() => { setOpen(false); setQuery(""); onAddNew(); }}
              >
                {addNewLabel || "+ Add new"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
