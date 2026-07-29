# Multi-Platform Landing Page & Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a landing page for picking a target platform (Android, iOS, .NET, Web/React) and an LLM provider (Azure OpenAI vs local Ollama, persisted but not yet functional), with real URL routing: Android routes into the existing, fully-working review flow; the other three platforms get a disabled placeholder previewing their eventual shape; every subpage can navigate back to the landing page.

**Architecture:** Introduces `react-router-dom` with two routes (`/` and `/review/:platform`). The existing `App.jsx` review flow is extracted unchanged into `pages/AndroidReviewFlow.jsx`; a new `pages/PlaceholderReviewFlow.jsx` reuses the existing `UploadForm` (disabled) for the other three platforms; a shared `components/TopNav.jsx` gives every subpage its "← Home" link; a single `platforms.js` config drives both the home page's cards and the review-page dispatcher's routing/labels. `App.jsx` itself becomes a thin `BrowserRouter` wrapper around a new `AppRoutes.jsx` (split out so the routes can be rendered in tests via `MemoryRouter`, which `BrowserRouter` does not support).

**Tech Stack:** React 19 (CRA), react-router-dom (new dependency), Jest/React Testing Library. Frontend-only — no backend changes.

## Global Constraints

- Frontend-only round: no backend endpoint, schema, or business-logic changes.
- Platform ids and labels, exact: `android`/"Android" (available), `ios`/"iOS", `dotnet`/".NET", `web`/"Web (React)" (all three not available yet) — single source of truth in `platforms.js`.
- Route shape: `/` (home) and `/review/:platform` (review dispatcher) — no other routes.
- LLM provider default is `"azure"` when nothing is yet in `localStorage`, under the key `"llmProvider"`.
- `UploadForm`'s existing `disabled` behavior and default button label (`"Starting review…"`) must not change for existing (Android) callers — the new `disabledLabel` prop only changes behavior for callers that pass it explicitly.
- Follow existing "Industry" design system conventions throughout: `.card.blueprint` + `<CornerMarks />`, `.btn`/`.btn-primary`/`.btn-ghost`, CSS custom properties from `design-system.css` — no ad hoc styling.
- TDD throughout: write the failing test, run it and confirm the failure, implement, run again and confirm the pass, then commit.

---

## Task 1: Platform config + LLM provider persistence

**Files:**
- Create: `frontend/src/platforms.js`
- Create: `frontend/src/services/llmProviderStorage.js`
- Test: `frontend/src/services/llmProviderStorage.test.jsx`

**Interfaces:**
- Consumes: `window.localStorage` (via the browser's global, no import needed).
- Produces: `PLATFORMS` (array export from `platforms.js`, shape `{ id: string, label: string, available: boolean }[]`); `getLlmProvider(): string` and `setLlmProvider(provider: string): void` (exports from `llmProviderStorage.js`).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/services/llmProviderStorage.test.jsx`:

```jsx
import { getLlmProvider, setLlmProvider } from "./llmProviderStorage";

beforeEach(() => {
  localStorage.clear();
});

test("defaults to azure when nothing is stored", () => {
  expect(getLlmProvider()).toBe("azure");
});

test("returns a previously-stored value", () => {
  localStorage.setItem("llmProvider", "ollama");
  expect(getLlmProvider()).toBe("ollama");
});

test("setLlmProvider writes to localStorage under the expected key", () => {
  setLlmProvider("ollama");
  expect(localStorage.getItem("llmProvider")).toBe("ollama");
  expect(getLlmProvider()).toBe("ollama");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npx react-scripts test src/services/llmProviderStorage.test.jsx`
Expected: FAIL — `Cannot find module './llmProviderStorage'`.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/platforms.js`:

```js
export const PLATFORMS = [
  { id: "android", label: "Android", available: true },
  { id: "ios", label: "iOS", available: false },
  { id: "dotnet", label: ".NET", available: false },
  { id: "web", label: "Web (React)", available: false },
];
```

Create `frontend/src/services/llmProviderStorage.js`:

```js
const STORAGE_KEY = "llmProvider";
const DEFAULT_PROVIDER = "azure";

export function getLlmProvider() {
  return localStorage.getItem(STORAGE_KEY) || DEFAULT_PROVIDER;
}

export function setLlmProvider(provider) {
  localStorage.setItem(STORAGE_KEY, provider);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && CI=true npx react-scripts test src/services/llmProviderStorage.test.jsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/platforms.js frontend/src/services/llmProviderStorage.js frontend/src/services/llmProviderStorage.test.jsx
git commit -m "feat: add platform config and LLM provider persistence"
```

---

## Task 2: Install react-router-dom + shared `TopNav`

**Files:**
- Modify: `frontend/package.json` (new dependency)
- Create: `frontend/src/components/TopNav.jsx`
- Test: `frontend/src/components/TopNav.test.jsx`

**Interfaces:**
- Consumes: `react-router-dom`'s `Link`.
- Produces: `TopNav` (default export, no props) — renders the brand and a "← Home" link, both pointing at `/`. Later tasks (`AndroidReviewFlow`, `PlaceholderReviewFlow`) render `<TopNav />` in place of the old inline `<nav>` markup.

- [ ] **Step 1: Install the dependency**

Run: `cd frontend && npm install react-router-dom`
Expected: `frontend/package.json` and `frontend/package-lock.json` gain the new dependency.

- [ ] **Step 2: Write the failing test**

Create `frontend/src/components/TopNav.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import TopNav from "./TopNav";

test("renders the brand and a Home link, both pointing at /", () => {
  render(
    <MemoryRouter>
      <TopNav />
    </MemoryRouter>
  );
  const links = screen.getAllByRole("link");
  expect(links).toHaveLength(2);
  links.forEach((link) => expect(link).toHaveAttribute("href", "/"));
  expect(screen.getByText("Code Review Automation")).toBeInTheDocument();
  expect(screen.getByText("← Home")).toBeInTheDocument();
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && CI=true npx react-scripts test src/components/TopNav.test.jsx`
Expected: FAIL — `Cannot find module './TopNav'`.

- [ ] **Step 4: Write minimal implementation**

Create `frontend/src/components/TopNav.jsx`:

```jsx
import { Link } from "react-router-dom";

export default function TopNav() {
  return (
    <nav className="nav">
      <Link to="/" className="nav-brand" style={{ textDecoration: "none", color: "inherit" }}>
        Code Review Automation
      </Link>
      <Link to="/" className="btn btn-ghost" style={{ marginLeft: "auto" }}>← Home</Link>
    </nav>
  );
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && CI=true npx react-scripts test src/components/TopNav.test.jsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/TopNav.jsx frontend/src/components/TopNav.test.jsx
git commit -m "feat: add react-router-dom and a shared TopNav component"
```

---

## Task 3: `UploadForm` gains a `disabledLabel` prop

**Files:**
- Modify: `frontend/src/components/UploadForm.jsx`
- Test: `frontend/src/components/UploadForm.test.jsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `UploadForm({ onSubmit, disabled, disabledLabel })` — `disabledLabel` defaults to `"Starting review…"` (today's hardcoded text), shown on the submit button instead of "Start review" whenever `disabled` is true.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/components/UploadForm.test.jsx`:

```jsx
test("shows a custom disabledLabel on the button when disabled and provided", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={true} disabledLabel="Coming soon" />);
  expect(screen.getByRole("button", { name: "Coming soon" })).toBeDisabled();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npx react-scripts test src/components/UploadForm.test.jsx`
Expected: FAIL — no button named "Coming soon" (the button still reads "Starting review…" regardless of props).

- [ ] **Step 3: Implement**

In `frontend/src/components/UploadForm.jsx`, change the function signature and the button's label:

```jsx
export default function UploadForm({ onSubmit, disabled, disabledLabel = "Starting review…" }) {
```

```jsx
      <button
        type="submit"
        className="btn btn-primary btn-block blueprint"
        style={{ marginTop: "var(--space-5)" }}
        disabled={disabled || !canStart}
      >
        <CornerMarks />
        {disabled ? disabledLabel : "Start review"}
        <ArrowRightIcon />
      </button>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/components/UploadForm.test.jsx`
Expected: PASS — all 5 tests (4 existing + 1 new), including `"disables inputs and shows the starting label when disabled prop is true"`, which confirms the default is unchanged.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/UploadForm.jsx frontend/src/components/UploadForm.test.jsx
git commit -m "feat: add disabledLabel prop to UploadForm"
```

---

## Task 4: `HomePage`

**Files:**
- Create: `frontend/src/pages/HomePage.jsx`
- Test: `frontend/src/pages/HomePage.test.jsx`

**Interfaces:**
- Consumes: `PLATFORMS` (`frontend/src/platforms.js`, Task 1); `getLlmProvider`/`setLlmProvider` (`frontend/src/services/llmProviderStorage.js`, Task 1); `CornerMarks` (existing, `frontend/src/components/CornerMarks.jsx`); `Link` (react-router-dom, Task 2).
- Produces: `HomePage` (default export, no props) — renders a `.card.blueprint` link per `PLATFORMS` entry (`href` = `/review/<id>`) and an LLM provider toggle. Later tasks (`ReviewPage`/`AppRoutes` in Task 7) mount this at `/`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/HomePage.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import HomePage from "./HomePage";
import { getLlmProvider } from "../services/llmProviderStorage";

beforeEach(() => {
  localStorage.clear();
});

function renderHome() {
  return render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>
  );
}

test("renders a link for each platform pointing at /review/<id>", () => {
  renderHome();
  expect(screen.getByRole("link", { name: /android/i })).toHaveAttribute("href", "/review/android");
  expect(screen.getByRole("link", { name: /ios/i })).toHaveAttribute("href", "/review/ios");
  expect(screen.getByRole("link", { name: /\.net/i })).toHaveAttribute("href", "/review/dotnet");
  expect(screen.getByRole("link", { name: /web \(react\)/i })).toHaveAttribute("href", "/review/web");
});

test("defaults the LLM toggle to Azure OpenAI highlighted", () => {
  renderHome();
  expect(screen.getByRole("button", { name: "Azure OpenAI" })).toHaveClass("btn-primary");
  expect(screen.getByRole("button", { name: "Ollama (local)" })).not.toHaveClass("btn-primary");
});

test("clicking Ollama persists the choice to localStorage and updates the highlighted button", async () => {
  const user = userEvent.setup();
  renderHome();

  await user.click(screen.getByRole("button", { name: "Ollama (local)" }));

  expect(screen.getByRole("button", { name: "Ollama (local)" })).toHaveClass("btn-primary");
  expect(screen.getByRole("button", { name: "Azure OpenAI" })).not.toHaveClass("btn-primary");
  expect(getLlmProvider()).toBe("ollama");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npx react-scripts test src/pages/HomePage.test.jsx`
Expected: FAIL — `Cannot find module './HomePage'`.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/pages/HomePage.jsx`:

```jsx
import { useState } from "react";
import { Link } from "react-router-dom";
import CornerMarks from "../components/CornerMarks";
import { PLATFORMS } from "../platforms";
import { getLlmProvider, setLlmProvider } from "../services/llmProviderStorage";

const LLM_PROVIDERS = [
  { id: "azure", label: "Azure OpenAI" },
  { id: "ollama", label: "Ollama (local)" },
];

export default function HomePage() {
  const [llmProvider, setLlmProviderState] = useState(() => getLlmProvider());

  function handleSelectProvider(providerId) {
    setLlmProvider(providerId);
    setLlmProviderState(providerId);
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <nav className="nav"><span className="nav-brand">Code Review Automation</span></nav>

      <main style={{ maxWidth: 920, margin: "0 auto", padding: "var(--space-8) var(--space-4) var(--space-10)" }}>
        <header style={{ marginBottom: "var(--space-6)" }}>
          <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 38, lineHeight: 1.1, margin: "0 0 var(--space-2)" }}>
            Code Review Automation
          </h1>
          <p style={{ margin: 0, opacity: 0.7, maxWidth: "60ch" }}>
            Choose a platform to start a review.
          </p>
        </header>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
          {PLATFORMS.map((platform) => (
            <Link
              key={platform.id}
              to={`/review/${platform.id}`}
              className="card blueprint elev-md"
              style={{ padding: "var(--space-6)", textDecoration: "none", color: "inherit" }}
            >
              <CornerMarks />
              <div className="card-kicker">{platform.available ? "Available" : "Coming soon"}</div>
              <div className="card-title" style={{ fontSize: 20 }}>{platform.label}</div>
            </Link>
          ))}
        </div>

        <div className="card blueprint" style={{ padding: "var(--space-6)", marginTop: "var(--space-6)" }}>
          <CornerMarks />
          <div className="card-kicker">LLM provider</div>
          <div className="card-title" style={{ fontSize: 20 }}>Choose a model provider</div>
          <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-4)" }}>
            {LLM_PROVIDERS.map((provider) => (
              <button
                key={provider.id}
                type="button"
                className={`btn ${llmProvider === provider.id ? "btn-primary" : ""}`}
                onClick={() => handleSelectProvider(provider.id)}
              >
                {provider.label}
              </button>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/pages/HomePage.test.jsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/HomePage.jsx frontend/src/pages/HomePage.test.jsx
git commit -m "feat: add HomePage with platform cards and LLM provider toggle"
```

---

## Task 5: `PlaceholderReviewFlow`

**Files:**
- Create: `frontend/src/pages/PlaceholderReviewFlow.jsx`
- Test: `frontend/src/pages/PlaceholderReviewFlow.test.jsx`

**Interfaces:**
- Consumes: `TopNav` (`frontend/src/components/TopNav.jsx`, Task 2); `UploadForm` (`frontend/src/components/UploadForm.jsx`, Task 3, using its `disabled`/`disabledLabel` props); `CornerMarks` (existing).
- Produces: `PlaceholderReviewFlow({ platform })` (default export), `platform` shaped `{ id, label, available }` (a `PLATFORMS` entry from Task 1). Later used by `ReviewPage` (Task 7) for every non-Android platform.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/PlaceholderReviewFlow.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import PlaceholderReviewFlow from "./PlaceholderReviewFlow";

const platform = { id: "ios", label: "iOS", available: false };

function renderPlaceholder() {
  return render(
    <MemoryRouter>
      <PlaceholderReviewFlow platform={platform} />
    </MemoryRouter>
  );
}

test("renders the platform's label in the header and banner", () => {
  renderPlaceholder();
  expect(screen.getByRole("heading", { name: "iOS Code Review Automation" })).toBeInTheDocument();
  expect(screen.getByText("iOS support is on the way")).toBeInTheDocument();
});

test("renders the upload form disabled with a coming-soon button label", () => {
  renderPlaceholder();
  expect(screen.getByLabelText(/android project/i)).toBeDisabled();
  expect(screen.getByRole("button", { name: "Coming soon" })).toBeDisabled();
});

test("renders a Home link back to /", () => {
  renderPlaceholder();
  expect(screen.getByText("← Home")).toHaveAttribute("href", "/");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npx react-scripts test src/pages/PlaceholderReviewFlow.test.jsx`
Expected: FAIL — `Cannot find module './PlaceholderReviewFlow'`.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/pages/PlaceholderReviewFlow.jsx`:

```jsx
import TopNav from "../components/TopNav";
import UploadForm from "../components/UploadForm";
import CornerMarks from "../components/CornerMarks";

export default function PlaceholderReviewFlow({ platform }) {
  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <TopNav />

      <main style={{ maxWidth: 920, margin: "0 auto", padding: "var(--space-8) var(--space-4) var(--space-10)" }}>
        <header style={{ marginBottom: "var(--space-6)" }}>
          <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 38, lineHeight: 1.1, margin: "0 0 var(--space-2)" }}>
            {platform.label} Code Review Automation
          </h1>
        </header>

        <div className="card blueprint elev-md" style={{ padding: "var(--space-6)", marginBottom: "var(--space-5)" }}>
          <CornerMarks />
          <div className="card-kicker">Coming soon</div>
          <div className="card-title" style={{ fontSize: 20 }}>{platform.label} support is on the way</div>
          <p className="card-body">
            The review flow will work the same way as Android once {platform.label} support ships.
          </p>
        </div>

        <UploadForm onSubmit={() => {}} disabled disabledLabel="Coming soon" />
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/pages/PlaceholderReviewFlow.test.jsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/PlaceholderReviewFlow.jsx frontend/src/pages/PlaceholderReviewFlow.test.jsx
git commit -m "feat: add PlaceholderReviewFlow for not-yet-available platforms"
```

---

## Task 6: Extract `AndroidReviewFlow`

**Files:**
- Create: `frontend/src/pages/AndroidReviewFlow.jsx` (full content moved from `frontend/src/App.jsx`, imports adjusted for the new location, nav swapped for `TopNav`)
- Create: `frontend/src/pages/AndroidReviewFlow.test.jsx` (full content moved from `frontend/src/App.test.jsx`, adjusted per below)
- (`frontend/src/App.jsx` and `frontend/src/App.test.jsx` are left untouched in this task — Task 7 replaces their content, so the app keeps building and every existing test keeps passing until then, at the cost of this task's content being briefly duplicated.)

**Interfaces:**
- Consumes: `TopNav` (`frontend/src/components/TopNav.jsx`, Task 2); every component `App.jsx` already used (`UploadForm`, `ProgressTracker`, `FindingsPanel`, `CategoryScoresChart`, `LlmUsageStats`, `PromptDebugLog`, `ReportTable`, `StatsDisplay`, `CornerMarks`, `createReview`) — same imports, just one directory level up (`../components/...`, `../services/api`).
- Produces: `AndroidReviewFlow` (default export, no props) — identical behavior to the current `App`. Used by `ReviewPage` (Task 7) when `platform.id === "android"`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/AndroidReviewFlow.test.jsx` with this exact content (the current `App.test.jsx`, with: the import path and component name changed from `App` to `AndroidReviewFlow`; the `services/api` import/mock path changed from `./services/api` to `../services/api`; a `renderFlow()` helper wrapping every render in `MemoryRouter` in place of the old bare `render(<App />)` calls; and one new assertion for the "← Home" link appended to the happy-path test):

```jsx
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import AndroidReviewFlow from "./AndroidReviewFlow";
import { createReview, getProgress } from "../services/api";

jest.mock("../services/api", () => ({
  ...jest.requireActual("../services/api"),
  createReview: jest.fn(),
  getProgress: jest.fn(),
}));

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
  jest.resetAllMocks();
});

function buildFile(name, type) {
  return new File(["content"], name, { type });
}

function renderFlow() {
  return render(
    <MemoryRouter>
      <AndroidReviewFlow />
    </MemoryRouter>
  );
}

async function uploadValidFiles(user) {
  const zip = buildFile("project.zip", "application/zip");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  await user.upload(screen.getByLabelText(/scoring template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));
}

test("full happy path: upload, poll, complete, download link, LLM stats, reset", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "completed", phase: "completed", progress: 100, message: "Done",
    stats: { total_time_ms: 500 }, download_url: "/api/reviews/abc-123/download", error: null,
    warnings: ["Missing AndroidManifest.xml"], test_coverage: 90.0, secrets_found: [],
    total_score_pct: 78,
    project_name: "project",
    category_scores: [
      {
        id: "1", name: "Code naming conventions / Code Structure", percent_points: 90.0,
        sub_criteria: [{ id: "1.1", description: "Clear naming", score: 1, remark: "" }],
      },
    ],
    code_context: "class MainActivity {}",
    prompt_log: [
      {
        label: "Code naming conventions / Code Structure",
        prompt_text: "Score the following...",
        tokens: { prompt_tokens: 500, completion_tokens: 40, total_tokens: 540, cached_tokens: null },
      },
    ],
    lint_issues: [],
    compile_status: "ok",
  });

  renderFlow();
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByText(/review ready/i)).toBeInTheDocument();
  expect(screen.getByText("Total 78%")).toBeInTheDocument();
  expect(screen.getAllByText("Code naming conventions / Code Structure").length).toBeGreaterThan(0);
  expect(screen.getByText("1 LLM calls")).toBeInTheDocument();
  expect(screen.getByText("540 tokens used")).toBeInTheDocument();
  expect(screen.getByText("1.1")).toBeInTheDocument();
  expect(screen.queryByText(/show source code sent to the model/i)).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Debug info" }));
  expect(screen.getByText(/show source code sent to the model/i)).toBeInTheDocument();
  expect(screen.queryByText("1.1")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Report" }));
  expect(screen.getByText("1.1")).toBeInTheDocument();
  expect(screen.queryByText(/show source code sent to the model/i)).not.toBeInTheDocument();

  expect(screen.getByText("No Lint warnings or errors found.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /download populated workbook/i })).toHaveAttribute(
    "href",
    "http://localhost:8000/api/reviews/abc-123/download"
  );
  expect(screen.getByText("← Home")).toHaveAttribute("href", "/");

  await user.click(screen.getByRole("button", { name: /start new review/i }));
  expect(screen.getByLabelText(/android project/i)).toBeInTheDocument();
});

test("shows the project name in the header once progress data has it, falling back beforehand", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "completed", phase: "completed", progress: 100, message: "Done",
    stats: {}, download_url: "/api/reviews/abc-123/download", error: null,
    warnings: [], test_coverage: null, secrets_found: [], total_score_pct: null,
    project_name: "MyAndroidApp",
    category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: "ok",
  });

  renderFlow();
  expect(screen.getByRole("heading", { name: "Android Code Review Automation" })).toBeInTheDocument();

  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByRole("heading", { name: "MyAndroidApp" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Android Code Review Automation" })).not.toBeInTheDocument();
});

test("shows an error message when review creation fails", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockRejectedValue(new Error("network error"));

  renderFlow();
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByText(/failed to start review/i)).toBeInTheDocument();
});

test("shows an error message when the review itself fails during processing, and Try again resets to idle", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "error", phase: "error", progress: 0, message: "Queued",
    stats: {}, download_url: null, error: "No source files found (.java/.kt)",
    warnings: [], test_coverage: null, secrets_found: [], total_score_pct: null,
    project_name: null,
    category_scores: [], code_context: null, prompt_log: [],
    lint_issues: [], compile_status: null,
  });

  renderFlow();
  await act(async () => {
    await uploadValidFiles(user);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(screen.getByText("No source files found (.java/.kt)")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /try again/i }));
  expect(screen.getByLabelText(/android project/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npx react-scripts test src/pages/AndroidReviewFlow.test.jsx`
Expected: FAIL — `Cannot find module './AndroidReviewFlow'`.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/pages/AndroidReviewFlow.jsx` (the current `frontend/src/App.jsx` content, with imports adjusted one directory level up and the `<nav>` replaced by `<TopNav />`):

```jsx
import { useCallback, useState } from "react";
import UploadForm from "../components/UploadForm";
import ProgressTracker from "../components/ProgressTracker";
import FindingsPanel from "../components/FindingsPanel";
import CategoryScoresChart from "../components/CategoryScoresChart";
import LlmUsageStats from "../components/LlmUsageStats";
import PromptDebugLog from "../components/PromptDebugLog";
import ReportTable from "../components/ReportTable";
import StatsDisplay from "../components/StatsDisplay";
import CornerMarks from "../components/CornerMarks";
import TopNav from "../components/TopNav";
import { createReview } from "../services/api";

const SCORING_PHASES = ["scoring", "generating", "completed"];

export default function AndroidReviewFlow() {
  const [state, setState] = useState("idle"); // idle | uploading | polling | completed | error
  const [reviewId, setReviewId] = useState(null);
  const [progressData, setProgressData] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [bottomView, setBottomView] = useState("report"); // report | debug

  const handleUpload = useCallback(async (androidZip, excelTemplate) => {
    setState("uploading");
    setErrorMessage("");
    try {
      const result = await createReview(androidZip, excelTemplate);
      if (result.status === "error") {
        setErrorMessage(result.error || "Upload failed");
        setState("error");
        return;
      }
      setReviewId(result.review_id);
      setState("polling");
    } catch (err) {
      setErrorMessage("Failed to start review. Is the server running?");
      setState("error");
    }
  }, []);

  const handleProgressUpdate = useCallback((data) => {
    setProgressData(data);
    if (data.status === "completed") {
      setState("completed");
    } else if (data.status === "error") {
      setErrorMessage(data.error || "Review failed");
      setState("error");
    }
  }, []);

  function handleReset() {
    setState("idle");
    setReviewId(null);
    setProgressData(null);
    setErrorMessage("");
  }

  const isRunningOrDone = state === "polling" || state === "completed";
  const showLlmDetails = !!progressData && SCORING_PHASES.includes(progressData.phase);

  return (
    <div style={{ minHeight: "100vh", background: "var(--color-bg)", fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
      <TopNav />

      <main style={{ maxWidth: isRunningOrDone ? 1440 : 920, margin: "0 auto", padding: "var(--space-8) var(--space-4) var(--space-10)" }}>
        <header style={{ marginBottom: "var(--space-6)" }}>
          <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 38, lineHeight: 1.1, margin: "0 0 var(--space-2)" }}>
            {progressData?.project_name || "Android Code Review Automation"}
          </h1>
          <p style={{ margin: 0, opacity: 0.7, maxWidth: "60ch" }}>
            Upload an Android project and a scoring template. The reviewer analyzes structure, security, tests and
            dependency versions, scores each category with AI, and hands back a populated workbook.
          </p>
        </header>

        {(state === "idle" || state === "uploading") && (
          <UploadForm onSubmit={handleUpload} disabled={state === "uploading"} />
        )}

        {isRunningOrDone && reviewId && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
              <div>
                {state === "polling" && (
                  <ProgressTracker reviewId={reviewId} onUpdate={handleProgressUpdate} />
                )}
                {progressData && (
                  <div style={{ marginTop: state === "polling" ? "var(--space-5)" : 0 }}>
                    <FindingsPanel
                      warnings={progressData.warnings}
                      testCoverage={progressData.test_coverage}
                      secretsFound={progressData.secrets_found}
                      lintIssues={progressData.lint_issues}
                      compileStatus={progressData.compile_status}
                    />
                  </div>
                )}
                {state === "completed" && progressData && (
                  <div style={{ marginTop: "var(--space-5)" }}>
                    <StatsDisplay
                      totalScorePct={progressData.total_score_pct}
                      warnings={progressData.warnings}
                      secretsFound={progressData.secrets_found}
                      stats={progressData.stats}
                      downloadUrl={progressData.download_url}
                      onReset={handleReset}
                    />
                  </div>
                )}
              </div>

              <div>
                {showLlmDetails && (
                  <>
                    <CategoryScoresChart categoryScores={progressData.category_scores} />
                    <div style={{ marginTop: "var(--space-4)" }}>
                      <LlmUsageStats promptLog={progressData.prompt_log} />
                    </div>
                  </>
                )}
              </div>
            </div>

            {showLlmDetails && (
              <div style={{ marginTop: "var(--space-5)" }}>
                <div style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-4)" }}>
                  <button
                    type="button"
                    className={`btn ${bottomView === "report" ? "btn-primary" : ""}`}
                    onClick={() => setBottomView("report")}
                  >
                    Report
                  </button>
                  <button
                    type="button"
                    className={`btn ${bottomView === "debug" ? "btn-primary" : ""}`}
                    onClick={() => setBottomView("debug")}
                  >
                    Debug info
                  </button>
                </div>
                {bottomView === "report" ? (
                  <ReportTable categoryScores={progressData.category_scores} />
                ) : (
                  <PromptDebugLog codeContext={progressData.code_context} promptLog={progressData.prompt_log} />
                )}
              </div>
            )}
          </>
        )}

        {state === "error" && (
          <div className="card blueprint elev-md" style={{ padding: "var(--space-6)" }}>
            <CornerMarks />
            <div className="card-kicker">Error</div>
            <div className="card-title" style={{ fontSize: 20 }}>Review failed</div>
            <p className="card-body">{errorMessage}</p>
            <div style={{ display: "flex", gap: "var(--space-3)", marginTop: "var(--space-4)" }}>
              <button type="button" className="btn btn-primary blueprint" onClick={handleReset}>
                <CornerMarks />
                Try again
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test src/pages/AndroidReviewFlow.test.jsx src/App.test.jsx`
Expected: PASS — both the new `AndroidReviewFlow.test.jsx` and the still-untouched original `App.test.jsx` pass (temporary duplication, resolved in Task 7).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AndroidReviewFlow.jsx frontend/src/pages/AndroidReviewFlow.test.jsx
git commit -m "feat: extract AndroidReviewFlow with a Home link, ready for routing"
```

---

## Task 7: Router shell — `AppRoutes`, `ReviewPage`, and the new `App.jsx`/`App.test.jsx`

**Files:**
- Create: `frontend/src/pages/ReviewPage.jsx`
- Create: `frontend/src/AppRoutes.jsx`
- Modify (full rewrite): `frontend/src/App.jsx`
- Modify (full rewrite): `frontend/src/App.test.jsx`

**Interfaces:**
- Consumes: `PLATFORMS` (Task 1); `AndroidReviewFlow` (Task 6); `PlaceholderReviewFlow` (Task 5); `HomePage` (Task 4); `Navigate`/`useParams`/`BrowserRouter`/`Routes`/`Route`/`MemoryRouter` (react-router-dom, Task 2).
- Produces: `ReviewPage` (default export, no props, reads `:platform` via `useParams()`) — dispatches to `AndroidReviewFlow`, `PlaceholderReviewFlow`, or `<Navigate to="/" replace />`. `AppRoutes` (default export, no props) — the `<Routes>` tree, split out from `App.jsx` specifically so tests can render it inside `MemoryRouter` (which needs a controllable initial path; `BrowserRouter` does not support one).

- [ ] **Step 1: Write the failing test**

Overwrite `frontend/src/App.test.jsx` with routing-only tests:

```jsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AppRoutes from "./AppRoutes";

function renderAt(initialPath) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AppRoutes />
    </MemoryRouter>
  );
}

test("renders the home page's platform cards and LLM toggle at /", () => {
  renderAt("/");
  expect(screen.getByRole("link", { name: /android/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Azure OpenAI" })).toBeInTheDocument();
});

test("renders the Android review flow at /review/android", () => {
  renderAt("/review/android");
  expect(screen.getByRole("button", { name: /start review/i })).toBeInTheDocument();
});

test("renders a placeholder banner for a not-yet-available platform", () => {
  renderAt("/review/ios");
  expect(screen.getByText("iOS support is on the way")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Coming soon" })).toBeDisabled();
});

test("redirects to / for an unknown platform id", () => {
  renderAt("/review/nonsense");
  expect(screen.getByRole("link", { name: /android/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && CI=true npx react-scripts test src/App.test.jsx`
Expected: FAIL — `Cannot find module './AppRoutes'` (and the old `App.test.jsx` content this overwrites is gone, so its prior assertions no longer run from this file — that content now lives in `AndroidReviewFlow.test.jsx`, Task 6).

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/pages/ReviewPage.jsx`:

```jsx
import { Navigate, useParams } from "react-router-dom";
import { PLATFORMS } from "../platforms";
import AndroidReviewFlow from "./AndroidReviewFlow";
import PlaceholderReviewFlow from "./PlaceholderReviewFlow";

export default function ReviewPage() {
  const { platform: platformId } = useParams();
  const platform = PLATFORMS.find((p) => p.id === platformId);

  if (!platform) return <Navigate to="/" replace />;
  if (platform.id === "android") return <AndroidReviewFlow />;
  return <PlaceholderReviewFlow platform={platform} />;
}
```

Create `frontend/src/AppRoutes.jsx`:

```jsx
import { Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";
import ReviewPage from "./pages/ReviewPage";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/review/:platform" element={<ReviewPage />} />
    </Routes>
  );
}
```

Overwrite `frontend/src/App.jsx`:

```jsx
import { BrowserRouter } from "react-router-dom";
import AppRoutes from "./AppRoutes";

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && CI=true npx react-scripts test`
Expected: PASS — full frontend suite green, including `App.test.jsx` (this task), `AndroidReviewFlow.test.jsx` (Task 6), `PlaceholderReviewFlow.test.jsx` (Task 5), `HomePage.test.jsx` (Task 4), `UploadForm.test.jsx` (Task 3), `TopNav.test.jsx` (Task 2), `llmProviderStorage.test.jsx` (Task 1), and every pre-existing component test untouched by this plan.

Then confirm no leftover duplication from the Task 6/7 overwrite: `grep -r "Android Code Review Automation" frontend/src/App.jsx` should produce no output (the string only appears in `AndroidReviewFlow.jsx` and `PlaceholderReviewFlow.jsx` now, since `App.jsx` was fully overwritten in Step 3 above).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ReviewPage.jsx frontend/src/AppRoutes.jsx frontend/src/App.jsx frontend/src/App.test.jsx
git commit -m "feat: wire up routing — home page, Android flow, and platform placeholders"
```

---

## Final Verification

- [ ] Run the full frontend suite: `cd frontend && CI=true npx react-scripts test` — all green.
- [ ] Run the full backend suite: `cd backend && source venv/bin/activate && python -m pytest -v` — all green (this round made no backend changes, confirms nothing broke).
- [ ] Rebuild and restart the frontend container: `docker compose up -d --build frontend`.
- [ ] Manually verify in the browser: landing page shows 4 platform cards and an LLM provider toggle; clicking Android goes to the existing working review flow; clicking iOS/.NET/Web shows the disabled form with a "Coming soon" banner; every subpage's "← Home" link returns to `/`; selecting Ollama on the home page, then reloading the page, still shows Ollama selected (persisted).
