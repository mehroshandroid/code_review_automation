import { useEffect, useState } from "react";
import DashboardFilters from "../components/DashboardFilters";
import DashboardOverview from "../components/DashboardOverview";
import DashboardCategoryTrends from "../components/DashboardCategoryTrends";
import DashboardResultsTable from "../components/DashboardResultsTable";
import StartReviewDialog from "../components/StartReviewDialog";
import UploadReviewDialog from "../components/UploadReviewDialog";
import ChatWidget from "../components/ChatWidget";
import AppNav from "../components/AppNav";
import PendingCyclesPanel from "../components/PendingCyclesPanel";
import { getProjects, getReviews, getReviewYears } from "../services/api";
import { useCan } from "../context/AuthContext";

function currentYear() {
  return new Date().getFullYear();
}

export default function ProjectDashboardPage() {
  const can = useCan();
  const [projects, setProjects] = useState([]);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  const [years, setYears] = useState([]);
  const [year, setYear] = useState(currentYear());
  const [platform, setPlatform] = useState(null);
  const [projectId, setProjectId] = useState(null);
  const [reviews, setReviews] = useState(null); // null = still loading
  const [startReviewOpen, setStartReviewOpen] = useState(false);
  const [uploadReviewOpen, setUploadReviewOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getProjects()
      .then((result) => { if (!cancelled) { setProjects(result); setProjectsLoaded(true); } })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    getReviewYears().then((result) => { if (!cancelled) setYears(result); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setReviews(null);
    getReviews({ year, platform, projectId })
      .then((result) => { if (!cancelled) setReviews(result); })
      .catch(() => { if (!cancelled) setReviews([]); });
    return () => { cancelled = true; };
  }, [year, platform, projectId, refreshKey]);

  function handleProjectCreated(project) {
    setProjects((current) => [project, ...current]);
  }

  function handleProjectRenamed(project) {
    setProjects((current) => current.map((p) => (p.id === project.id ? project : p)));
  }

  function handleReset() {
    setYear(currentYear());
    setPlatform(null);
    setProjectId(null);
  }

  function handleReviewUploaded(review) {
    setYear(new Date(review.created_at).getFullYear());
    setPlatform(review.platform);
    setProjectId(review.project_id);
    setRefreshKey((key) => key + 1);
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <AppNav />

      <main style={{ maxWidth: 1600, margin: "0 auto", padding: "40px 16px 96px", display: "grid", gap: "var(--space-4)" }}>
        <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-3)", flexWrap: "wrap" }}>
          <p style={{ margin: 0, color: "var(--color-text-muted)", maxWidth: "60ch", fontSize: 16, lineHeight: 1.6 }}>
            Filter review history by year, platform, and project.
          </p>
          {can("reviews.create") && (
            <div style={{ display: "flex", gap: "var(--space-2)" }}>
              <button type="button" className="btn" onClick={() => setUploadReviewOpen(true)}>Upload review</button>
              <button type="button" className="btn btn-primary" onClick={() => setStartReviewOpen(true)}>Start review</button>
            </div>
          )}
        </header>

        {can("cycles.submit_urls") && can("dashboard.view_assigned") && <PendingCyclesPanel />}

        {can("dashboard.view_assigned") && projectsLoaded && projects.length === 0 ? (
          <div className="card" style={{ padding: 20 }}>
            <p className="card-body">No projects assigned yet — contact your admin.</p>
          </div>
        ) : (
          <>
            <DashboardFilters
              year={year} years={years} onYearChange={setYear}
              platform={platform} onPlatformChange={setPlatform}
              projectId={projectId} projects={projects} onProjectChange={setProjectId}
              onProjectCreated={handleProjectCreated} onProjectRenamed={handleProjectRenamed}
              onReset={handleReset}
            />

            {reviews !== null && (
              reviews.length === 0 ? (
                <div className="card" style={{ padding: 20 }}>
                  <p className="card-body">No reviews match these filters.</p>
                </div>
              ) : (
                <>
                  <DashboardOverview reviews={reviews} />
                  <DashboardCategoryTrends reviews={reviews} />
                  <DashboardResultsTable reviews={reviews} />
                </>
              )
            )}
          </>
        )}
      </main>

      {can("reviews.create") && startReviewOpen && (
        <StartReviewDialog
          projects={projects}
          onProjectCreated={handleProjectCreated}
          onClose={() => setStartReviewOpen(false)}
        />
      )}

      {can("reviews.create") && uploadReviewOpen && (
        <UploadReviewDialog
          projects={projects}
          onProjectCreated={handleProjectCreated}
          onUploaded={handleReviewUploaded}
          onClose={() => setUploadReviewOpen(false)}
        />
      )}

      {can("chat.use") && <ChatWidget />}
    </div>
  );
}
