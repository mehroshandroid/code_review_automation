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

  if (!progressData) {
    return <p className="text-gray-500">Starting review...</p>;
  }

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium capitalize">{progressData.phase}</p>
      <div className="w-full bg-gray-200 rounded h-2">
        <div className="bg-blue-600 h-2 rounded" style={{ width: `${progressData.progress}%` }} />
      </div>
      <p className="text-sm text-gray-500">{progressData.message}</p>
    </div>
  );
}
