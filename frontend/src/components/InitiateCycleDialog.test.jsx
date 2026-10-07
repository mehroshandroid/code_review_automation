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
