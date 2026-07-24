import { useEffect, useState } from "react";
import { getProgress } from "../services/api";

const POLL_INTERVAL_MS = 2000;

export default function ProgressTracker({ reviewId, onUpdate }) {
  const [progressData, setProgressData] = useState(null);

  useEffect(() => {
    let intervalId;
    let cancelled = false;

    async function poll() {
      const data = await getProgress(reviewId);
      if (cancelled) return;
      setProgressData(data);
      onUpdate(data);
      if (data.status !== "processing") {
        clearInterval(intervalId);
      }
    }

    poll();
    intervalId = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [reviewId, onUpdate]);

  const phase = progressData?.phase ?? "starting";
  const progress = progressData?.progress ?? 0;
  const message = progressData?.message;

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium capitalize">{phase}</p>
      <div className="w-full bg-gray-200 rounded h-2">
        <div
          className="bg-blue-600 h-2 rounded transition-all duration-500 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>
      {message && <p className="text-sm text-gray-500">{message}</p>}
    </div>
  );
}
