import { Navigate, useLocation, useParams } from "react-router-dom";
import { PLATFORMS } from "../platforms";
import AndroidReviewFlow from "./AndroidReviewFlow";
import PlaceholderReviewFlow from "./PlaceholderReviewFlow";

export default function ReviewPage() {
  const { platform: platformId } = useParams();
  const location = useLocation();
  const platform = PLATFORMS.find((p) => p.id === platformId);

  if (!platform) return <Navigate to="/" replace />;
  if (platform.available) return <AndroidReviewFlow platform={platform} projectId={location.state?.projectId ?? null} />;
  return <PlaceholderReviewFlow platform={platform} />;
}
