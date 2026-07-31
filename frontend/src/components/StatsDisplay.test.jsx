import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StatsDisplay from "./StatsDisplay";

const baseProps = {
  totalScorePct: 78,
  warnings: [],
  secretsFound: [],
  lintIssues: [],
  stats: {},
  downloadUrl: "/api/reviews/abc-123/download",
  onReset: () => {},
};

test("shows timing breakdown for each provided stat, formatted as seconds, inside the performance breakdown modal", async () => {
  const user = userEvent.setup();
  render(
    <StatsDisplay
      {...baseProps}
      stats={{ ingest_time_ms: 800, analysis_time_ms: 2100, compile_time_ms: 5200, scoring_time_ms: 11400, generation_time_ms: 600, total_time_ms: 14900 }}
    />
  );

  expect(screen.queryByText("0.8s")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /performance breakdown/i }));

  expect(screen.getByText("0.8s")).toBeInTheDocument();
  expect(screen.getByText("14.9s")).toBeInTheDocument();
  expect(screen.getByText("Compiling & Lint (Gradle)")).toBeInTheDocument();
  expect(screen.getByText("5.2s")).toBeInTheDocument();
});

test("closes the performance breakdown modal when Close is clicked", async () => {
  const user = userEvent.setup();
  render(<StatsDisplay {...baseProps} stats={{ total_time_ms: 500 }} />);

  await user.click(screen.getByRole("button", { name: /performance breakdown/i }));
  expect(screen.getByText("Total")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /^close$/i }));
  expect(screen.queryByText("Total")).not.toBeInTheDocument();
});

test("shows the total score tag when totalScorePct is present", () => {
  render(<StatsDisplay {...baseProps} totalScorePct={78} />);
  expect(screen.getByText("Total 78%")).toBeInTheDocument();
});

test("omits the total score tag when totalScorePct is null", () => {
  render(<StatsDisplay {...baseProps} totalScorePct={null} />);
  expect(screen.queryByText(/^Total/)).not.toBeInTheDocument();
});

test("shows warning and secret counts as outline tags", () => {
  render(
    <StatsDisplay
      {...baseProps}
      warnings={["Missing AndroidManifest.xml"]}
      secretsFound={[{ file: "Constants.java", line: 42, pattern: "api_key" }]}
    />
  );
  expect(screen.getByText("1 warnings")).toBeInTheDocument();
  expect(screen.getByText("1 secrets")).toBeInTheDocument();
});

test("renders the warnings and secrets tags as plain, non-clickable spans when both counts are 0", () => {
  render(<StatsDisplay {...baseProps} />);
  expect(screen.getByText("0 warnings").tagName).toBe("SPAN");
  expect(screen.getByText("0 secrets").tagName).toBe("SPAN");
});

test("clicking the warnings tag opens a dialog listing every warning", async () => {
  const user = userEvent.setup();
  render(
    <StatsDisplay
      {...baseProps}
      warnings={["Missing AndroidManifest.xml", "Unused dependency: guava"]}
    />
  );

  expect(screen.queryByText("Missing AndroidManifest.xml")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "2 warnings" }));

  expect(screen.getByText("Missing AndroidManifest.xml")).toBeInTheDocument();
  expect(screen.getByText("Unused dependency: guava")).toBeInTheDocument();
});

test("combines structural warnings and lint issues into one warnings count and popup", async () => {
  const user = userEvent.setup();
  render(
    <StatsDisplay
      {...baseProps}
      warnings={["Missing AndroidManifest.xml"]}
      lintIssues={[{ severity: "Warning", message: "Possible null reference", file: "Program.cs", line: 15 }]}
    />
  );

  // 1 structural warning + 1 lint issue -- shown as one combined count, not two separate tags.
  await user.click(screen.getByRole("button", { name: "2 warnings" }));

  expect(screen.getByText("Missing AndroidManifest.xml")).toBeInTheDocument();
  expect(screen.getByText("Program.cs:15 (Warning): Possible null reference")).toBeInTheDocument();
});

test("counts only lint issues toward the warnings tag when there are no structural warnings", async () => {
  const user = userEvent.setup();
  render(
    <StatsDisplay
      {...baseProps}
      lintIssues={[
        { severity: "Warning", message: "Possible null reference", file: "Program.cs", line: 15 },
        { severity: "Error", message: "Unresolved reference", file: "Startup.cs", line: 3 },
      ]}
    />
  );

  expect(screen.getByRole("button", { name: "2 warnings" })).toBeInTheDocument();
});

test("renders every item in a large warnings list -- the dialog scrolls, it doesn't truncate", async () => {
  const user = userEvent.setup();
  const manyWarnings = Array.from({ length: 250 }, (_, index) => `Warning #${index + 1}`);
  render(<StatsDisplay {...baseProps} warnings={manyWarnings} />);

  await user.click(screen.getByRole("button", { name: "250 warnings" }));

  expect(screen.getByText("Warning #1")).toBeInTheDocument();
  expect(screen.getByText("Warning #250")).toBeInTheDocument();
});

test("clicking the secrets tag opens a dialog listing every secret as file:line (pattern)", async () => {
  const user = userEvent.setup();
  render(
    <StatsDisplay
      {...baseProps}
      secretsFound={[{ file: "Constants.java", line: 42, pattern: "api_key" }]}
    />
  );

  await user.click(screen.getByRole("button", { name: "1 secrets" }));

  expect(screen.getByText("Constants.java:42 (api_key)")).toBeInTheDocument();
});

test("closes the warnings dialog when Close is clicked", async () => {
  const user = userEvent.setup();
  render(<StatsDisplay {...baseProps} warnings={["Missing AndroidManifest.xml"]} />);

  await user.click(screen.getByRole("button", { name: "1 warnings" }));
  expect(screen.getByText("Missing AndroidManifest.xml")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /^close$/i }));
  expect(screen.queryByText("Missing AndroidManifest.xml")).not.toBeInTheDocument();
});

test("only one dialog is open at a time -- opening secrets while warnings is open replaces it", async () => {
  const user = userEvent.setup();
  render(
    <StatsDisplay
      {...baseProps}
      warnings={["Missing AndroidManifest.xml"]}
      secretsFound={[{ file: "Constants.java", line: 42, pattern: "api_key" }]}
    />
  );

  await user.click(screen.getByRole("button", { name: "1 warnings" }));
  expect(screen.getByText("Missing AndroidManifest.xml")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "1 secrets" }));
  expect(screen.queryByText("Missing AndroidManifest.xml")).not.toBeInTheDocument();
  expect(screen.getByText("Constants.java:42 (api_key)")).toBeInTheDocument();
});

test("renders a download link pointing at the constructed download URL", () => {
  render(<StatsDisplay {...baseProps} />);
  const link = screen.getByRole("link", { name: /download populated workbook/i });
  expect(link).toHaveAttribute("href", "http://localhost:8000/api/reviews/abc-123/download");
  expect(link).toHaveAttribute("download");
});

test("calls onReset when Start new review is clicked", async () => {
  const user = userEvent.setup();
  const onReset = jest.fn();
  render(<StatsDisplay {...baseProps} onReset={onReset} />);
  await user.click(screen.getByRole("button", { name: /start new review/i }));
  expect(onReset).toHaveBeenCalled();
});
