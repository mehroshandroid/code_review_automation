import { Routes, Route } from "react-router-dom";
import ProjectDashboardPage from "./pages/ProjectDashboardPage";
import ReviewPage from "./pages/ReviewPage";
import ReviewReportPage from "./pages/ReviewReportPage";
import SettingsPage from "./pages/SettingsPage";
import LoginPage from "./pages/LoginPage";
import UsersPage from "./pages/UsersPage";
import MyReviewsPage from "./pages/MyReviewsPage";
import ProjectsPage from "./pages/ProjectsPage";
import { DashboardOrHome, RequireAuth, RequirePermission } from "./components/RouteGuards";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RequireAuth><DashboardOrHome><ProjectDashboardPage /></DashboardOrHome></RequireAuth>} />
      <Route path="/review/:platform" element={<RequirePermission anyOf={["reviews.create"]}><ReviewPage /></RequirePermission>} />
      <Route path="/reports/:reviewId" element={<RequireAuth><ReviewReportPage /></RequireAuth>} />
      <Route path="/my-reviews" element={<RequirePermission anyOf={["my_reviews.view"]}><MyReviewsPage /></RequirePermission>} />
      <Route path="/projects" element={<RequirePermission anyOf={["projects.view"]}><ProjectsPage /></RequirePermission>} />
      <Route path="/settings" element={<RequirePermission anyOf={["settings.manage"]}><SettingsPage /></RequirePermission>} />
      <Route path="/users" element={<RequirePermission anyOf={["users.manage"]}><UsersPage /></RequirePermission>} />
    </Routes>
  );
}
