import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppNav from "../components/AppNav";
import { getMyReviews } from "../services/api";

const STATUS_LABELS = { pending_approval: "Pending approval", approved: "Approved", error: "Error" };

export default function MyReviewsPage() {
  const [reviews, setReviews] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("pending");

  useEffect(() => {
    let cancelled = false;
    getMyReviews()
      .then((result) => { if (!cancelled) setReviews(result); })
      .catch(() => { if (!cancelled) setError("Failed to load your reviews."); });
    return () => { cancelled = true; };
  }, []);

  const visible = (reviews || []).filter((review) => filter === "all" || review.status !== "approved");

  return (
    <div className="page">
      <AppNav />
      <main className="page-main">
        <header className="page-header">
          <div>
            <h1 className="page-title">My reviews</h1>
            <p className="page-subtitle">Reviews assigned to you for finalization.</p>
          </div>
          <div className="segmented" role="group" aria-label="Filter">
            <button type="button" className={`btn ${filter === "pending" ? "btn-primary" : ""}`} onClick={() => setFilter("pending")}>Pending</button>
            <button type="button" className={`btn ${filter === "all" ? "btn-primary" : ""}`} onClick={() => setFilter("all")}>All</button>
          </div>
        </header>

        {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}

        {reviews !== null && visible.length === 0 && (
          <div className="card" style={{ padding: 20 }}><p className="card-body">No reviews assigned to you.</p></div>
        )}

        {visible.length > 0 && (
          <div className="card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="table table--padded">
              <thead>
                <tr><th>Project</th><th>Platform</th><th>Date</th><th>AI score</th><th>Status</th><th aria-label="Actions" /></tr>
              </thead>
              <tbody>
                {visible.map((review) => (
                  <tr key={review.id}>
                    <td>{review.project_name}</td>
                    <td>{review.platform}</td>
                    <td>{new Date(review.created_at).toLocaleDateString()}</td>
                    <td>{review.total_score_pct ?? "—"}{review.total_score_pct != null && "%"}</td>
                    <td><span className="tag tag-outline">{STATUS_LABELS[review.status] || review.status}</span></td>
                    <td style={{ textAlign: "right" }}><Link className="btn btn-ghost" to={`/reports/${review.id}`}>Open</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
