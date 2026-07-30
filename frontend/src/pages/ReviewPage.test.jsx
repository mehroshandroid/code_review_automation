import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import ReviewPage from "./ReviewPage";

jest.mock("./AndroidReviewFlow", () => (props) => <div data-testid="real-flow">{props.platform.label}</div>);
jest.mock("./PlaceholderReviewFlow", () => (props) => <div data-testid="placeholder-flow">{props.platform.label}</div>);

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/review/:platform" element={<ReviewPage />} />
        <Route path="/" element={<div>home</div>} />
      </Routes>
    </MemoryRouter>
  );
}

test("routes an available platform (Android) to the real review flow", () => {
  renderAt("/review/android");
  expect(screen.getByTestId("real-flow")).toHaveTextContent("Android");
});

test("routes an available non-Android platform (iOS) to the real review flow too", () => {
  renderAt("/review/ios");
  expect(screen.getByTestId("real-flow")).toHaveTextContent("iOS");
});

test("routes an unavailable platform to the placeholder", () => {
  renderAt("/review/dotnet");
  expect(screen.getByTestId("placeholder-flow")).toHaveTextContent(".NET");
});

test("redirects to home for an unknown platform id", () => {
  renderAt("/review/nonexistent");
  expect(screen.getByText("home")).toBeInTheDocument();
});
