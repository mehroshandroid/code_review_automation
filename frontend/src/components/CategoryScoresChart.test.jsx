import { render, screen } from "@testing-library/react";
import CategoryScoresChart from "./CategoryScoresChart";

const categoryScores = [
  { id: "1", name: "Code naming conventions / Code Structure", percent_points: 90.0 },
  { id: "2", name: "Reliability, Security & Observability", percent_points: 75.5 },
  { id: "3", name: "Delivery Discipline & Architecture", percent_points: null },
];

test("renders a labeled bar for each scored category", () => {
  render(<CategoryScoresChart categoryScores={categoryScores} />);

  expect(screen.getByText("Code naming conventions / Code Structure")).toBeInTheDocument();
  expect(screen.getByText("90%")).toBeInTheDocument();
  expect(screen.getByText("Reliability, Security & Observability")).toBeInTheDocument();
  expect(screen.getByText("75.5%")).toBeInTheDocument();
});

test("renders a Pending label instead of a percentage for unscored categories", () => {
  render(<CategoryScoresChart categoryScores={categoryScores} />);

  expect(screen.getByText("Delivery Discipline & Architecture")).toBeInTheDocument();
  expect(screen.getByText("Pending…")).toBeInTheDocument();
});

test("renders one row per category in a mixed scored/pending list", () => {
  render(<CategoryScoresChart categoryScores={categoryScores} />);

  expect(screen.getAllByText(/^(Pending…|[\d.]+%)$/)).toHaveLength(3);
});
