import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Line, LineChart, Tooltip, XAxis, YAxis } from "recharts";
import { getProjectReviews } from "../services/api";

const CHART_WIDTH = 820;
const CHART_HEIGHT = 260;
const CHART_MARGIN = { top: 8, right: 16, bottom: 8, left: 8 };

const LINE_COLORS = ["#1B3A6B", "#E4402C", "#2E9E6B", "#8891A0"];

const STATUS_LABELS = {
  pending_approval: "Pending approval",
  approved: "Approved",
  completed: "Completed",
  error: "Error",
};

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString();
}

export default function ProjectReviewHistory({ projectId }) {
  const [reviews, setReviews] = useState(null); // null = still loading
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    setReviews(null);
    getProjectReviews(projectId)
      .then((result) => { if (!cancelled) setReviews(result); })
      .catch(() => { if (!cancelled) setReviews([]); });
    return () => { cancelled = true; };
  }, [projectId]);

  if (reviews === null) return null;

  if (reviews.length === 0) {
    return (
      <div className="card" style={{ padding: 20 }}>
        <p className="card-body">No reviews yet -- start one on the right to see history here.</p>
      </div>
    );
  }

  const platforms = [...new Set(reviews.map((r) => r.platform))];
  const chartData = [...reviews].reverse().map((r) => ({
    date: formatDate(r.created_at),
    [r.platform]: r.total_score_pct,
  }));

  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      <div className="card" style={{ padding: 20 }}>
        <div className="card-kicker-muted" style={{ marginBottom: "var(--space-3)" }}>Review history</div>
        <LineChart width={CHART_WIDTH} height={CHART_HEIGHT} data={chartData} margin={CHART_MARGIN}>
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
          <Tooltip />
          {platforms.map((platform, index) => (
            <Line
              key={platform}
              name={platform}
              dataKey={platform}
              stroke={LINE_COLORS[index % LINE_COLORS.length]}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </div>

      <div className="card" style={{ padding: 20 }}>
        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Platform</th>
              <th>Status</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
            {reviews.map((review) => (
              <tr
                key={review.id}
                onClick={() => navigate(`/reports/${review.id}`)}
                style={{ cursor: "pointer" }}
              >
                <td>{formatDate(review.created_at)}</td>
                <td>{review.platform}</td>
                <td>{STATUS_LABELS[review.status] || review.status}</td>
                <td>{review.total_score_pct !== null && review.total_score_pct !== undefined ? `${review.total_score_pct}%` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
