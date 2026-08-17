import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bar, BarChart, Legend, Tooltip, XAxis, YAxis } from "recharts";
import { getProjectReviews } from "../services/api";
import { PLATFORMS } from "../platforms";

const CHART_WIDTH = 780;
const CHART_HEIGHT = 220;
const CHART_MARGIN = { top: 8, right: 16, bottom: 8, left: 8 };
const MAX_REVIEWS_PER_CHART = 5;

const BAR_COLORS = ["#1B3A6B", "#E4402C", "#2E9E6B", "#8891A0", "#C9A227", "#7B5EA7"];

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

  // Errored reviews have no scores to chart, and older reviews from before
  // this endpoint returned category_scores default it to []  -- both are
  // simply excluded from the per-clause charts (they still show in the
  // table below, unchanged).
  const chartableReviews = reviews.filter((review) => review.status !== "error" && (review.category_scores || []).length > 0);

  const allCategoryNames = [...new Set(chartableReviews.flatMap((review) => review.category_scores.map((category) => category.name)))];
  const colorByCategory = new Map(allCategoryNames.map((name, index) => [name, BAR_COLORS[index % BAR_COLORS.length]]));

  const knownPlatformOrder = PLATFORMS.map((platform) => platform.label);
  const presentPlatforms = [...new Set(chartableReviews.map((review) => review.platform))];
  const chartablePlatforms = [
    ...knownPlatformOrder.filter((label) => presentPlatforms.includes(label)),
    ...presentPlatforms.filter((label) => !knownPlatformOrder.includes(label)),
  ];

  return (
    <div style={{ display: "grid", gap: "var(--space-4)" }}>
      {chartablePlatforms.map((platform) => {
        const platformReviews = chartableReviews
          .filter((review) => review.platform === platform)
          .slice(0, MAX_REVIEWS_PER_CHART)
          .reverse();
        const categoryNames = [...new Set(platformReviews.flatMap((review) => review.category_scores.map((category) => category.name)))];
        const chartData = platformReviews.map((review) => {
          const point = { date: formatDate(review.created_at) };
          for (const category of review.category_scores) {
            if (category.percent_points !== null && category.percent_points !== undefined) {
              point[category.name] = category.percent_points;
            }
          }
          return point;
        });

        return (
          <div key={platform} className="card" style={{ padding: 20 }}>
            <div className="card-kicker-muted" style={{ marginBottom: "var(--space-3)" }}>{platform} clause scores</div>
            <BarChart width={CHART_WIDTH} height={CHART_HEIGHT} data={chartData} margin={CHART_MARGIN}>
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {categoryNames.map((name) => (
                <Bar key={name} name={name} dataKey={name} fill={colorByCategory.get(name)} isAnimationActive={false} />
              ))}
            </BarChart>
          </div>
        );
      })}

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
