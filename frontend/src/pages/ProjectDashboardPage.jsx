import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import DashboardFilters from "../components/DashboardFilters";
import DashboardOverview from "../components/DashboardOverview";
import DashboardCategoryTrends from "../components/DashboardCategoryTrends";
import DashboardResultsTable from "../components/DashboardResultsTable";
import StartReviewDialog from "../components/StartReviewDialog";
import UploadReviewDialog from "../components/UploadReviewDialog";
import ChatWidget from "../components/ChatWidget";
import { GearIcon } from "../icons";
import { getProjects, getReviews, getReviewYears } from "../services/api";

function currentYear() {
  return new Date().getFullYear();
}

export default function ProjectDashboardPage() {
  const [projects, setProjects] = useState([]);
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
    getProjects().then((result) => { if (!cancelled) setProjects(result); }).catch(() => {});
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

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <nav className="nav">
        <span className="logo-mark">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        </span>
        <span className="nav-brand">Code Review Automation</span>
        <Link to="/settings" className="btn btn-ghost" aria-label="Settings" style={{ marginLeft: "auto" }}><GearIcon /></Link>
      </nav>

      <main style={{ maxWidth: 1600, margin: "0 auto", padding: "40px 16px 96px", display: "grid", gap: "var(--space-4)" }}>
        <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-3)", flexWrap: "wrap" }}>
          <p style={{ margin: 0, color: "var(--color-text-muted)", maxWidth: "60ch", fontSize: 16, lineHeight: 1.6 }}>
            Filter review history by year, platform, and project.
          </p>
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <button type="button" className="btn" onClick={() => setUploadReviewOpen(true)}>Upload review</button>
            <button type="button" className="btn btn-primary" onClick={() => setStartReviewOpen(true)}>Start review</button>
          </div>
        </header>

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
      </main>

      {startReviewOpen && (
        <StartReviewDialog
          projects={projects}
          onProjectCreated={handleProjectCreated}
          onClose={() => setStartReviewOpen(false)}
        />
      )}

      {uploadReviewOpen && (
        <UploadReviewDialog
          projects={projects}
          onProjectCreated={handleProjectCreated}
          onUploaded={() => setRefreshKey((key) => key + 1)}
          onClose={() => setUploadReviewOpen(false)}
        />
      )}

      <ChatWidget />
    </div>
  );
}
