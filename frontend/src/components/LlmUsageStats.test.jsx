import { render, screen } from "@testing-library/react";
import LlmUsageStats from "./LlmUsageStats";

test("shows the call count and summed total tokens", () => {
  const promptLog = [
    {
      label: "Code naming conventions / Code Structure",
      prompt_text: "...",
      tokens: { prompt_tokens: 500, completion_tokens: 40, total_tokens: 540, cached_tokens: null },
    },
    {
      label: "General remarks",
      prompt_text: "...",
      tokens: { prompt_tokens: 100, completion_tokens: 20, total_tokens: 120, cached_tokens: null },
    },
  ];
  render(<LlmUsageStats promptLog={promptLog} />);
  expect(screen.getByText("2 LLM calls")).toBeInTheDocument();
  expect(screen.getByText("660 tokens used")).toBeInTheDocument();
});

test("shows a zero state for an empty prompt log", () => {
  render(<LlmUsageStats promptLog={[]} />);
  expect(screen.getByText("0 LLM calls")).toBeInTheDocument();
  expect(screen.getByText("0 tokens used")).toBeInTheDocument();
});
