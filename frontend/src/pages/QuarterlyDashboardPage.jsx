import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppNav from "../components/AppNav";
import QuarterCard from "../components/QuarterCard";
import InitiateCycleDialog from "../components/InitiateCycleDialog";
import { useCan } from "../context/AuthContext";
import { getQuarterly, getReviewYears } from "../services/api";

export default function QuarterlyDashboardPage() {
  const can = useCan();
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const [years, setYears] = useState([thisYear - 2, thisYear - 1, thisYear]);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [initiating, setInitiating] = useState(null); // { project, entry, year }

  useEffect(() => {
    let cancelled = false;
    getReviewYears()
      .then((reviewYears) => { if (!cancelled) setYears((current) => [...new Set([...current, ...reviewYears])].sort((a, b) => b - a)); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setError("");
    // Drop the previous year's cards so a stale card can't initiate the newly selected year.
    setData(null);
    getQuarterly(year)
      .then((result) => { if (!cancelled) setData(result); })
      .catch(() => { if (!cancelled) setError("Couldn't load quarterly status."); });
    return () => { cancelled = true; };
  }, [year]);

  function replaceEntry(projectId, entryYear, updated) {
    // Only apply to the year the initiate was for; the user may have switched years meanwhile.
    setData((current) => (!current || current.year !== entryYear ? current : {
      ...current,
      projects: current.projects.map((project) => (project.id !== projectId ? project : {
        ...project,
        quarters: project.quarters.map((entry) => (entry.quarter === updated.quarter ? updated : entry)),
      })),
    }));
  }

  const projects = (data?.projects || []).filter((project) => project.name.toLowerCase().includes(query.toLowerCase()));
  const sortedYears = [...years].sort((a, b) => b - a);

  return (
    <div className="page">
      <AppNav />
      <main className="page-main">
        <header className="page-header">
          <div>
            <h1 className="page-title">Quarterly reviews</h1>
            <p className="page-subtitle">Each project needs at least one review per platform every quarter.</p>
          </div>
          <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center", flexWrap: "wrap" }}>
            <input
              type="search" className="input" aria-label="Search projects" placeholder="Search projects…"
              value={query} onChange={(event) => setQuery(event.target.value)} style={{ width: 220 }}
            />
            <select aria-label="Year" className="input" value={year} onChange={(event) => setYear(Number(event.target.value))} style={{ width: 110 }}>
              {sortedYears.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
        </header>

        {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}

        {data && projects.length === 0 && (
          <div className="card" style={{ padding: 20 }}><p className="card-body">No projects found.</p></div>
        )}

        {projects.map((project) => (
          <section key={project.id} className="card quarterly-row" aria-label={project.name}>
            <div className="quarterly-row-head">
              <div className="quarterly-row-name">{project.name}</div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {project.platforms.map((platform) => <span key={platform} className="tag tag-outline">{platform}</span>)}
              </div>
            </div>
            {project.platforms.length === 0 ? (
              <Link to="/projects" className="card-body">Set platforms to track quarterly reviews</Link>
            ) : (
              <div className="quarter-grid">
                {project.quarters.map((entry) => (
                  <QuarterCard
                    key={entry.quarter} entry={entry} platforms={project.platforms}
                    canInitiate={can("cycles.initiate")}
                    onInitiate={() => setInitiating({ project, entry, year: data.year })}
                  />
                ))}
              </div>
            )}
          </section>
        ))}
      </main>

      {initiating && (
        <InitiateCycleDialog
          project={initiating.project} year={initiating.year} entry={initiating.entry}
          onInitiated={(updated) => replaceEntry(initiating.project.id, initiating.year, updated)}
          onClose={() => setInitiating(null)}
        />
      )}
    </div>
  );
}
