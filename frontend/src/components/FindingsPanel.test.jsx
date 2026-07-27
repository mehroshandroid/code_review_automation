import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FindingsPanel from "./FindingsPanel";

test("renders nothing when there are no findings at all", () => {
  const { container } = render(<FindingsPanel warnings={[]} testCoverage={null} secretsFound={[]} />);
  expect(container.firstChild).toBeNull();
});

test("shows all three cards once any finding is present, with placeholders for absent ones", () => {
  render(<FindingsPanel warnings={["Missing AndroidManifest.xml"]} testCoverage={null} secretsFound={[]} />);

  expect(screen.getByText("Warnings")).toBeInTheDocument();
  expect(screen.getByText("Test coverage")).toBeInTheDocument();
  expect(screen.getByText("No coverage report found.")).toBeInTheDocument();
  expect(screen.getByText("Secrets found")).toBeInTheDocument();
  expect(screen.getByText("No secrets found.")).toBeInTheDocument();
});

test("shows the coverage percentage and secret summary when present", () => {
  render(
    <FindingsPanel
      warnings={[]}
      testCoverage={82.5}
      secretsFound={[{ file: "Constants.java", line: 42, pattern: "api_key" }]}
    />
  );
  expect(screen.getByText("82.5%")).toBeInTheDocument();
  expect(screen.getByText("1 possible secret found")).toBeInTheDocument();
});

test("expands the warnings card to list every warning on click", async () => {
  const user = userEvent.setup();
  render(<FindingsPanel warnings={["Missing AndroidManifest.xml", "Outdated Gradle plugin"]} testCoverage={null} secretsFound={[]} />);

  expect(screen.queryByText("Missing AndroidManifest.xml")).not.toBeInTheDocument();
  await user.click(screen.getByText("2 issues found"));
  expect(screen.getByText("Missing AndroidManifest.xml")).toBeInTheDocument();
  expect(screen.getByText("Outdated Gradle plugin")).toBeInTheDocument();
});

test("expands the secrets card to list file:line (pattern) for every secret on click", async () => {
  const user = userEvent.setup();
  render(
    <FindingsPanel
      warnings={[]}
      testCoverage={null}
      secretsFound={[{ file: "Constants.java", line: 42, pattern: "api_key" }]}
    />
  );

  await user.click(screen.getByText("1 possible secret found"));
  expect(screen.getByText("Constants.java:42 (api_key)")).toBeInTheDocument();
});
