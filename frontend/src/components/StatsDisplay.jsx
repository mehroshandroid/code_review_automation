import { getDownloadUrl } from "../services/api";

export default function StatsDisplay({ stats, downloadUrl }) {
  return (
    <div className="space-y-3">
      <h3 className="font-medium">Review Complete</h3>
      <ul className="text-sm text-gray-600 space-y-1">
        {stats.ingest_time_ms !== undefined && <li>Ingest: {stats.ingest_time_ms}ms</li>}
        {stats.analysis_time_ms !== undefined && <li>Analysis: {stats.analysis_time_ms}ms</li>}
        {stats.scoring_time_ms !== undefined && <li>Scoring: {stats.scoring_time_ms}ms</li>}
        {stats.generation_time_ms !== undefined && <li>Generation: {stats.generation_time_ms}ms</li>}
        {stats.total_time_ms !== undefined && <li className="font-medium">Total: {stats.total_time_ms}ms</li>}
      </ul>
      <a
        href={getDownloadUrl(downloadUrl)}
        download
        className="inline-block bg-green-600 text-white px-4 py-2 rounded"
      >
        Download Result
      </a>
    </div>
  );
}
