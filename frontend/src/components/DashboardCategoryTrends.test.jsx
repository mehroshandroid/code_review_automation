import { render, screen } from "@testing-library/react";
import DashboardCategoryTrends from "./DashboardCategoryTrends";

// jsdom has no ResizeObserver and reports 0 layout size, so recharts'
// ResponsiveContainer would otherwise never measure a real size and render
// nothing -- polyfill both so the charts actually lay out their SVG content.
// CRA's jest config resets mock implementations before every test, so this
// has to be reinstalled in beforeEach rather than beforeAll.
beforeAll(() => {
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

beforeEach(() => {
  jest.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
    width: 600, height: 220, top: 0, left: 0, bottom: 220, right: 600, x: 0, y: 0, toJSON() {},
  });
});

const androidReview = {
  id: "r1", project_name: "Moove", platform: "Android", status: "pending_approval",
  created_at: "2026-08-01T00:00:00Z", total_score_pct: 80,
  category_scores: [{ id: "c1", name: "Code Structure", percent_points: 80 }, { id: "c2", name: "Security", percent_points: 60 }],
};

const dotnetReview = {
  id: "r2", project_name: "Payments", platform: ".NET", status: "approved",
  created_at: "2026-08-02T00:00:00Z", total_score_pct: 90,
  category_scores: [{ id: "c1", name: "Code Structure", percent_points: 90 }],
};

test("renders nothing when there are no chartable reviews", () => {
  const { container } = render(<DashboardCategoryTrends reviews={[]} />);
  expect(container).toBeEmptyDOMElement();
});

test("excludes errored reviews and reviews with no category scores", () => {
  const reviews = [
    { ...androidReview, id: "r3", status: "error" },
    { ...androidReview, id: "r4", category_scores: [] },
  ];
  const { container } = render(<DashboardCategoryTrends reviews={reviews} />);
  expect(container).toBeEmptyDOMElement();
});

test("renders one chart card per platform present in the filtered reviews", () => {
  render(<DashboardCategoryTrends reviews={[androidReview, dotnetReview]} />);

  expect(screen.getByText("Android clause scores")).toBeInTheDocument();
  expect(screen.getByText(".NET clause scores")).toBeInTheDocument();
});

test("shows a legend entry for each distinct category on that platform's chart", () => {
  render(<DashboardCategoryTrends reviews={[androidReview]} />);

  expect(screen.getByText("Code Structure")).toBeInTheDocument();
  expect(screen.getByText("Security")).toBeInTheDocument();
});

test("labels each x-axis point with the review's date and project", () => {
  render(<DashboardCategoryTrends reviews={[androidReview]} />);

  // Recharts wraps a long tick label across multiple <tspan> lines, so no
  // single text node holds the full string -- match on the <text> element's
  // combined textContent instead.
  const expected = `${new Date(androidReview.created_at).toLocaleDateString()}·Moove`;
  expect(screen.getByText((_, element) => element.tagName === "text" && element.textContent.replace(/\s+/g, "") === expected)).toBeInTheDocument();
});
