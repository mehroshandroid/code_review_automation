import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FindingsPanel from "./FindingsPanel";

test("renders nothing when there are no findings at all", () => {
  const { container } = render(
    <FindingsPanel warnings={[]} testCoverage={null} secretsFound={[]} lintIssues={[]} compileStatus={null} />
  );
  expect(container.firstChild).toBeNull();
});

test("shows all four cards once any finding is present, with placeholders for absent ones", () => {
  render(
    <FindingsPanel
      warnings={["Missing AndroidManifest.xml"]}
      testCoverage={null}
      secretsFound={[]}
      lintIssues={[]}
      compileStatus={null}
    />
  );

  expect(screen.getByText("Warnings")).toBeInTheDocument();
  expect(screen.getByText("Test coverage")).toBeInTheDocument();
  expect(screen.getByText("No coverage report found.")).toBeInTheDocument();
  expect(screen.getByText("Secrets found")).toBeInTheDocument();
  expect(screen.getByText("No secrets found.")).toBeInTheDocument();
  expect(screen.getByText("Lint issues")).toBeInTheDocument();
  expect(screen.getByText("Not yet checked.")).toBeInTheDocument();
});

test("shows the coverage percentage and secret summary when present", () => {
  render(
    <FindingsPanel
      warnings={[]}
      testCoverage={82.5}
      secretsFound={[{ file: "Constants.java", line: 42, pattern: "api_key" }]}
      lintIssues={[]}
      compileStatus={null}
    />
  );
  expect(screen.getByText("82.5%")).toBeInTheDocument();
  expect(screen.getByText("1 possible secret found")).toBeInTheDocument();
});

test("expands the warnings card to list every warning on click", async () => {
  const user = userEvent.setup();
  render(
    <FindingsPanel
      warnings={["Missing AndroidManifest.xml", "Outdated Gradle plugin"]}
      testCoverage={null}
      secretsFound={[]}
      lintIssues={[]}
      compileStatus={null}
    />
  );

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
      lintIssues={[]}
      compileStatus={null}
    />
  );

  await user.click(screen.getByText("1 possible secret found"));
  expect(screen.getByText("Constants.java:42 (api_key)")).toBeInTheDocument();
});

test("shows a clean caption when the compile check succeeds with no issues", () => {
  render(
    <FindingsPanel warnings={[]} testCoverage={null} secretsFound={[]} lintIssues={[]} compileStatus="ok" />
  );
  expect(screen.getByText("No Lint warnings or errors found.")).toBeInTheDocument();
});

test("expands the Lint issues card to list every issue on click", async () => {
  const user = userEvent.setup();
  render(
    <FindingsPanel
      warnings={[]}
      testCoverage={null}
      secretsFound={[]}
      lintIssues={[{ file: "Main.java", line: 10, severity: "Warning", message: "Unused import" }]}
      compileStatus="ok"
    />
  );

  expect(screen.queryByText("Main.java:10 (Warning): Unused import")).not.toBeInTheDocument();
  await user.click(screen.getByText("1 issue found"));
  expect(screen.getByText("Main.java:10 (Warning): Unused import")).toBeInTheDocument();
});

test("shows a build-failed caption when the project could not compile", () => {
  render(
    <FindingsPanel warnings={[]} testCoverage={null} secretsFound={[]} lintIssues={[]} compileStatus="build_failed" />
  );
  expect(screen.getByText("Project failed to compile.")).toBeInTheDocument();
});

test("shows an unavailable caption when the compile check couldn't run", () => {
  render(
    <FindingsPanel warnings={[]} testCoverage={null} secretsFound={[]} lintIssues={[]} compileStatus="unavailable" />
  );
  expect(screen.getByText("Compile check unavailable.")).toBeInTheDocument();
});

test("shows a static-analysis caption when the compiler check was skipped", () => {
  render(
    <FindingsPanel warnings={[]} testCoverage={null} secretsFound={[]} lintIssues={[]} compileStatus="skipped" />
  );
  expect(screen.getByText("Static analysis mode selected — clause 1.4 scored by AI.")).toBeInTheDocument();
});
