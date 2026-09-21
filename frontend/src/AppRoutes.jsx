import { Routes, Route } from "react-router-dom";
import ProjectDashboardPage from "./pages/ProjectDashboardPage";
import ReviewPage from "./pages/ReviewPage";
import ReviewReportPage from "./pages/ReviewReportPage";
import SettingsPage from "./pages/SettingsPage";
import LoginPage from "./pages/LoginPage";
import UsersPage from "./pages/UsersPage";
import { RequireAuth, RequireRole } from "./components/RouteGuards";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RequireAuth><ProjectDashboardPage /></RequireAuth>} />
      <Route path="/review/:platform" element={<RequireAuth><ReviewPage /></RequireAuth>} />
      <Route path="/reports/:reviewId" element={<RequireAuth><ReviewReportPage /></RequireAuth>} />
      <Route path="/settings" element={<RequireRole roles={["admin", "reviewer"]}><SettingsPage /></RequireRole>} />
      <Route path="/users" element={<RequireRole roles={["admin"]}><UsersPage /></RequireRole>} />
    </Routes>
  );
}
