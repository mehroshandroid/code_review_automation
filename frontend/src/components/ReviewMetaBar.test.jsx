import { render, screen } from "@testing-library/react";
import ReviewMetaBar from "./ReviewMetaBar";

test("shows Azure OpenAI, Uploaded ZIP, and Docker compile-check mode as separate chips", () => {
  render(<ReviewMetaBar llmProvider="azure" llmModel={null} source="upload" compileCheckMode="compiler" />);
  expect(screen.getByText("Azure OpenAI")).toHaveClass("tag");
  expect(screen.getByText("Uploaded ZIP")).toHaveClass("tag");
  expect(screen.getByText("Compile-check: Docker")).toHaveClass("tag");
});

test("shows Ollama with its model name", () => {
  render(<ReviewMetaBar llmProvider="ollama" llmModel="qwen2.5-coder:7b" source="upload" compileCheckMode="static" />);
  expect(screen.getByText("Ollama (qwen2.5-coder:7b)")).toBeInTheDocument();
});

test("shows Azure DevOps as the source", () => {
  render(<ReviewMetaBar llmProvider="azure" llmModel={null} source="devops" compileCheckMode="compiler" />);
  expect(screen.getByText("Azure DevOps")).toBeInTheDocument();
});

test("shows Local compile-check mode", () => {
  render(<ReviewMetaBar llmProvider="azure" llmModel={null} source="upload" compileCheckMode="local" />);
  expect(screen.getByText("Compile-check: Local")).toBeInTheDocument();
});

test("shows Static compile-check mode", () => {
  render(<ReviewMetaBar llmProvider="azure" llmModel={null} source="upload" compileCheckMode="static" />);
  expect(screen.getByText("Compile-check: Static")).toBeInTheDocument();
});
