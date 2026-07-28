import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PromptDebugLog from "./PromptDebugLog";

const promptLog = [
  {
    label: "Code naming conventions / Code Structure",
    prompt_text: "Score the following...",
    tokens: { prompt_tokens: 500, completion_tokens: 40, total_tokens: 540, cached_tokens: null },
  },
  {
    label: "General remarks",
    prompt_text: "Given per-criterion scores...",
    tokens: { prompt_tokens: 100, completion_tokens: 20, total_tokens: 120, cached_tokens: 64 },
  },
];

test("code context is collapsed by default", () => {
  render(<PromptDebugLog codeContext="class MainActivity {}" promptLog={promptLog} />);
  expect(screen.queryByText("class MainActivity {}")).not.toBeInTheDocument();
  expect(screen.getByText(/show source code sent to the model/i)).toBeInTheDocument();
});

test("expands the code context on click", async () => {
  const user = userEvent.setup();
  render(<PromptDebugLog codeContext="class MainActivity {}" promptLog={promptLog} />);
  await user.click(screen.getByText(/show source code sent to the model/i));
  expect(screen.getByText("class MainActivity {}")).toBeInTheDocument();
});

test("renders every prompt log entry with its label, text, and token summary", () => {
  render(<PromptDebugLog codeContext="" promptLog={promptLog} />);
  expect(screen.getByText("Code naming conventions / Code Structure")).toBeInTheDocument();
  expect(screen.getByText("Score the following...")).toBeInTheDocument();
  expect(screen.getByText("500 prompt · 40 completion · 540 total")).toBeInTheDocument();
  expect(screen.getByText("General remarks")).toBeInTheDocument();
  expect(screen.getByText("100 prompt · 20 completion · 120 total · 64 cached")).toBeInTheDocument();
});
