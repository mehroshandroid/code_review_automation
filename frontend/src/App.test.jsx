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

test("renders the project dashboard at / -- no projects yet since no backend is mocked here", async () => {
  renderAt("/");
  expect(await screen.findByText(/no projects yet/i)).toBeInTheDocument();
  expect(screen.getByText(/create a project to get started/i)).toBeInTheDocument();
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

test("renders the real review flow at /review/dotnet now that .NET is available", () => {
  renderAt("/review/dotnet");
  expect(screen.getByRole("heading", { name: ".NET Code Review Automation" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /start review/i })).toBeInTheDocument();
});

test("renders a placeholder banner for a not-yet-available platform", () => {
  renderAt("/review/web");
  expect(screen.getByText("Web (React) support is on the way")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Coming soon" })).toBeDisabled();
});

test("redirects to / for an unknown platform id", async () => {
  renderAt("/review/nonsense");
  expect(await screen.findByText(/no projects yet/i)).toBeInTheDocument();
});
