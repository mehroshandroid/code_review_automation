function scoreLabel(score) {
  if (score === 1) return "Meets";
  if (score === 0) return "Fails";
  return "Not evaluated";
}

function scoreToSelectValue(score) {
  if (score === 1) return "1";
  if (score === 0) return "0";
  return "";
}

function selectValueToScore(value) {
  if (value === "1") return 1;
  if (value === "0") return 0;
  return null;
}

export default function ReportTable({ categoryScores, editable = false, onChangeScore, onChangeRemark }) {
  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      {categoryScores.map((category) => (
        <div key={category.id} className="card" style={{ padding: 20 }}>
          <div className="card-title" style={{ fontSize: 16, display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
            {category.name}
            {category.percent_points !== null && category.percent_points !== undefined && (
              <span className="tag tag-accent">{category.percent_points}%</span>
            )}
          </div>
          <table className="table" style={{ marginTop: "var(--space-3)" }}>
            <thead>
              <tr>
                <th>Clause</th>
                <th>Description</th>
                <th>Score</th>
                <th>Remark</th>
              </tr>
            </thead>
            <tbody>
              {category.sub_criteria.map((sub) => (
                <tr key={sub.id}>
                  <td>{sub.id}</td>
                  <td>{sub.description}</td>
                  <td>
                    {editable ? (
                      <select
                        aria-label={`Score for ${sub.id}`}
                        className="input"
                        value={scoreToSelectValue(sub.score)}
                        onChange={(event) => onChangeScore(category.id, sub.id, selectValueToScore(event.target.value))}
                      >
                        <option value="1">Meets</option>
                        <option value="0">Fails</option>
                        <option value="">Not evaluated</option>
                      </select>
                    ) : (
                      scoreLabel(sub.score)
                    )}
                  </td>
                  <td className="text-muted">
                    {editable ? (
                      <textarea
                        aria-label={`Remark for ${sub.id}`}
                        className="input"
                        rows={2}
                        value={sub.remark || ""}
                        onChange={(event) => onChangeRemark(category.id, sub.id, event.target.value)}
                      />
                    ) : (
                      sub.remark
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
