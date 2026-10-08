import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppNav from "../components/AppNav";
import AssignmentStatusBadge from "../components/AssignmentStatusBadge";
import { COMPILE_OPTIONS } from "../components/AutomationSettingsSection";
import RunSettingsDialog, { PROVIDER_LABELS } from "../components/RunSettingsDialog";
import {
  getQueue, moveQueueItemToFront, pauseQueue, removeQueueItem, resumeQueue, retryAssignment, stopQueueItem,
} from "../services/api";

const REFRESH_MS = 5000;
const FAILURE_KIND_LABELS = { url: "URL", system: "System", stopped: "Stopped" };

function minutesBetween(fromIso, toMs) {
  const seconds = Math.max(0, Math.round((toMs - new Date(fromIso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return minutes < 60 ? `${minutes}m ${seconds % 60}s` : `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function label(item) {
  return `${item.project_name} · ${item.platform} · Q${item.quarter} ${item.year}`;
}

function OverrideChips({ item }) {
  const compile = (COMPILE_OPTIONS[item.platform] || []).find(([value]) => value === item.override_compile_mode)?.[1];
  return (
    <>
      {item.override_llm_provider && (
        <span className="tag tag-outline">
          LLM: {PROVIDER_LABELS[item.override_llm_provider]}{item.override_llm_model ? ` (${item.override_llm_model})` : ""}
        </span>
      )}
      {compile && <span className="tag tag-outline">Compile: {compile}</span>}
    </>
  );
}

function Panel({ title, empty, items, children }) {
  return (
    <section className="card queue-panel" aria-label={title}>
      <div className="queue-panel-title">{title} <span className="queue-panel-count">{items.length}</span></div>
      {items.length === 0 ? <p className="card-body" style={{ margin: 0 }}>{empty}</p> : <ul className="queue-list">{children}</ul>}
    </section>
  );
}

function ConfirmDialog({ title, body, confirmLabel, onConfirm, onClose }) {
  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" role="dialog" aria-label={title} onClick={(event) => event.stopPropagation()}>
        <div className="dialog-title">{title}</div>
        <div className="dialog-body"><p className="card-body" style={{ margin: 0 }}>{body}</p></div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-primary" onClick={() => { onClose(); onConfirm(); }}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

export default function QueuePage() {
  const [queue, setQueue] = useState(null);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState(null);
  const [now, setNow] = useState(Date.now());
  const [confirm, setConfirm] = useState(null);
  const [settingsFor, setSettingsFor] = useState(null);

  const load = useCallback(() => getQueue()
    .then((result) => { setQueue(result); setUpdatedAt(Date.now()); })
    .catch(() => setError("Couldn't load the queue.")), []);

  useEffect(() => {
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  async function act(request) {
    setError("");
    try {
      await request();
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || "Something went wrong.");
    }
  }

  const status = !queue ? null : queue.paused ? "Paused" : queue.running.length ? "Running" : "Idle";
  const defaults = queue?.defaults;

  return (
    <div className="page">
      <AppNav />
      <main className="page-main">
        <header className="page-header">
          <div>
            <h1 className="page-title">Review queue</h1>
            <p className="page-subtitle">
              Automated quarterly reviews run one at a time, oldest first.
              {updatedAt && <> Updated {minutesBetween(new Date(updatedAt).toISOString(), now)} ago.</>}
            </p>
          </div>
          {queue && (
            <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center", flexWrap: "wrap" }}>
              <span className={`queue-status queue-status--${status.toLowerCase()}`}>{status}</span>
              {queue.paused && queue.paused_by_name && (
                <span className="quarter-card-meta">Paused by {queue.paused_by_name} · {new Date(queue.paused_at).toLocaleString()}</span>
              )}
              {queue.paused ? (
                <button type="button" className="btn btn-primary" onClick={() => act(resumeQueue)}>Resume queue</button>
              ) : (
                <button
                  type="button" className="btn"
                  onClick={() => setConfirm({
                    title: "Pause the queue?",
                    body: "No new reviews will start. The running review will be stopped and restarted from the beginning when you resume.",
                    confirmLabel: "Pause", action: pauseQueue,
                  })}
                >
                  Pause queue
                </button>
              )}
            </div>
          )}
        </header>

        {error && <p className="card-body" style={{ color: "var(--color-brand-coral)" }}>{error}</p>}

        {defaults && (
          <p className="quarter-card-meta" style={{ margin: 0 }}>
            Defaults: {PROVIDER_LABELS[defaults.llm_provider] || defaults.llm_provider}
            {Object.entries(defaults.compile_modes).map(([platform, mode]) => ` · ${platform} ${(COMPILE_OPTIONS[platform] || []).find(([v]) => v === mode)?.[1] || mode}`).join("")}
            {" "}(change in <Link to="/settings">Settings</Link>) · {queue.waiting_for_url} waiting for a URL
          </p>
        )}

        {queue && (
          <div className="queue-grid">
            <Panel title="Running now" empty="Nothing is running." items={queue.running}>
              {queue.running.map((item) => (
                <li key={`${item.cycle_id}-${item.platform}`} className="queue-item">
                  <div className="queue-item-main">
                    <span className="queue-item-title">{label(item)}</span>
                    <AssignmentStatusBadge assignment={item} />
                    <OverrideChips item={item} />
                  </div>
                  <div className="progress-track" role="progressbar" aria-valuenow={item.run_progress ?? 0} aria-valuemin={0} aria-valuemax={100}>
                    <div className="progress-fill" style={{ width: `${item.run_progress ?? 0}%` }} />
                  </div>
                  <div className="queue-item-meta">
                    {item.started_at && <span>Running {minutesBetween(item.started_at, now)}</span>}
                    <span>Attempt {item.attempts}</span>
                    <span>Reviewer {item.reviewer_name || "—"}</span>
                  </div>
                  <div className="queue-item-actions">
                    {item.cancel_requested ? <span className="quarter-card-meta">Stopping…</span> : (
                      <button type="button" className="btn btn-ghost" onClick={() => setConfirm({
                        title: "Stop this review?",
                        body: `${label(item)} will be marked failed (stopped). You can retry it later.`,
                        confirmLabel: "Stop review", action: () => stopQueueItem(item.cycle_id, item.platform),
                      })}>Stop</button>
                    )}
                  </div>
                </li>
              ))}
            </Panel>

            <Panel title="Queued" empty="The queue is empty." items={queue.queued}>
              {queue.queued.map((item) => (
                <li key={`${item.cycle_id}-${item.platform}`} className="queue-item">
                  <div className="queue-item-main">
                    <span className="queue-position">#{item.queue_position}</span>
                    <span className="queue-item-title">{label(item)}</span>
                    <OverrideChips item={item} />
                  </div>
                  <div className="queue-item-meta">
                    {item.queued_at && <span>Waiting {minutesBetween(item.queued_at, now)}</span>}
                    <span>Reviewer {item.reviewer_name || "—"}</span>
                  </div>
                  <div className="queue-item-actions">
                    {item.queue_position !== 1 && (
                      <button type="button" className="btn btn-ghost" onClick={() => act(() => moveQueueItemToFront(item.cycle_id, item.platform))}>Move to front</button>
                    )}
                    <button type="button" className="btn btn-ghost" onClick={() => setSettingsFor(item)}>Run settings</button>
                    <button type="button" className="btn btn-ghost" onClick={() => setConfirm({
                      title: "Remove from the queue?",
                      body: `${label(item)} goes back to "Waiting for URL" and the project's PMs are notified.`,
                      confirmLabel: "Remove from queue", action: () => removeQueueItem(item.cycle_id, item.platform),
                    })}>Remove</button>
                  </div>
                </li>
              ))}
            </Panel>

            <Panel title="Failed" empty="No failed reviews." items={queue.failed}>
              {queue.failed.map((item) => (
                <li key={`${item.cycle_id}-${item.platform}`} className="queue-item">
                  <div className="queue-item-main">
                    <span className="queue-item-title">{label(item)}</span>
                    {item.failure_kind && <span className={`tag tag-outline failure-kind failure-kind--${item.failure_kind}`}>{FAILURE_KIND_LABELS[item.failure_kind] || item.failure_kind}</span>}
                    <OverrideChips item={item} />
                  </div>
                  <div className="run-error">{item.run_error}</div>
                  <div className="queue-item-meta">{item.finished_at && <span>Failed {new Date(item.finished_at).toLocaleString()}</span>}</div>
                  <div className="queue-item-actions">
                    <button type="button" className="btn btn-ghost" onClick={() => act(() => retryAssignment(item.cycle_id, item.platform))}>Retry</button>
                    <button type="button" className="btn btn-ghost" onClick={() => setSettingsFor(item)}>Run settings</button>
                  </div>
                </li>
              ))}
            </Panel>

            <Panel title="Recently completed" empty="No completed reviews yet." items={queue.completed}>
              {queue.completed.map((item) => (
                <li key={`${item.cycle_id}-${item.platform}`} className="queue-item">
                  <div className="queue-item-main">
                    <span className="queue-item-title">{label(item)}</span>
                    <AssignmentStatusBadge assignment={item} />
                  </div>
                  <div className="queue-item-meta">
                    {item.finished_at && <span>Finished {new Date(item.finished_at).toLocaleString()}</span>}
                    {item.started_at && item.finished_at && <span>Took {minutesBetween(item.started_at, new Date(item.finished_at).getTime())}</span>}
                  </div>
                  <div className="queue-item-actions">
                    {item.review_id && <Link to={`/reports/${item.review_id}`} className="btn btn-ghost">View</Link>}
                  </div>
                </li>
              ))}
            </Panel>
          </div>
        )}
      </main>

      {confirm && (
        <ConfirmDialog
          title={confirm.title} body={confirm.body} confirmLabel={confirm.confirmLabel}
          onConfirm={() => act(confirm.action)} onClose={() => setConfirm(null)}
        />
      )}
      {settingsFor && defaults && (
        <RunSettingsDialog item={settingsFor} defaults={defaults} onSaved={load} onClose={() => setSettingsFor(null)} />
      )}
    </div>
  );
}
