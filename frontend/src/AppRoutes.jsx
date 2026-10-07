import { Routes, Route } from "react-router-dom";
import ProjectDashboardPage from "./pages/ProjectDashboardPage";
import ReviewPage from "./pages/ReviewPage";
import ReviewReportPage from "./pages/ReviewReportPage";
import SettingsPage from "./pages/SettingsPage";
import LoginPage from "./pages/LoginPage";
import UsersPage from "./pages/UsersPage";
import { RequireAuth, RequirePermission } from "./components/RouteGuards";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RequireAuth><ProjectDashboardPage /></RequireAuth>} />
      <Route path="/review/:platform" element={<RequireAuth><ReviewPage /></RequireAuth>} />
      <Route path="/reports/:reviewId" element={<RequireAuth><ReviewReportPage /></RequireAuth>} />
      <Route path="/settings" element={<RequirePermission anyOf={["settings.manage"]}><SettingsPage /></RequirePermission>} />
      <Route path="/users" element={<RequirePermission anyOf={["users.manage"]}><UsersPage /></RequirePermission>} />
    </Routes>
  );
}
