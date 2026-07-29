import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StatsDisplay from "./StatsDisplay";

const baseProps = {
  totalScorePct: 78,
  warnings: [],
  secretsFound: [],
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
