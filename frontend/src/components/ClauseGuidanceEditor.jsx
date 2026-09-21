import { useState } from "react";

export default function ClauseGuidanceEditor({ categories, onChange }) {
  const [values, setValues] = useState({});

  function handleChange(subId, newText) {
    const next = { ...values, [subId]: newText };
    setValues(next);

    const overrides = {};
    for (const category of categories) {
      for (const sub of category.sub_criteria) {
        if (sub.id in next) {
          const original = sub.checklist_text || "";
          if (next[sub.id] !== original) overrides[sub.id] = next[sub.id];
        }
      }
    }
    onChange(overrides);
  }

  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      {categories.map((category) => (
        <div key={category.id}>
          <div className="card-kicker-muted" style={{ marginBottom: "var(--space-2)" }}>{category.name}</div>
          <div style={{ display: "grid", gap: "var(--space-3)" }}>
            {category.sub_criteria.map((sub) => {
              const original = sub.checklist_text || "";
              const currentValue = sub.id in values ? values[sub.id] : original;
              return (
                <div className="field" key={sub.id}>
                  <label htmlFor={`clauseGuidance-${sub.id}`}>{sub.id} — {sub.description}</label>
                  <textarea
                    id={`clauseGuidance-${sub.id}`}
                    className="input"
                    rows={2}
                    value={currentValue}
                    onChange={(event) => handleChange(sub.id, event.target.value)}
                  />
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
