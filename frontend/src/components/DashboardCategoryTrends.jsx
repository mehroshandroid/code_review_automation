import { Bar, BarChart, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PLATFORMS } from "../platforms";

const CHART_HEIGHT = 220;
const CHART_MIN_WIDTH = 380;
const CHART_MARGIN = { top: 8, right: 16, bottom: 8, left: 8 };
const MAX_REVIEWS_PER_CHART = 5;

const BAR_COLORS = ["#1B3A6B", "#E4402C", "#2E9E6B", "#8891A0", "#C9A227", "#7B5EA7"];

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString();
}

export default function DashboardCategoryTrends({ reviews }) {
  const chartableReviews = reviews.filter((review) => review.status !== "error" && (review.category_scores || []).length > 0);

  if (chartableReviews.length === 0) return null;

  const allCategoryNames = [...new Set(chartableReviews.flatMap((review) => review.category_scores.map((category) => category.name)))];
  const colorByCategory = new Map(allCategoryNames.map((name, index) => [name, BAR_COLORS[index % BAR_COLORS.length]]));

  const knownPlatformOrder = PLATFORMS.map((platform) => platform.label);
  const presentPlatforms = [...new Set(chartableReviews.map((review) => review.platform))];
  const chartablePlatforms = [
    ...knownPlatformOrder.filter((label) => presentPlatforms.includes(label)),
    ...presentPlatforms.filter((label) => !knownPlatformOrder.includes(label)),
  ];

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-4)" }}>
      {chartablePlatforms.map((platform) => {
        const platformReviews = chartableReviews
          .filter((review) => review.platform === platform)
          .slice(0, MAX_REVIEWS_PER_CHART)
          .reverse();
        const categoryNames = [...new Set(platformReviews.flatMap((review) => review.category_scores.map((category) => category.name)))];
        const chartData = platformReviews.map((review) => {
          const point = { date: `${formatDate(review.created_at)} · ${review.project_name}` };
          for (const category of review.category_scores) {
            if (category.percent_points !== null && category.percent_points !== undefined) {
              point[category.name] = category.percent_points;
            }
          }
          return point;
        });

        return (
          <div key={platform} className="card" style={{ padding: 20, flex: `1 1 ${CHART_MIN_WIDTH}px`, minWidth: 0 }}>
            <div className="card-kicker-muted" style={{ marginBottom: "var(--space-3)" }}>{platform} clause scores</div>
            <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
              <BarChart data={chartData} margin={CHART_MARGIN}>
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {categoryNames.map((name) => (
                  <Bar key={name} name={name} dataKey={name} fill={colorByCategory.get(name)} isAnimationActive={false} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        );
      })}
    </div>
  );
}
