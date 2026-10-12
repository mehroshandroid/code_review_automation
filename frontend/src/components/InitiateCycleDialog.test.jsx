import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import InitiateCycleDialog from "./InitiateCycleDialog";
import { getReviewers, initiateCycle } from "../services/api";

jest.mock("../services/api", () => ({ ...jest.requireActual("../services/api"), getReviewers: jest.fn(), initiateCycle: jest.fn() }));

const project = { id: "p1", name: "Alpha", platforms: ["Android", "iOS"] };
const entry = { quarter: 4, status: "not_started" };

beforeEach(() => {
  jest.resetAllMocks();
  getReviewers.mockResolvedValue([{ id: "r1", email: "rae@example.com", name: "Rae" }, { id: "r2", email: "sam@example.com", name: null }]);
});

test("requires a reviewer per platform, then posts assignments", async () => {
  const user = userEvent.setup();
  const onInitiated = jest.fn();
  initiateCycle.mockResolvedValue({ quarter: 4, status: "in_progress" });
  render(<InitiateCycleDialog project={project} year={2026} entry={entry} onInitiated={onInitiated} onClose={jest.fn()} />);
  expect(screen.getByText("Initiate Q4 2026 review — Alpha")).toBeInTheDocument();
  const submit = screen.getByRole("button", { name: "Initiate" });
  await screen.findAllByRole("option", { name: "Rae" });
  expect(submit).toBeDisabled();
  await user.selectOptions(screen.getByLabelText("Reviewer for Android"), "r1");
  expect(submit).toBeDisabled();
  await user.selectOptions(screen.getByLabelText("Reviewer for iOS"), "r2");
  await user.click(submit);
  await waitFor(() => expect(initiateCycle).toHaveBeenCalledWith("p1", {
    year: 2026, quarter: 4,
    assignments: [{ platform: "Android", reviewer_id: "r1" }, { platform: "iOS", reviewer_id: "r2" }],
  }));
  expect(onInitiated).toHaveBeenCalledWith({ quarter: 4, status: "in_progress" });
});

test("shows the API error", async () => {
  const user = userEvent.setup();
  initiateCycle.mockRejectedValue({ response: { data: { detail: "This quarter's review has already been initiated." } } });
  render(<InitiateCycleDialog project={{ ...project, platforms: ["Android"] }} year={2026} entry={entry} onInitiated={jest.fn()} onClose={jest.fn()} />);
  await screen.findByRole("option", { name: "Rae" });
  await user.selectOptions(screen.getByLabelText("Reviewer for Android"), "r1");
  await user.click(screen.getByRole("button", { name: "Initiate" }));
  expect(await screen.findByText("This quarter's review has already been initiated.")).toBeInTheDocument();
});

test("only ticked platforms need a reviewer", async () => {
  const user = userEvent.setup();
  initiateCycle.mockResolvedValue({ quarter: 4, status: "in_progress" });
  render(<InitiateCycleDialog project={project} year={2026} entry={entry} onInitiated={jest.fn()} onClose={jest.fn()} />);
  await screen.findAllByRole("option", { name: "Rae" });
  await user.click(screen.getByLabelText("Start iOS"));
  expect(screen.queryByLabelText("Reviewer for iOS")).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Reviewer for Android"), "r1");
  await user.click(screen.getByRole("button", { name: "Initiate" }));
  await waitFor(() => expect(initiateCycle).toHaveBeenCalledWith("p1", {
    year: 2026, quarter: 4, assignments: [{ platform: "Android", reviewer_id: "r1" }],
  }));
});

test("nothing ticked can't be submitted", async () => {
  const user = userEvent.setup();
  render(<InitiateCycleDialog project={project} year={2026} entry={entry} onInitiated={jest.fn()} onClose={jest.fn()} />);
  await screen.findAllByRole("option", { name: "Rae" });
  await user.click(screen.getByLabelText("Start Android"));
  await user.click(screen.getByLabelText("Start iOS"));
  expect(screen.getByRole("button", { name: "Initiate" })).toBeDisabled();
});

test("add mode offers only the platforms not started yet", async () => {
  const user = userEvent.setup();
  initiateCycle.mockResolvedValue({ quarter: 4, status: "in_progress" });
  const started = { quarter: 4, status: "in_progress", uninitiated_platforms: ["iOS"], cycle: { id: "c1", assignments: [{ platform: "Android" }] } };
  render(<InitiateCycleDialog project={project} year={2026} entry={started} onInitiated={jest.fn()} onClose={jest.fn()} />);
  expect(screen.getByText("Add platforms — Alpha · Q4 2026")).toBeInTheDocument();
  await screen.findAllByRole("option", { name: "Rae" });
  expect(screen.queryByLabelText("Start Android")).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Reviewer for iOS"), "r2");
  await user.click(screen.getByRole("button", { name: "Initiate" }));
  await waitFor(() => expect(initiateCycle).toHaveBeenCalledWith("p1", {
    year: 2026, quarter: 4, assignments: [{ platform: "iOS", reviewer_id: "r2" }],
  }));
});
