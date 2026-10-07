import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import MultiSelect from "./MultiSelect";

const options = [{ value: "a", label: "Alice" }, { value: "b", label: "Bob" }, { value: "c", label: "Cara" }];

function Harness({ initial = [] }) {
  const [values, setValues] = useState(initial);
  return <MultiSelect ariaLabel="Managers" options={options} values={values} onChange={setValues} />;
}

test("shows chips for selected values and removes them", async () => {
  const user = userEvent.setup();
  render(<Harness initial={["a"]} />);
  expect(screen.getByText("Alice")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Remove Alice" }));
  expect(screen.queryByRole("button", { name: "Remove Alice" })).not.toBeInTheDocument();
});

test("filters and toggles options with checkboxes", async () => {
  const user = userEvent.setup();
  render(<Harness />);
  await user.click(screen.getByRole("button", { name: "Managers" }));
  await user.type(screen.getByRole("textbox", { name: "Search Managers" }), "bo");
  expect(screen.queryByRole("checkbox", { name: "Alice" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("checkbox", { name: "Bob" }));
  expect(screen.getByRole("button", { name: "Remove Bob" })).toBeInTheDocument();
});

test("the options panel is laid out in normal flow so a dialog grows to fit it", async () => {
  // An absolutely-positioned panel takes no space, so inside a dialog body
  // with overflow-y: auto it was clipped instead of expanding the dialog.
  const user = userEvent.setup();
  render(<Harness />);
  await user.click(screen.getByRole("button", { name: "Managers" }));
  const panel = screen.getByRole("group", { name: "Managers options" });
  expect(panel).not.toHaveStyle({ position: "absolute" });
});
