import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import TopNav from "./TopNav";

test("renders the brand and a Home link, both pointing at /", () => {
  render(
    <MemoryRouter>
      <TopNav />
    </MemoryRouter>
  );
  const links = screen.getAllByRole("link");
  expect(links).toHaveLength(2);
  links.forEach((link) => expect(link).toHaveAttribute("href", "/"));
  expect(screen.getByText("Code Review Automation")).toBeInTheDocument();
  expect(screen.getByText("← Home")).toBeInTheDocument();
});
