import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SearchableSelect from "./SearchableSelect";

const options = [
  { value: null, label: "All platforms" },
  { value: "Android", label: "Android" },
  { value: ".NET", label: ".NET" },
  { value: "iOS", label: "iOS" },
];

test("shows the placeholder when nothing is selected", () => {
  render(<SearchableSelect ariaLabel="Platform" options={options} value={undefined} onChange={jest.fn()} placeholder="Choose…" />);
  expect(screen.getByRole("button", { name: "Platform" })).toHaveTextContent("Choose…");
});

test("shows the selected option's label", () => {
  render(<SearchableSelect ariaLabel="Platform" options={options} value=".NET" onChange={jest.fn()} />);
  expect(screen.getByRole("button", { name: "Platform" })).toHaveTextContent(".NET");
});

test("clicking the trigger opens the option list", async () => {
  const user = userEvent.setup();
  render(<SearchableSelect ariaLabel="Platform" options={options} value={null} onChange={jest.fn()} />);

  await user.click(screen.getByRole("button", { name: "Platform" }));

  expect(screen.getByRole("button", { name: "Android" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: ".NET" })).toBeInTheDocument();
});

test("typing in the search box filters the option list", async () => {
  const user = userEvent.setup();
  render(<SearchableSelect ariaLabel="Platform" options={options} value={null} onChange={jest.fn()} />);

  await user.click(screen.getByRole("button", { name: "Platform" }));
  await user.type(screen.getByLabelText(/search platform/i), "and");

  expect(screen.getByRole("button", { name: "Android" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: ".NET" })).not.toBeInTheDocument();
});

test("shows a 'No matches' message when the search filters everything out", async () => {
  const user = userEvent.setup();
  render(<SearchableSelect ariaLabel="Platform" options={options} value={null} onChange={jest.fn()} />);

  await user.click(screen.getByRole("button", { name: "Platform" }));
  await user.type(screen.getByLabelText(/search platform/i), "zzz");

  expect(screen.getByText(/no matches/i)).toBeInTheDocument();
});

test("selecting an option calls onChange with its value and closes the panel", async () => {
  const user = userEvent.setup();
  const onChange = jest.fn();
  render(<SearchableSelect ariaLabel="Platform" options={options} value={null} onChange={onChange} />);

  await user.click(screen.getByRole("button", { name: "Platform" }));
  await user.click(screen.getByRole("button", { name: "Android" }));

  expect(onChange).toHaveBeenCalledWith("Android");
  expect(screen.queryByLabelText(/search platform/i)).not.toBeInTheDocument();
});

test("clicking outside the component closes the panel", async () => {
  const user = userEvent.setup();
  render(
    <div>
      <SearchableSelect ariaLabel="Platform" options={options} value={null} onChange={jest.fn()} />
      <button type="button">Outside</button>
    </div>
  );

  await user.click(screen.getByRole("button", { name: "Platform" }));
  expect(screen.getByLabelText(/search platform/i)).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Outside" }));

  expect(screen.queryByLabelText(/search platform/i)).not.toBeInTheDocument();
});

test("renders the add-new action when onAddNew is provided, and calls it on click", async () => {
  const user = userEvent.setup();
  const onAddNew = jest.fn();
  render(
    <SearchableSelect
      ariaLabel="Project" options={options} value={null} onChange={jest.fn()}
      onAddNew={onAddNew} addNewLabel="+ Add new project"
    />
  );

  await user.click(screen.getByRole("button", { name: "Project" }));
  await user.click(screen.getByRole("button", { name: "+ Add new project" }));

  expect(onAddNew).toHaveBeenCalled();
});

test("does not render an add-new action when onAddNew is omitted", async () => {
  const user = userEvent.setup();
  render(<SearchableSelect ariaLabel="Platform" options={options} value={null} onChange={jest.fn()} />);

  await user.click(screen.getByRole("button", { name: "Platform" }));

  expect(screen.queryByText(/add new/i)).not.toBeInTheDocument();
});
