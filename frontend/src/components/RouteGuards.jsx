import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { hasAny } from "../permissions";

export function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

export function RequirePermission({ anyOf, children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (!hasAny(user, anyOf)) return <Navigate to={user.home_path || "/"} replace />;
  return children;
}

// "/" is the scores dashboard for roles that have one, the quarterly dashboard
// for roles that only track cycles (coordinator), and otherwise the user's home.
export function DashboardOrHome({ children, quarterly = null }) {
  const { user } = useAuth();
  if (hasAny(user, ["dashboard.view_all", "dashboard.view_assigned"])) return children;
  if (quarterly && hasAny(user, ["cycles.view"])) return quarterly;
  return <Navigate to={user?.home_path && user.home_path !== "/" ? user.home_path : "/login"} replace />;
}
