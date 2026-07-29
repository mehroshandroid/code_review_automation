import { Bar, BarChart, Cell, LabelList, Tooltip, XAxis, YAxis } from "recharts";
import CornerMarks from "./CornerMarks";

const ROW_HEIGHT = 40;
const CHART_WIDTH = 820;
const CHART_MARGIN = { top: 8, right: 56, bottom: 8, left: 8 };

function isPending(entry) {
  return entry.percent_points === null || entry.percent_points === undefined;
}

function ValueLabel({ x, y, width, height, index, data }) {
  const entry = data[index];
  const pending = isPending(entry);
  const label = pending ? "Pending…" : `${entry.percent_points}%`;
  const labelX = pending ? x + 8 : x + width + 8;
  return (
    <text x={labelX} y={y + height / 2} dy={4} fontSize={12} fill="var(--color-text)" opacity={pending ? 0.5 : 1}>
      {label}
    </text>
  );
}

function CategoryTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const entry = payload[0].payload;
  return (
    <div className="card blueprint" style={{ padding: "var(--space-2) var(--space-3)", background: "var(--color-bg)" }}>
      <div style={{ fontSize: 12, fontWeight: 600 }}>{entry.name}</div>
      <div style={{ fontSize: 12 }}>{isPending(entry) ? "Not yet scored" : `${entry.percent_points}%`}</div>
    </div>
  );
}

export default function CategoryScoresChart({ categoryScores }) {
  const data = categoryScores.map((entry) => ({ ...entry, value: entry.percent_points ?? 0 }));

  return (
    <div className="card blueprint" style={{ padding: "var(--space-4)" }}>
      <CornerMarks />
      <div className="card-kicker">Category scores</div>
      <BarChart
        width={CHART_WIDTH}
        height={data.length * ROW_HEIGHT + CHART_MARGIN.top + CHART_MARGIN.bottom}
        data={data}
        layout="vertical"
        margin={CHART_MARGIN}
      >
        <XAxis type="number" domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="name" width={260} tick={{ fontSize: 12 }} />
        <Tooltip
          content={<CategoryTooltip />}
          cursor={{ fill: "color-mix(in srgb, var(--color-text) 6%, transparent)" }}
        />
        <Bar dataKey="value" barSize={20} radius={[0, 4, 4, 0]} isAnimationActive={false} minPointSize={2}>
          {data.map((entry) => (
            <Cell
              key={entry.id}
              fill={isPending(entry) ? "color-mix(in srgb, var(--color-text) 10%, transparent)" : "var(--color-accent)"}
            />
          ))}
          <LabelList content={(props) => <ValueLabel {...props} data={data} />} />
        </Bar>
      </BarChart>
    </div>
  );
}
