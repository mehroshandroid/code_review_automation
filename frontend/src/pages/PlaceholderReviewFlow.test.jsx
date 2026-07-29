import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import PlaceholderReviewFlow from "./PlaceholderReviewFlow";

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
  expect(screen.getByRole("heading", { name: "iOS Code Review Automation" })).toBeInTheDocument();
  expect(screen.getByText("iOS support is on the way")).toBeInTheDocument();
});

test("renders the upload form disabled with a coming-soon button label", () => {
  renderPlaceholder();
  expect(screen.getByLabelText(/android project/i)).toBeDisabled();
  expect(screen.getByRole("button", { name: "Coming soon" })).toBeDisabled();
});

test("renders a Home link back to /", () => {
  renderPlaceholder();
  expect(screen.getByText("← Home")).toHaveAttribute("href", "/");
});
