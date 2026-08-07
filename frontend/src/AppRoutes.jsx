import { Routes, Route } from "react-router-dom";
import ProjectDashboardPage from "./pages/ProjectDashboardPage";
import ReviewPage from "./pages/ReviewPage";
import ReviewReportPage from "./pages/ReviewReportPage";
import SettingsPage from "./pages/SettingsPage";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<ProjectDashboardPage />} />
      <Route path="/review/:platform" element={<ReviewPage />} />
      <Route path="/reports/:reviewId" element={<ReviewReportPage />} />
      <Route path="/settings" element={<SettingsPage />} />
    </Routes>
  );
}
