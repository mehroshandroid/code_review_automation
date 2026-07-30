import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AppRoutes from "./AppRoutes";

function renderAt(initialPath) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AppRoutes />
    </MemoryRouter>
  );
}

test("renders the home page's platform cards and LLM toggle at /", () => {
  renderAt("/");
  expect(screen.getByRole("link", { name: /android/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Azure OpenAI" })).toBeInTheDocument();
});

test("renders the Android review flow at /review/android", () => {
  renderAt("/review/android");
  expect(screen.getByRole("button", { name: /start review/i })).toBeInTheDocument();
});

test("renders the real review flow at /review/ios now that iOS is available", () => {
  renderAt("/review/ios");
  expect(screen.getByRole("heading", { name: "iOS Code Review Automation" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /start review/i })).toBeInTheDocument();
});

test("renders a placeholder banner for a not-yet-available platform", () => {
  renderAt("/review/dotnet");
  expect(screen.getByText(".NET support is on the way")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Coming soon" })).toBeDisabled();
});

test("redirects to / for an unknown platform id", () => {
  renderAt("/review/nonsense");
  expect(screen.getByRole("link", { name: /android/i })).toBeInTheDocument();
});
