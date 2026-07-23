import { render, screen } from "@testing-library/react";
import StatsDisplay from "./StatsDisplay";

test("shows timing breakdown for each provided stat", () => {
  const stats = {
    ingest_time_ms: 100, analysis_time_ms: 200, scoring_time_ms: 300,
    generation_time_ms: 50, total_time_ms: 650,
  };
  render(<StatsDisplay stats={stats} downloadUrl="/api/reviews/abc-123/download" />);

  expect(screen.getByText(/Ingest: 100ms/)).toBeInTheDocument();
  expect(screen.getByText(/Total: 650ms/)).toBeInTheDocument();
});

test("renders a download link pointing at the constructed download URL", () => {
  render(<StatsDisplay stats={{}} downloadUrl="/api/reviews/abc-123/download" />);
  const link = screen.getByRole("link", { name: /download result/i });
  expect(link).toHaveAttribute("href", "http://localhost:8000/api/reviews/abc-123/download");
  expect(link).toHaveAttribute("download");
});
