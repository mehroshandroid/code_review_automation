export function scoreTier(value) {
  if (value === null || value === undefined) return "unknown";
  if (value >= 80) return "green";
  if (value >= 60) return "orange";
  return "red";
}

const TIER_COLORS = { green: "#2E9E6B", orange: "#E4A72E", red: "#E4402C", unknown: "#C9D1DE" };

export default function ProgressRing({ value, label, size = 120, strokeWidth = 10 }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = value === null || value === undefined ? 0 : Math.max(0, Math.min(100, value));
  const offset = circumference * (1 - clamped / 100);
  const tier = scoreTier(value);

  return (
    <div style={{ display: "grid", justifyItems: "center", gap: 6 }} data-tier={tier}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--color-divider)" strokeWidth={strokeWidth} />
        <circle
          cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={TIER_COLORS[tier]} strokeWidth={strokeWidth}
          strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle" fontSize={size / 5} fontWeight="700" fill="var(--color-text)">
          {value === null || value === undefined ? "—" : `${value.toFixed(1)}%`}
        </text>
      </svg>
      <div className="card-body" style={{ textAlign: "center", fontWeight: 600, fontSize: 13 }}>{label}</div>
    </div>
  );
}
