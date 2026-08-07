function scoreLabel(score) {
  if (score === 1) return "Meets";
  if (score === 0) return "Fails";
  return "Not evaluated";
}

export default function ReportTable({ categoryScores }) {
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
                  <td>{scoreLabel(sub.score)}</td>
                  <td className="text-muted">{sub.remark}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
