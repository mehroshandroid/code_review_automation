import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import TopNav from "./TopNav";

test("renders the brand and Home link, both pointing at /", () => {
  render(
    <MemoryRouter>
      <TopNav />
    </MemoryRouter>
  );
  expect(screen.getByText("Code Review Automation").closest("a")).toHaveAttribute("href", "/");
  expect(screen.getByText("← Home")).toHaveAttribute("href", "/");
});
