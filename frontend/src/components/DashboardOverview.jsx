import ProgressRing from "./ProgressRing";

function average(values) {
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export default function DashboardOverview({ reviews }) {
  const scored = reviews.filter((review) => review.status !== "error");

  if (scored.length === 0) {
    return (
      <div className="card" style={{ padding: 20 }}>
        <p className="card-body">No scored reviews match these filters yet.</p>
      </div>
    );
  }

  const overallAverage = average(scored.map((review) => review.total_score_pct).filter((value) => value !== null && value !== undefined));

  const byCategoryName = new Map();
  for (const review of scored) {
    for (const category of review.category_scores || []) {
      if (category.percent_points === null || category.percent_points === undefined) continue;
      if (!byCategoryName.has(category.name)) byCategoryName.set(category.name, []);
      byCategoryName.get(category.name).push(category.percent_points);
    }
  }
  const categoryAverages = [...byCategoryName.entries()].map(([name, values]) => ({ name, average: average(values) }));

  return (
    <div className="card" style={{ padding: 20 }}>
      <div className="card-kicker-muted" style={{ marginBottom: "var(--space-3)" }}>Overview</div>
      <div style={{ display: "flex", gap: "var(--space-5)", flexWrap: "wrap", alignItems: "flex-start" }}>
        <div style={{ display: "grid", justifyItems: "center" }}>
          <ProgressRing value={overallAverage} label="Final Score" size={160} strokeWidth={14} />
          <p className="card-body" style={{ margin: "6px 0 0" }}>
            Based on {scored.length} review{scored.length === 1 ? "" : "s"}
          </p>
        </div>
        <div style={{ display: "flex", gap: "var(--space-4)", flexWrap: "wrap", alignItems: "flex-start" }}>
          {categoryAverages.map(({ name, average: categoryAverage }) => (
            <ProgressRing key={name} value={categoryAverage} label={name} size={100} strokeWidth={8} />
          ))}
        </div>
      </div>
    </div>
  );
}
