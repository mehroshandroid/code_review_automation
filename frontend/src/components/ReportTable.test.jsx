import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

test("renders plain text, not inputs, when editable is false (the default)", () => {
  render(<ReportTable categoryScores={categoryScores} />);
  expect(screen.queryByLabelText(/score for 1\.1/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/remark for 1\.1/i)).not.toBeInTheDocument();
});

test("renders a score select and remark textarea per sub-criterion when editable", () => {
  render(<ReportTable categoryScores={categoryScores} editable onChangeScore={jest.fn()} onChangeRemark={jest.fn()} />);

  expect(screen.getByLabelText(/score for 1\.1/i)).toHaveValue("1");
  expect(screen.getByLabelText(/score for 1\.4/i)).toHaveValue("0");
  expect(screen.getByLabelText(/score for 1\.5/i)).toHaveValue("");
  expect(screen.getByLabelText(/remark for 1\.1/i)).toHaveValue("Looks good.");
});

test("changing the score select calls onChangeScore with the category id, sub id, and numeric/null score", async () => {
  const user = userEvent.setup();
  const onChangeScore = jest.fn();
  render(<ReportTable categoryScores={categoryScores} editable onChangeScore={onChangeScore} onChangeRemark={jest.fn()} />);

  await user.selectOptions(screen.getByLabelText(/score for 1\.5/i), "1");

  expect(onChangeScore).toHaveBeenCalledWith("1", "1.5", 1);
});

test("editing the remark textarea calls onChangeRemark with the category id, sub id, and new text", async () => {
  const user = userEvent.setup();
  const onChangeRemark = jest.fn();
  render(<ReportTable categoryScores={categoryScores} editable onChangeScore={jest.fn()} onChangeRemark={onChangeRemark} />);

  await user.type(screen.getByLabelText(/remark for 1\.5/i), "x");

  expect(onChangeRemark).toHaveBeenCalledWith("1", "1.5", "x");
});
