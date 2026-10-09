import { assignmentStatusLabel } from "./AssignmentStatusBadge";
import { StageDots } from "./StageTracker";

export const STATUS_LABELS = {
  done: "Done", in_progress: "In progress", overdue: "Overdue", not_started: "Not started", not_applicable: "N/A",
};

export const QUARTER_MONTHS = { 1: "Jan–Mar", 2: "Apr–Jun", 3: "Jul–Sep", 4: "Oct–Dec" };

function shortDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export default function QuarterCard({ entry, platforms, canInitiate, onInitiate, canManage = false, onManage }) {
  const coveredByPlatform = Object.fromEntries(entry.covered.map((c) => [c.platform, c]));
  const reviewerByPlatform = Object.fromEntries((entry.cycle?.assignments || []).map((a) => [a.platform, a.reviewer_name]));
  const assignmentByPlatform = Object.fromEntries((entry.cycle?.assignments || []).map((a) => [a.platform, a]));
  const statusClass = entry.status.replace("_", "-");

  return (
    <div className={`quarter-card quarter-card--${statusClass}`}>
      <div className="quarter-card-head">
        <span className="quarter-card-title">Q{entry.quarter} · {QUARTER_MONTHS[entry.quarter]}</span>
        <span style={{ display: "flex", gap: 4 }}>
          {entry.late && <span className="quarter-badge quarter-badge--late" title="Started after the quarter ended">Late</span>}
          <span className={`quarter-badge quarter-badge--${statusClass}`}>{STATUS_LABELS[entry.status]}</span>
        </span>
      </div>
      {entry.status !== "not_applicable" && (
        <ul className="quarter-card-platforms">
          {platforms.map((platform) => {
            const covered = coveredByPlatform[platform];
            return (
              <li key={platform}>
                <span aria-hidden="true" className={covered ? "quarter-tick" : "quarter-dot"}>{covered ? "✓" : "○"}</span>
                {" "}{platform}
                {entry.cycle && assignmentByPlatform[platform] && (
                  <>{" "}<StageDots assignment={assignmentByPlatform[platform]} initiatedAt={entry.cycle.initiated_at} /></>
                )}
                {covered && <span className="quarter-card-meta"> · {shortDate(covered.reviewed_at)}{covered.late ? " (late)" : ""}</span>}
                {reviewerByPlatform[platform] && <span className="quarter-card-meta"> · {reviewerByPlatform[platform]}</span>}
                {!covered && assignmentByPlatform[platform]?.run_status && assignmentByPlatform[platform].run_status !== "completed" && (
                  <span className="quarter-card-meta"> · {assignmentStatusLabel(assignmentByPlatform[platform])}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {entry.cycle && (
        <p className="quarter-card-meta" style={{ margin: 0 }}>
          Initiated {shortDate(entry.cycle.initiated_at)}{entry.cycle.initiated_by_name ? ` by ${entry.cycle.initiated_by_name}` : ""}
        </p>
      )}
      {canInitiate && entry.can_initiate && (
        <button type="button" className="btn btn-primary quarter-card-action" onClick={onInitiate}>Initiate review</button>
      )}
      {canManage && entry.cycle && (
        <button type="button" className="btn btn-ghost quarter-card-action" onClick={onManage}>Manage</button>
      )}
    </div>
  );
}
