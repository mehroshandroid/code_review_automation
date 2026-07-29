import { render, screen } from "@testing-library/react";
import ReportTable from "./ReportTable";

const categoryScores = [
  {
    id: "1",
    name: "Code naming conventions / Code Structure",
    percent_points: 83.3,
    sub_criteria: [
      { id: "1.1", description: "Clear and consistent naming conventions", score: 1, remark: "Looks good." },
      { id: "1.4", description: "No compile-time warnings", score: 0, remark: "2 Lint warning(s)/error(s) found." },
      { id: "1.5", description: "No unused dependencies", score: null, remark: null },
    ],
  },
  {
    id: "2",
    name: "Reliability, Security & Observability",
    percent_points: null,
    sub_criteria: [
      { id: "2.1", description: "Proper exception handling", score: null, remark: null },
    ],
  },
];

test("renders a section per category with its name and percent", () => {
  render(<ReportTable categoryScores={categoryScores} />);
  expect(screen.getByText("Code naming conventions / Code Structure")).toBeInTheDocument();
  expect(screen.getByText("83.3%")).toBeInTheDocument();
  expect(screen.getByText("Reliability, Security & Observability")).toBeInTheDocument();
});

test("omits the percent tag when percent_points is null", () => {
  render(<ReportTable categoryScores={categoryScores} />);
  expect(screen.queryByText("null%")).not.toBeInTheDocument();
});

test("renders one row per sub-criterion with clause id, description and remark", () => {
  render(<ReportTable categoryScores={categoryScores} />);
  expect(screen.getByText("1.1")).toBeInTheDocument();
  expect(screen.getByText("Clear and consistent naming conventions")).toBeInTheDocument();
  expect(screen.getByText("Looks good.")).toBeInTheDocument();
});

test("maps score 1/0/null to Meets/Fails/Not evaluated labels", () => {
  render(<ReportTable categoryScores={categoryScores} />);
  expect(screen.getByText("Meets")).toBeInTheDocument();
  expect(screen.getByText("Fails")).toBeInTheDocument();
  expect(screen.getAllByText("Not evaluated").length).toBe(2);
});
