import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChatIcon, SpinnerIcon } from "../icons";
import { sendChatMessage } from "../services/api";

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString();
}

function SourcesTable({ sources, onSelectReview }) {
  return (
    <table className="table" style={{ marginTop: "var(--space-2)", fontSize: 12 }}>
      <thead>
        <tr>
          <th>Project</th>
          <th>Platform</th>
          <th>Score</th>
          <th>Date</th>
        </tr>
      </thead>
      <tbody>
        {sources.map((source) => (
          <tr key={source.id} style={{ cursor: "pointer" }} onClick={() => onSelectReview(source.id)}>
            <td>{source.project_name}</td>
            <td>{source.platform}</td>
            <td>{source.total_score_pct !== null && source.total_score_pct !== undefined ? `${source.total_score_pct}%` : "—"}</td>
            <td>{formatDate(source.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SourcesSparkline({ sources }) {
  const points = [...sources]
    .filter((source) => source.total_score_pct !== null && source.total_score_pct !== undefined)
    .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
    .map((source) => ({ date: formatDate(source.created_at), score: source.total_score_pct }));

  const uniqueDates = new Set(points.map((point) => point.date));
  if (points.length < 2 || uniqueDates.size < 2) return null;

  return (
    <div style={{ height: 80, marginTop: "var(--space-2)" }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
          <XAxis dataKey="date" tick={{ fontSize: 9 }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 9 }} width={24} />
          <Tooltip />
          <Line dataKey="score" stroke="#1B3A6B" dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSend(event) {
    event.preventDefault();
    const question = input.trim();
    if (!question || loading) return;

    const history = messages.map((message) => ({ role: message.role, content: message.content }));
    const nextMessages = [...messages, { role: "user", content: question }];
    setMessages(nextMessages);
    setInput("");
    setLoading(true);
    try {
      const response = await sendChatMessage(question, history);
      setMessages([...nextMessages, { role: "assistant", content: response.answer, sources: response.sources }]);
    } catch (err) {
      setMessages([...nextMessages, {
        role: "assistant",
        content: "Sorry, something went wrong answering that. Please try again.",
        isError: true,
      }]);
    } finally {
      setLoading(false);
    }
  }

  function handleSelectReview(reviewId) {
    navigate(`/reports/${reviewId}`);
  }

  if (!open) {
    return (
      <button
        type="button"
        className="btn btn-primary"
        aria-label="Open review insights chat"
        style={{
          position: "fixed", bottom: 24, right: 24, borderRadius: 999, width: 56, height: 56,
          padding: 0, boxShadow: "var(--shadow-lg)", display: "flex", alignItems: "center", justifyContent: "center",
        }}
        onClick={() => setOpen(true)}
      >
        <ChatIcon />
      </button>
    );
  }

  return (
    <div
      className="card elev-md"
      style={{
        position: "fixed", bottom: 24, right: 24, width: 360, height: 480,
        display: "flex", flexDirection: "column", padding: 0, overflow: "hidden", zIndex: 100,
      }}
    >
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "var(--space-3) var(--space-4)", borderBottom: "1px solid var(--color-divider)",
      }}
      >
        <span className="card-title" style={{ fontSize: 15 }}>Ask about your reviews</span>
        <button type="button" className="btn btn-ghost" aria-label="Close chat" onClick={() => setOpen(false)}>✕</button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-3) var(--space-4)", display: "grid", gap: "var(--space-3)" }}>
        {messages.length === 0 && (
          <p className="card-body">
            Ask things like "what was the reason for .NET low score" or "common issue in .NET reviews for 2025".
          </p>
        )}
        {messages.map((message, index) => (
          <div key={index} style={{ textAlign: message.role === "user" ? "right" : "left" }}>
            <p
              className="card-body"
              style={{
                display: "inline-block", margin: 0, padding: "8px 12px", borderRadius: 12, textAlign: "left",
                background: message.role === "user" ? "var(--color-accent)" : "var(--color-surface)",
                color: message.role === "user" ? "#fff" : (message.isError ? "var(--color-brand-coral)" : "var(--color-text)"),
              }}
            >
              {message.content}
            </p>
            {message.sources && message.sources.length > 0 && (
              <>
                <SourcesTable sources={message.sources} onSelectReview={handleSelectReview} />
                <SourcesSparkline sources={message.sources} />
              </>
            )}
          </div>
        ))}
        {loading && <SpinnerIcon />}
      </div>

      <form
        onSubmit={handleSend}
        style={{ display: "flex", gap: "var(--space-2)", padding: "var(--space-3) var(--space-4)", borderTop: "1px solid var(--color-divider)" }}
      >
        <input
          type="text"
          className="input"
          aria-label="Ask a question"
          placeholder="Ask a question…"
          value={input}
          disabled={loading}
          onChange={(event) => setInput(event.target.value)}
        />
        <button type="submit" className="btn btn-primary" disabled={loading || !input.trim()}>Send</button>
      </form>
    </div>
  );
}
