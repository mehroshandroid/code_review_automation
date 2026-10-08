import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AppNav from "../components/AppNav";
import ReportTable from "../components/ReportTable";
import ReviewMetaBar from "../components/ReviewMetaBar";
import { DownloadIcon } from "../icons";
import { getReview, getDownloadUrl, updateReview, getReviewers, setReviewReviewer, deleteReview } from "../services/api";
import { useAuth } from "../context/AuthContext";
import { hasPermission } from "../permissions";

const STATUS_LABELS = {
  pending_approval: "Pending approval",
  approved: "Approved",
  error: "Error",
};

const SELECTABLE_STATUSES = ["pending_approval", "approved"];

function cloneCategoryScores(categoryScores) {
  return categoryScores.map((category) => ({
    ...category,
    sub_criteria: category.sub_criteria.map((sub) => ({ ...sub })),
  }));
}

export default function ReviewReportPage() {
  const { reviewId } = useParams();
  const [review, setReview] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftCategoryScores, setDraftCategoryScores] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [statusSaving, setStatusSaving] = useState(false);
  const [statusError, setStatusError] = useState("");
  const [reviewers, setReviewers] = useState([]);
  const [reviewerSaving, setReviewerSaving] = useState(false);
  const [reviewerError, setReviewerError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const navigate = useNavigate();
  const { user } = useAuth();
  const canAssignReviewer = hasPermission(user, "reviews.assign_reviewer");

  useEffect(() => {
    let cancelled = false;
    setReview(null);
    setNotFound(false);
    setEditing(false);
    getReview(reviewId)
      .then((result) => { if (!cancelled) setReview(result); })
      .catch(() => { if (!cancelled) setNotFound(true); });
    return () => { cancelled = true; };
  }, [reviewId]);

  useEffect(() => {
    if (!canAssignReviewer) return undefined;
    let cancelled = false;
    getReviewers()
      .then((result) => { if (!cancelled) setReviewers(result); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [canAssignReviewer]);

  async function handleChangeReviewer(event) {
    const reviewerId = event.target.value || null;
    setReviewerSaving(true);
    setReviewerError("");
    try {
      const updated = await setReviewReviewer(reviewId, reviewerId);
      setReview(updated);
    } catch (err) {
      setReviewerError("Failed to update reviewer");
    } finally {
      setReviewerSaving(false);
    }
  }

  function handleStartEdit() {
    setDraftCategoryScores(cloneCategoryScores(review.category_scores));
    setSaveError("");
    setEditing(true);
  }

  function handleCancelEdit() {
    setEditing(false);
    setDraftCategoryScores(null);
    setSaveError("");
  }

  function handleChangeScore(categoryId, subId, score) {
    setDraftCategoryScores((current) =>
      current.map((category) => (
        category.id !== categoryId
          ? category
          : { ...category, sub_criteria: category.sub_criteria.map((sub) => (sub.id !== subId ? sub : { ...sub, score })) }
      ))
    );
  }

  function handleChangeRemark(categoryId, subId, remark) {
    setDraftCategoryScores((current) =>
      current.map((category) => (
        category.id !== categoryId
          ? category
          : { ...category, sub_criteria: category.sub_criteria.map((sub) => (sub.id !== subId ? sub : { ...sub, remark })) }
      ))
    );
  }

  async function handleSaveEdit() {
    setSaving(true);
    setSaveError("");
    try {
      const updated = await updateReview(reviewId, { categoryScores: draftCategoryScores });
      setReview(updated);
      setEditing(false);
      setDraftCategoryScores(null);
    } catch (err) {
      setSaveError("Failed to save changes");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteReview(reviewId);
      navigate("/");
    } catch (err) {
      setDeleteError("Failed to delete review");
      setDeleting(false);
    }
  }

  async function handleChangeStatus(status) {
    setStatusSaving(true);
    setStatusError("");
    try {
      const updated = await updateReview(reviewId, { status });
      setReview(updated);
    } catch (err) {
      setStatusError("Failed to update status");
    } finally {
      setStatusSaving(false);
    }
  }

  const isAssignedReviewer = !!review && !!user && review.reviewer_id === user.id;
  const canEditReview = hasPermission(user, "reviews.edit") || (hasPermission(user, "reviews.finalize_own") && isAssignedReviewer);
  const canApprove = review && review.status !== "error" && review.category_scores.length > 0 && canEditReview;

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <AppNav />

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
              <div style={{ marginTop: "var(--space-3)" }}>
                <ReviewMetaBar
                  llmProvider={review.llm_provider}
                  llmModel={review.llm_model}
                  source={review.source}
                  compileCheckMode={review.compile_check_mode}
                />
              </div>
              <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap", alignItems: "center", marginTop: "var(--space-4)" }}>
                {review.has_workbook && (
                  <a
                    href={getDownloadUrl(`/api/reviews/${review.id}/download`)}
                    download
                    className="btn btn-primary"
                  >
                    Download workbook
                    <DownloadIcon />
                  </a>
                )}
                {hasPermission(user, "reviews.delete") && (
                  <button
                    type="button"
                    className="btn btn-ghost"
                    style={{ color: "var(--color-brand-coral)" }}
                    disabled={deleting}
                    onClick={handleDelete}
                  >
                    {deleting ? "Deleting…" : "Delete review"}
                  </button>
                )}
              </div>
              {deleteError && (
                <p className="card-body" style={{ color: "var(--color-brand-coral)", marginTop: "var(--space-2)" }}>{deleteError}</p>
              )}
              {review.error && (
                <p className="card-body" style={{ color: "var(--color-brand-coral)", marginTop: "var(--space-3)" }}>{review.error}</p>
              )}
            </header>

            {canAssignReviewer && (
            <div className="card card-subtle" style={{ padding: 20, marginBottom: "var(--space-4)" }}>
              <div className="card-kicker">Reviewer</div>
              <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-3)", alignItems: "center", flexWrap: "wrap" }}>
                <select
                  aria-label="Reviewer"
                  className="input"
                  value={review.reviewer_id || ""}
                  disabled={reviewerSaving}
                  onChange={handleChangeReviewer}
                >
                  <option value="">Unassigned</option>
                  {reviewers.map((reviewer) => (
                    <option key={reviewer.id} value={reviewer.id}>{reviewer.email}</option>
                  ))}
                </select>
              </div>
              {reviewerError && <p className="card-body" style={{ color: "var(--color-brand-coral)", marginTop: "var(--space-2)" }}>{reviewerError}</p>}
            </div>
            )}

            {canApprove && (
              <div className="card card-subtle" style={{ padding: 20, marginBottom: "var(--space-4)" }}>
                <div className="card-kicker">Approval</div>
                <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-3)", flexWrap: "wrap", alignItems: "center" }}>
                  {SELECTABLE_STATUSES.map((status) => (
                    <button
                      key={status}
                      type="button"
                      className={`btn ${review.status === status ? "btn-primary" : ""}`}
                      disabled={statusSaving}
                      onClick={() => handleChangeStatus(status)}
                    >
                      {STATUS_LABELS[status]}
                    </button>
                  ))}
                  {!editing && (
                    <button type="button" className="btn btn-ghost" style={{ marginLeft: "auto" }} onClick={handleStartEdit}>
                      Edit scores
                    </button>
                  )}
                </div>
                {statusError && <p className="card-body" style={{ color: "var(--color-brand-coral)", marginTop: "var(--space-2)" }}>{statusError}</p>}
              </div>
            )}

            <ReportTable
              categoryScores={editing ? draftCategoryScores : review.category_scores}
              editable={editing}
              onChangeScore={handleChangeScore}
              onChangeRemark={handleChangeRemark}
            />

            {editing && (
              <div style={{ display: "flex", gap: "var(--space-3)", marginTop: "var(--space-4)", alignItems: "center" }}>
                <button type="button" className="btn btn-primary" disabled={saving} onClick={handleSaveEdit}>
                  {saving ? "Saving…" : "Save changes"}
                </button>
                <button type="button" className="btn" disabled={saving} onClick={handleCancelEdit}>Cancel</button>
                {saveError && <p className="card-body" style={{ color: "var(--color-brand-coral)", margin: 0 }}>{saveError}</p>}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
