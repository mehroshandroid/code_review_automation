import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import PlaceholderReviewFlow from "./PlaceholderReviewFlow";
import { getSampleTemplates } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  getSampleTemplates: jest.fn(),
}));

beforeEach(() => {
  getSampleTemplates.mockReset();
  getSampleTemplates.mockResolvedValue([]);
});

const platform = { id: "ios", label: "iOS", available: false };

function renderPlaceholder() {
  return render(
    <MemoryRouter>
      <PlaceholderReviewFlow platform={platform} />
    </MemoryRouter>
  );
}

test("renders the platform's label in the header and banner", () => {
  renderPlaceholder();
  expect(screen.getByRole("heading", { name: "CodeAssure for iOS" })).toBeInTheDocument();
  expect(screen.getByText("iOS support is on the way")).toBeInTheDocument();
});

test("renders the upload form disabled with a coming-soon button label", () => {
  renderPlaceholder();
  expect(screen.getByLabelText(/android project/i)).toBeDisabled();
  expect(screen.getByRole("button", { name: "Coming soon" })).toBeDisabled();
});

test("renders the shared nav with the brand linking home", () => {
  renderPlaceholder();
  expect(screen.getByRole("link", { name: /codeassure/i })).toHaveAttribute("href", "/");
});
