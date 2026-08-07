import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import TopNav from "../components/TopNav";
import ReportTable from "../components/ReportTable";
import { DownloadIcon } from "../icons";
import { getReview, getDownloadUrl } from "../services/api";

const STATUS_LABELS = {
  pending_approval: "Pending approval",
  approved: "Approved",
  completed: "Completed",
  error: "Error",
};

export default function ReviewReportPage() {
  const { reviewId } = useParams();
  const [review, setReview] = useState(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setReview(null);
    setNotFound(false);
    getReview(reviewId)
      .then((result) => { if (!cancelled) setReview(result); })
      .catch(() => { if (!cancelled) setNotFound(true); });
    return () => { cancelled = true; };
  }, [reviewId]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <TopNav />

      <main style={{ maxWidth: 920, margin: "0 auto", padding: "64px 24px 96px" }}>
        {notFound && (
          <div className="card elev-md" style={{ padding: 32 }}>
            <div className="card-title" style={{ fontSize: 20 }}>Review not found</div>
            <p className="card-body">This review doesn't exist or is no longer available.</p>
          </div>
        )}

        {review && (
          <>
            <header style={{ marginBottom: "var(--space-6)" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap", marginBottom: 10 }}>
                <h1 style={{ fontFamily: "var(--font-heading)", fontWeight: "var(--font-heading-weight)", fontSize: 40, lineHeight: 1.1, letterSpacing: "-0.02em", margin: 0 }}>
                  {review.project_name}
                </h1>
                <span className="tag tag-outline">{review.platform}</span>
                <span className="tag tag-outline">{STATUS_LABELS[review.status] || review.status}</span>
              </div>
              <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
                {review.total_score_pct !== null && review.total_score_pct !== undefined && (
                  <span className="tag tag-accent">Total {review.total_score_pct}%</span>
                )}
                <span className="tag tag-outline">{review.warnings.length + review.lint_issues.length} warnings</span>
                <span className="tag tag-outline">{review.secrets_found.length} secrets</span>
              </div>
              {review.has_workbook && (
                <a
                  href={getDownloadUrl(`/api/reviews/${review.id}/download`)}
                  download
                  className="btn btn-primary"
                  style={{ marginTop: "var(--space-4)" }}
                >
                  Download workbook
                  <DownloadIcon />
                </a>
              )}
              {review.error && (
                <p className="card-body" style={{ color: "var(--color-brand-coral)", marginTop: "var(--space-3)" }}>{review.error}</p>
              )}
            </header>

            <ReportTable categoryScores={review.category_scores} />
          </>
        )}
      </main>
    </div>
  );
}
