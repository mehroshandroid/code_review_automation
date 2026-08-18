import { useNavigate } from "react-router-dom";

const STATUS_LABELS = {
  pending_approval: "Pending approval",
  approved: "Approved",
  completed: "Completed",
  error: "Error",
};

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString();
}

export default function DashboardResultsTable({ reviews }) {
  const navigate = useNavigate();

  if (reviews.length === 0) {
    return (
      <div className="card" style={{ padding: 20 }}>
        <p className="card-body">No reviews match these filters.</p>
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: 20 }}>
      <table className="table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Project</th>
            <th>Platform</th>
            <th>Status</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {reviews.map((review) => (
            <tr key={review.id} onClick={() => navigate(`/reports/${review.id}`)} style={{ cursor: "pointer" }}>
              <td>{formatDate(review.created_at)}</td>
              <td>{review.project_name}</td>
              <td>{review.platform}</td>
              <td>{STATUS_LABELS[review.status] || review.status}</td>
              <td>{review.total_score_pct !== null && review.total_score_pct !== undefined ? `${review.total_score_pct}%` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
