import { Routes, Route } from "react-router-dom";
import ProjectDashboardPage from "./pages/ProjectDashboardPage";
import ReviewPage from "./pages/ReviewPage";
import ReviewReportPage from "./pages/ReviewReportPage";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<ProjectDashboardPage />} />
      <Route path="/review/:platform" element={<ReviewPage />} />
      <Route path="/reports/:reviewId" element={<ReviewReportPage />} />
    </Routes>
  );
}
