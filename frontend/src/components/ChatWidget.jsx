import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Markdown from "markdown-to-jsx";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChatIcon, SpinnerIcon } from "../icons";
import { sendChatMessage } from "../services/api";

const DEFAULT_WIDTH = 360;
const DEFAULT_HEIGHT = 480;
const MIN_WIDTH = 320;
const MIN_HEIGHT = 320;

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
  const [size, setSize] = useState({ width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT });
  const dragRef = useRef(null);
  const navigate = useNavigate();

  // The panel is anchored bottom-right (position: fixed; bottom/right), so
  // the top-left corner is the one that actually moves as it resizes --
  // native CSS `resize` always puts its handle at the bottom-right corner
  // with no way to relocate it, so this drives width/height by hand from a
  // handle placed where users actually expect to grab it.
  useEffect(() => {
    function handleMouseMove(event) {
      if (!dragRef.current) return;
      const { startX, startY, startWidth, startHeight } = dragRef.current;
      const maxWidth = Math.min(640, window.innerWidth * 0.9);
      const maxHeight = window.innerHeight * 0.9;
      setSize({
        width: Math.min(maxWidth, Math.max(MIN_WIDTH, startWidth + (startX - event.clientX))),
        height: Math.min(maxHeight, Math.max(MIN_HEIGHT, startHeight + (startY - event.clientY))),
      });
    }
    function handleMouseUp() {
      dragRef.current = null;
    }
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  function handleResizeStart(event) {
    event.preventDefault();
    dragRef.current = { startX: event.clientX, startY: event.clientY, startWidth: size.width, startHeight: size.height };
  }

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
        position: "fixed", bottom: 24, right: 24, width: size.width, height: size.height,
        display: "flex", flexDirection: "column", padding: 0, overflow: "hidden", zIndex: 100,
      }}
    >
      <div
        role="presentation"
        aria-label="Resize chat window"
        onMouseDown={handleResizeStart}
        style={{
          position: "absolute", top: 0, left: 0, width: 18, height: 18,
          cursor: "nwse-resize", zIndex: 101, display: "flex", alignItems: "flex-start", justifyContent: "flex-start",
          color: "var(--color-text-muted)",
        }}
      >
        <svg width="12" height="12" viewBox="0 0 12 12" style={{ margin: 3 }}>
          <path d="M1 11 L11 1 M4.5 11 L11 4.5 M8 11 L11 8" stroke="currentColor" strokeWidth="1.3" fill="none" />
        </svg>
      </div>

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
            <div
              className="card-body"
              style={{
                display: "inline-block", margin: 0, padding: "8px 12px", borderRadius: 12, textAlign: "left",
                background: message.role === "user" ? "var(--color-accent)" : "var(--color-surface)",
                color: message.role === "user" ? "#fff" : (message.isError ? "var(--color-brand-coral)" : "var(--color-text)"),
              }}
            >
              {message.role === "assistant" ? <Markdown>{message.content}</Markdown> : message.content}
            </div>
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
