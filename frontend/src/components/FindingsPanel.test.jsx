import { render, screen } from "@testing-library/react";
import FindingsPanel from "./FindingsPanel";

test("renders nothing when there are no findings", () => {
  const { container } = render(<FindingsPanel warnings={[]} testCoverage={null} secretsFound={[]} />);
  expect(container.firstChild).toBeNull();
});

test("shows warnings when present", () => {
  render(<FindingsPanel warnings={["Missing AndroidManifest.xml"]} testCoverage={null} secretsFound={[]} />);
  expect(screen.getByText("Missing AndroidManifest.xml")).toBeInTheDocument();
  expect(screen.queryByText(/test coverage/i)).not.toBeInTheDocument();
});

test("shows test coverage and secrets when present", () => {
  render(
    <FindingsPanel
      warnings={[]}
      testCoverage={82.5}
      secretsFound={[{ file: "Constants.java", line: 42, pattern: "api_key" }]}
    />
  );
  expect(screen.getByText(/82\.5%/)).toBeInTheDocument();
  expect(screen.getByText(/Constants\.java:42/)).toBeInTheDocument();
});
