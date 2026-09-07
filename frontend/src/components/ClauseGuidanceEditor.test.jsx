import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ClauseGuidanceEditor from "./ClauseGuidanceEditor";

const categories = [
  {
    id: "1", name: "Code naming conventions / Code Structure",
    sub_criteria: [
      { id: "1.1", description: "Clear and consistent naming", checklist_text: "Check for camelCase" },
      { id: "1.2", description: "Clean structure and formatting", checklist_text: null },
    ],
  },
];

test("renders each clause's description and pre-fills the org default text", () => {
  render(<ClauseGuidanceEditor categories={categories} onChange={jest.fn()} />);

  expect(screen.getByText(/Clear and consistent naming/)).toBeInTheDocument();
  expect(screen.getByLabelText(/1\.1/)).toHaveValue("Check for camelCase");
  expect(screen.getByLabelText(/1\.2/)).toHaveValue("");
});

test("editing one clause's text reports only that clause as an override", async () => {
  const user = userEvent.setup();
  const onChange = jest.fn();
  render(<ClauseGuidanceEditor categories={categories} onChange={onChange} />);

  await user.type(screen.getByLabelText(/1\.2/), "Check for retry logic");

  expect(onChange).toHaveBeenLastCalledWith({ "1.2": "Check for retry logic" });
});

test("clearing a field that had a default counts as an override", async () => {
  const user = userEvent.setup();
  const onChange = jest.fn();
  render(<ClauseGuidanceEditor categories={categories} onChange={onChange} />);

  await user.clear(screen.getByLabelText(/1\.1/));

  expect(onChange).toHaveBeenLastCalledWith({ "1.1": "" });
});

test("retyping a field back to its original value removes it from the overrides", async () => {
  const user = userEvent.setup();
  const onChange = jest.fn();
  render(<ClauseGuidanceEditor categories={categories} onChange={onChange} />);

  const field = screen.getByLabelText(/1\.1/);
  await user.type(field, "x");
  await user.type(field, "{backspace}");

  expect(onChange).toHaveBeenLastCalledWith({});
});
