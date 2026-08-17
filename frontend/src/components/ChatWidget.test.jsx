import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ChatWidget from "./ChatWidget";
import { sendChatMessage } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  sendChatMessage: jest.fn(),
}));

beforeEach(() => {
  jest.resetAllMocks();
});

function renderWidget() {
  return render(
    <MemoryRouter>
      <ChatWidget />
    </MemoryRouter>
  );
}

test("starts collapsed, showing only the open button", () => {
  renderWidget();
  expect(screen.getByRole("button", { name: /open review insights chat/i })).toBeInTheDocument();
  expect(screen.queryByLabelText(/ask a question/i)).not.toBeInTheDocument();
});

test("clicking the bubble opens the panel with the input visible", async () => {
  const user = userEvent.setup();
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));

  expect(screen.getByLabelText(/ask a question/i)).toBeInTheDocument();
});

test("clicking close collapses the panel again", async () => {
  const user = userEvent.setup();
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  await user.click(screen.getByRole("button", { name: /close chat/i }));

  expect(screen.queryByLabelText(/ask a question/i)).not.toBeInTheDocument();
});

test("sending a message calls sendChatMessage and renders the answer", async () => {
  const user = userEvent.setup();
  sendChatMessage.mockResolvedValue({ answer: "It commonly failed on naming conventions.", sources: [] });
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  await user.type(screen.getByLabelText(/ask a question/i), "what was the reason for .NET low score");
  await user.click(screen.getByRole("button", { name: /send/i }));

  expect(await screen.findByText("It commonly failed on naming conventions.")).toBeInTheDocument();
  expect(sendChatMessage).toHaveBeenCalledWith("what was the reason for .NET low score", []);
});

test("clears the input after sending", async () => {
  const user = userEvent.setup();
  sendChatMessage.mockResolvedValue({ answer: "ok", sources: [] });
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  const input = screen.getByLabelText(/ask a question/i);
  await user.type(input, "question");
  await user.click(screen.getByRole("button", { name: /send/i }));

  await waitFor(() => expect(input).toHaveValue(""));
});

test("sends accumulated history on the second message", async () => {
  const user = userEvent.setup();
  sendChatMessage.mockResolvedValueOnce({ answer: "First answer", sources: [] });
  sendChatMessage.mockResolvedValueOnce({ answer: "Second answer", sources: [] });
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  await user.type(screen.getByLabelText(/ask a question/i), "first question");
  await user.click(screen.getByRole("button", { name: /send/i }));
  await screen.findByText("First answer");

  await user.type(screen.getByLabelText(/ask a question/i), "second question");
  await user.click(screen.getByRole("button", { name: /send/i }));

  await waitFor(() => expect(sendChatMessage).toHaveBeenLastCalledWith("second question", [
    { role: "user", content: "first question" },
    { role: "assistant", content: "First answer" },
  ]));
});

test("renders a sources table with project names when the answer has sources", async () => {
  const user = userEvent.setup();
  sendChatMessage.mockResolvedValue({
    answer: "Two reviews scored low.",
    sources: [
      { id: "r1", project_name: "Moove", platform: ".NET", total_score_pct: 60, created_at: "2025-06-01T00:00:00Z" },
      { id: "r2", project_name: "Payments", platform: ".NET", total_score_pct: 55, created_at: "2025-07-01T00:00:00Z" },
    ],
  });
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  await user.type(screen.getByLabelText(/ask a question/i), "question");
  await user.click(screen.getByRole("button", { name: /send/i }));

  expect(await screen.findByText("Moove")).toBeInTheDocument();
  expect(screen.getByText("Payments")).toBeInTheDocument();
});

test("shows an error message when sendChatMessage fails", async () => {
  const user = userEvent.setup();
  sendChatMessage.mockRejectedValue(new Error("network error"));
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  await user.type(screen.getByLabelText(/ask a question/i), "question");
  await user.click(screen.getByRole("button", { name: /send/i }));

  expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
});

test("disables send while a response is loading, re-enables once loading finishes and text is entered", async () => {
  const user = userEvent.setup();
  let resolvePromise;
  sendChatMessage.mockReturnValue(new Promise((resolve) => { resolvePromise = resolve; }));
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  const input = screen.getByLabelText(/ask a question/i);
  await user.type(input, "question");
  await user.click(screen.getByRole("button", { name: /send/i }));

  expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  resolvePromise({ answer: "done", sources: [] });
  await screen.findByText("done");

  expect(input).toBeEnabled();
  await user.type(input, "another question");
  expect(screen.getByRole("button", { name: /send/i })).toBeEnabled();
});

test("does not send an empty or whitespace-only message", async () => {
  const user = userEvent.setup();
  renderWidget();

  await user.click(screen.getByRole("button", { name: /open review insights chat/i }));
  expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();

  await user.type(screen.getByLabelText(/ask a question/i), "   ");
  expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  expect(sendChatMessage).not.toHaveBeenCalled();
});
