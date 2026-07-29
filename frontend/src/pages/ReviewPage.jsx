import { Navigate, useParams } from "react-router-dom";
import { PLATFORMS } from "../platforms";
import AndroidReviewFlow from "./AndroidReviewFlow";
import PlaceholderReviewFlow from "./PlaceholderReviewFlow";

export default function ReviewPage() {
  const { platform: platformId } = useParams();
  const platform = PLATFORMS.find((p) => p.id === platformId);

  if (!platform) return <Navigate to="/" replace />;
  if (platform.id === "android") return <AndroidReviewFlow platform={platform} />;
  return <PlaceholderReviewFlow platform={platform} />;
}
