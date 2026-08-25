import { render, screen } from "@testing-library/react";
import DashboardOverview from "./DashboardOverview";

function buildReview(overrides) {
  return {
    id: "r", status: "pending_approval", total_score_pct: 80,
    category_scores: [{ id: "1", name: "Structure", percent_points: 80 }],
    ...overrides,
  };
}

test("shows an empty state when there are no non-error reviews", () => {
  render(<DashboardOverview reviews={[buildReview({ status: "error", total_score_pct: null, category_scores: [] })]} />);
  expect(screen.getByText(/no scored reviews match/i)).toBeInTheDocument();
});

test("shows an empty state when there are zero reviews at all", () => {
  render(<DashboardOverview reviews={[]} />);
  expect(screen.getByText(/no scored reviews match/i)).toBeInTheDocument();
});

test("renders the Final Score as the average total_score_pct across non-error reviews", () => {
  render(<DashboardOverview reviews={[
    buildReview({ id: "r1", total_score_pct: 80 }),
    buildReview({ id: "r2", total_score_pct: 60 }),
  ]} />);

  expect(screen.getByText("70.0%")).toBeInTheDocument();
  expect(screen.getByText("Final Score")).toBeInTheDocument();
});

test("excludes errored reviews from the Final Score average", () => {
  render(<DashboardOverview reviews={[
    buildReview({ id: "r1", total_score_pct: 80, category_scores: [{ id: "1", name: "Structure", percent_points: 55 }] }),
    buildReview({ id: "r2", status: "error", total_score_pct: null, category_scores: [] }),
  ]} />);

  expect(screen.getByText("80.0%")).toBeInTheDocument();
});

test("shows how many reviews the Final Score is based on", () => {
  render(<DashboardOverview reviews={[
    buildReview({ id: "r1" }),
    buildReview({ id: "r2" }),
    buildReview({ id: "r3", status: "error", total_score_pct: null, category_scores: [] }),
  ]} />);

  expect(screen.getByText(/based on 2 reviews/i)).toBeInTheDocument();
});

test("uses singular wording for exactly one review", () => {
  render(<DashboardOverview reviews={[buildReview({ id: "r1" })]} />);
  expect(screen.getByText(/based on 1 review$/i)).toBeInTheDocument();
});

test("renders one ring per distinct category name, averaging percent_points across reviews that have it", () => {
  render(<DashboardOverview reviews={[
    buildReview({ id: "r1", category_scores: [{ id: "2", name: "Security", percent_points: 40 }] }),
    buildReview({ id: "r2", category_scores: [{ id: "2", name: "Security", percent_points: 90 }] }),
  ]} />);

  expect(screen.getByText("Security")).toBeInTheDocument();
  expect(screen.getByText("65.0%")).toBeInTheDocument();
});

test("skips null percent_points when averaging a category", () => {
  render(<DashboardOverview reviews={[
    buildReview({ id: "r1", category_scores: [{ id: "2", name: "Security", percent_points: 100 }] }),
    buildReview({ id: "r2", category_scores: [{ id: "2", name: "Security", percent_points: null }] }),
  ]} />);

  expect(screen.getByText("100.0%")).toBeInTheDocument();
});
