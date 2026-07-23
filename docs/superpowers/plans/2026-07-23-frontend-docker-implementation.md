# Frontend + Docker Compose Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a React single-page app that uploads an Android ZIP + Excel template to the backend, polls progress, shows mid-flight findings, and downloads the completed review — then package both services with Docker Compose.

**Architecture:** Create React App (react-scripts 5.0.1) + Tailwind CSS v3 + Axios. One page (`App.jsx`) owns a simple state machine (`idle → uploading → polling → completed/error`) and renders four focused components. No routing, no external state library. Docker: multi-stage frontend build (Node build stage → `serve` static-file stage, no nginx), wired to the existing backend image via `docker-compose.yml`.

**Tech Stack:** React 18/19 (whatever CRA's latest installs), react-scripts 5.0.1, Tailwind CSS 3, Axios, React Testing Library (bundled with CRA by default), Docker.

## Global Constraints

- Plain JavaScript, `.jsx` file extensions for React components (react-scripts' default webpack config resolves `.jsx` out of the box — verified).
- Tailwind CSS v3 (not v4 — v4's setup is meaningfully different and untested here; v3 + CRA is a well-trodden path, verified working end-to-end including production build).
- No routing library, no Redux/Zustand/etc. — `useState`/`useCallback` in `App.jsx` is sufficient for this single page.
- Polling interval is exactly 2000ms while `status === "processing"` (matches the backend design's documented 2s interval — no WebSocket).
- The backend's error contract is "always HTTP 200, errors carried in the response body." The frontend must check `status`/`error` fields in response bodies, never rely on HTTP status codes to detect review failures (a non-2xx only happens for truly unexpected network/server errors, e.g. the backend being down).
- `warnings`/`test_coverage`/`secrets_found` become available on the progress response *before* the review reaches `"completed"` (they populate after the `"analyzing"` phase, mid-poll) — `FindingsPanel` must be able to render while `status` is still `"processing"`.
- **Docker + CRA env var gotcha:** `REACT_APP_*` variables are baked into the static JS bundle at `npm run build` time, not read at container runtime. Setting `REACT_APP_API_URL` as a plain `environment:` entry in `docker-compose.yml` for the frontend service would have **no effect** on the already-built bundle. It must be passed as a Docker build `ARG`/`ENV` *before* `RUN npm run build` in the Dockerfile, and supplied via `build.args` in `docker-compose.yml`.
- No nginx. Serve the production build with the `serve` npm package (`serve -s build -l 3000`) — verified this is also the CRA-suggested approach for static deployment.
- Client-side upload extension validation (`.zip`/`.xlsx`) is a UX nicety, not a security boundary — it mirrors, does not replace, the backend's own validation.

---

### Task 1: Scaffold Create React App with Tailwind CSS and Axios

**Files:**
- Create: `frontend/` (via `create-react-app`, generates `package.json`, `public/`, `src/index.js`, `src/index.css`, `src/App.js`, etc.)
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/src/index.css`
- Modify: `frontend/package.json` (via `npm install`, not manual editing)

**Interfaces:**
- Produces: a working CRA project at `frontend/` with `npm start` and `npm run build` both functional, Tailwind utility classes compiling into the production CSS bundle, and `axios` installed as a dependency — consumed by every later task in this plan.

- [ ] **Step 1: Scaffold the CRA project**

Run from the repository root (`/Users/mehroshmehboob/VsCodeProjects/CodeReviewsAutomation`):

```bash
npx create-react-app frontend
```

Expected: completes with "Success! Created frontend at ...", no nested `.git` created inside `frontend/` (CRA detects the repo root is already a git repository and skips `git init` — verify with `git -C frontend rev-parse --is-inside-work-tree 2>&1`, expected output is the same repo root as the parent, or an error if no nested repo exists; either way, run `ls -la frontend/.git` and confirm it does NOT exist as its own directory — if it does, remove it with `rm -rf frontend/.git`).

- [ ] **Step 2: Install Tailwind CSS v3 and Axios**

```bash
cd frontend
npm install -D tailwindcss@3 postcss autoprefixer
npx tailwindcss init -p
npm install axios
```

Expected: `tailwind.config.js` and `postcss.config.js` are created in `frontend/`.

- [ ] **Step 3: Configure Tailwind's content paths**

Replace `frontend/tailwind.config.js` with:

```javascript
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

- [ ] **Step 4: Add Tailwind directives**

Replace the entire contents of `frontend/src/index.css` with:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 5: Verify the production build compiles Tailwind classes**

```bash
cd frontend
CI=true npm run build
grep -rl "flex" build/static/css/*.css
```

Expected: build succeeds ("The build folder is ready to be deployed."), and the grep finds Tailwind's `flex` utility class present in the compiled CSS (proving Tailwind is actually processing `src/` content, not just installed inertly). This is expected because CRA's default `src/App.js` (not yet replaced) contains Tailwind-irrelevant CSS classes from `App.css`, but Tailwind's `preflight`/`base` layer alone emits enough base styles — if `grep` finds nothing, add a temporary `className="flex"` to any element in `src/App.js`, rebuild, confirm, then remove it (Task 7 replaces `App.js` entirely anyway).

- [ ] **Step 6: Commit**

```bash
cd /Users/mehroshmehboob/VsCodeProjects/CodeReviewsAutomation
git add frontend/
git commit -m "feat: scaffold CRA frontend with Tailwind CSS and axios"
```

---

### Task 2: API service module

**Files:**
- Create: `frontend/src/services/api.js`
- Test: `frontend/src/services/api.test.js`

**Interfaces:**
- Produces: `createReview(androidZip: File, excelTemplate: File) -> Promise<{review_id: string, status: string}>`, `getProgress(reviewId: string) -> Promise<ProgressResponse>`, `getDownloadUrl(downloadPath: string) -> string` — consumed by Tasks 3, 4, 6, 7.
- `ProgressResponse` shape (from the real backend, verified against `backend/app/api/reviews.py`): `{status, phase, progress, message, stats, download_url, error, warnings, test_coverage, secrets_found}`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/services/api.test.js`:
```javascript
import axios from "axios";
import { createReview, getProgress, getDownloadUrl } from "./api";

jest.mock("axios");

describe("createReview", () => {
  it("posts multipart form data with both files and returns the response body", async () => {
    axios.post.mockResolvedValue({ data: { review_id: "abc-123", status: "processing" } });
    const zip = new File(["zip content"], "project.zip", { type: "application/zip" });
    const xlsx = new File(["xlsx content"], "template.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

    const result = await createReview(zip, xlsx);

    expect(result).toEqual({ review_id: "abc-123", status: "processing" });
    expect(axios.post).toHaveBeenCalledTimes(1);
    const [url, formData] = axios.post.mock.calls[0];
    expect(url).toContain("/reviews");
    expect(formData.get("androidZip")).toBe(zip);
    expect(formData.get("excelTemplate")).toBe(xlsx);
  });
});

describe("getProgress", () => {
  it("fetches progress for a review id and returns the response body", async () => {
    const progressBody = {
      status: "processing", phase: "scoring", progress: 60, message: "Scoring",
      stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
    };
    axios.get.mockResolvedValue({ data: progressBody });

    const result = await getProgress("abc-123");

    expect(result).toEqual(progressBody);
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining("/reviews/abc-123/progress"));
  });
});

describe("getDownloadUrl", () => {
  it("combines the API origin with the backend's returned download path without doubling /api", () => {
    const url = getDownloadUrl("/api/reviews/abc-123/download");
    expect(url).toBe("http://localhost:8000/api/reviews/abc-123/download");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx react-scripts test src/services/api.test.js --watchAll=false`
Expected: FAIL — `Cannot find module './api'`

- [ ] **Step 3: Implement api.js**

`frontend/src/services/api.js`:
```javascript
import axios from "axios";

const API_BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:8000/api";
const API_ORIGIN = API_BASE_URL.replace(/\/api\/?$/, "");

export async function createReview(androidZip, excelTemplate) {
  const formData = new FormData();
  formData.append("androidZip", androidZip);
  formData.append("excelTemplate", excelTemplate);
  const response = await axios.post(`${API_BASE_URL}/reviews`, formData);
  return response.data;
}

export async function getProgress(reviewId) {
  const response = await axios.get(`${API_BASE_URL}/reviews/${reviewId}/progress`);
  return response.data;
}

export function getDownloadUrl(downloadPath) {
  return `${API_ORIGIN}${downloadPath}`;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx react-scripts test src/services/api.test.js --watchAll=false`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api.js frontend/src/services/api.test.js
git commit -m "feat: add API service module for reviews endpoints"
```

---

### Task 3: UploadForm component

**Files:**
- Create: `frontend/src/components/UploadForm.jsx`
- Test: `frontend/src/components/UploadForm.test.jsx`

**Interfaces:**
- Consumes: nothing (props only).
- Produces: `<UploadForm onSubmit={(androidZip: File, excelTemplate: File) => void} disabled={boolean} />` — consumed by Task 7 (`App.jsx`).

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/UploadForm.test.jsx`:
```javascript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import UploadForm from "./UploadForm";

function buildFile(name, type) {
  return new File(["content"], name, { type });
}

test("calls onSubmit with both files when extensions are valid", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn();
  render(<UploadForm onSubmit={onSubmit} disabled={false} />);

  const zip = buildFile("project.zip", "application/zip");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  await user.upload(screen.getByLabelText(/review template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(onSubmit).toHaveBeenCalledWith(zip, xlsx);
});

test("shows a validation error and does not call onSubmit when the zip has the wrong extension", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn();
  render(<UploadForm onSubmit={onSubmit} disabled={false} />);

  const notAZip = buildFile("project.txt", "text/plain");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), notAZip);
  await user.upload(screen.getByLabelText(/review template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));

  expect(onSubmit).not.toHaveBeenCalled();
  expect(screen.getByText(/must be a \.zip file/i)).toBeInTheDocument();
});

test("disables inputs and button when disabled prop is true", () => {
  render(<UploadForm onSubmit={jest.fn()} disabled={true} />);
  expect(screen.getByLabelText(/android project/i)).toBeDisabled();
  expect(screen.getByRole("button")).toBeDisabled();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx react-scripts test src/components/UploadForm.test.jsx --watchAll=false`
Expected: FAIL — `Cannot find module './UploadForm'`

- [ ] **Step 3: Implement UploadForm.jsx**

`frontend/src/components/UploadForm.jsx`:
```jsx
import { useState } from "react";

export default function UploadForm({ onSubmit, disabled }) {
  const [androidZip, setAndroidZip] = useState(null);
  const [excelTemplate, setExcelTemplate] = useState(null);
  const [validationError, setValidationError] = useState("");

  function handleSubmit(event) {
    event.preventDefault();
    if (!androidZip || !androidZip.name.endsWith(".zip")) {
      setValidationError("Android project must be a .zip file");
      return;
    }
    if (!excelTemplate || !excelTemplate.name.endsWith(".xlsx")) {
      setValidationError("Review template must be a .xlsx file");
      return;
    }
    setValidationError("");
    onSubmit(androidZip, excelTemplate);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700" htmlFor="androidZip">
          Android Project (.zip)
        </label>
        <input
          id="androidZip"
          type="file"
          accept=".zip"
          disabled={disabled}
          onChange={(event) => setAndroidZip(event.target.files[0] ?? null)}
          className="mt-1 block w-full"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700" htmlFor="excelTemplate">
          Review Template (.xlsx)
        </label>
        <input
          id="excelTemplate"
          type="file"
          accept=".xlsx"
          disabled={disabled}
          onChange={(event) => setExcelTemplate(event.target.files[0] ?? null)}
          className="mt-1 block w-full"
        />
      </div>
      {validationError && <p className="text-red-600 text-sm">{validationError}</p>}
      <button
        type="submit"
        disabled={disabled}
        className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-50"
      >
        {disabled ? "Uploading..." : "Start Review"}
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx react-scripts test src/components/UploadForm.test.jsx --watchAll=false`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/UploadForm.jsx frontend/src/components/UploadForm.test.jsx
git commit -m "feat: add UploadForm component with client-side extension validation"
```

---

### Task 4: ProgressTracker component

**Files:**
- Create: `frontend/src/components/ProgressTracker.jsx`
- Test: `frontend/src/components/ProgressTracker.test.jsx`

**Interfaces:**
- Consumes: `getProgress(reviewId: string) -> Promise<ProgressResponse>` (Task 2, `../services/api`).
- Produces: `<ProgressTracker reviewId={string} onUpdate={(data: ProgressResponse) => void} />` — consumed by Task 7 (`App.jsx`). `onUpdate` must be a stable (memoized) callback from the caller, since it is a `useEffect` dependency.

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/ProgressTracker.test.jsx`:
```javascript
import { act, render, screen } from "@testing-library/react";
import ProgressTracker from "./ProgressTracker";
import { getProgress } from "../services/api";

jest.mock("../services/api");

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
  jest.resetAllMocks();
});

test("polls immediately on mount and shows the returned phase", async () => {
  getProgress.mockResolvedValue({
    status: "processing", phase: "extracting", progress: 20, message: "Extracting...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
  });
  const onUpdate = jest.fn();

  render(<ProgressTracker reviewId="abc-123" onUpdate={onUpdate} />);
  await act(async () => {
    await Promise.resolve();
  });

  expect(getProgress).toHaveBeenCalledWith("abc-123");
  expect(screen.getByText("extracting")).toBeInTheDocument();
  expect(onUpdate).toHaveBeenCalledWith(expect.objectContaining({ phase: "extracting" }));
});

test("polls again after 2000ms while status is processing", async () => {
  getProgress.mockResolvedValue({
    status: "processing", phase: "scoring", progress: 60, message: "Scoring...",
    stats: {}, download_url: null, error: null, warnings: [], test_coverage: null, secrets_found: [],
  });
  render(<ProgressTracker reviewId="abc-123" onUpdate={jest.fn()} />);
  await act(async () => {
    await Promise.resolve();
  });
  expect(getProgress).toHaveBeenCalledTimes(1);

  await act(async () => {
    jest.advanceTimersByTime(2000);
    await Promise.resolve();
  });

  expect(getProgress).toHaveBeenCalledTimes(2);
});

test("stops polling once status is completed", async () => {
  getProgress.mockResolvedValue({
    status: "completed", phase: "completed", progress: 100, message: "Done",
    stats: { total_time_ms: 500 }, download_url: "/api/reviews/abc-123/download", error: null,
    warnings: [], test_coverage: null, secrets_found: [],
  });
  render(<ProgressTracker reviewId="abc-123" onUpdate={jest.fn()} />);
  await act(async () => {
    await Promise.resolve();
  });
  expect(getProgress).toHaveBeenCalledTimes(1);

  await act(async () => {
    jest.advanceTimersByTime(2000);
    await Promise.resolve();
  });

  expect(getProgress).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx react-scripts test src/components/ProgressTracker.test.jsx --watchAll=false`
Expected: FAIL — `Cannot find module './ProgressTracker'`

- [ ] **Step 3: Implement ProgressTracker.jsx**

`frontend/src/components/ProgressTracker.jsx`:
```jsx
import { useEffect, useState } from "react";
import { getProgress } from "../services/api";

const POLL_INTERVAL_MS = 2000;

export default function ProgressTracker({ reviewId, onUpdate }) {
  const [progressData, setProgressData] = useState(null);

  useEffect(() => {
    let intervalId;
    let cancelled = false;

    async function poll() {
      const data = await getProgress(reviewId);
      if (cancelled) return;
      setProgressData(data);
      onUpdate(data);
      if (data.status !== "processing") {
        clearInterval(intervalId);
      }
    }

    poll();
    intervalId = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [reviewId, onUpdate]);

  if (!progressData) {
    return <p className="text-gray-500">Starting review...</p>;
  }

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium capitalize">{progressData.phase}</p>
      <div className="w-full bg-gray-200 rounded h-2">
        <div className="bg-blue-600 h-2 rounded" style={{ width: `${progressData.progress}%` }} />
      </div>
      <p className="text-sm text-gray-500">{progressData.message}</p>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx react-scripts test src/components/ProgressTracker.test.jsx --watchAll=false`
Expected: PASS (3 passed). If the async/fake-timer interaction is flaky, add an extra `await act(async () => { await Promise.resolve(); })` flush after each `jest.advanceTimersByTime` call — this is a known fiddly area (mixing fake timers with real promise microtasks), iterate on flushing rather than changing the component's actual polling logic.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ProgressTracker.jsx frontend/src/components/ProgressTracker.test.jsx
git commit -m "feat: add ProgressTracker component with 2s polling"
```

---

### Task 5: FindingsPanel component

**Files:**
- Create: `frontend/src/components/FindingsPanel.jsx`
- Test: `frontend/src/components/FindingsPanel.test.jsx`

**Interfaces:**
- Consumes: nothing (props only).
- Produces: `<FindingsPanel warnings={string[]} testCoverage={number|null} secretsFound={{file,line,pattern}[]} />` — consumed by Task 7 (`App.jsx`). Renders `null` when all three are empty/absent.

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/FindingsPanel.test.jsx`:
```javascript
import { render, screen } from "@testing-library/react";
import FindingsPanel from "./FindingsPanel";

test("renders nothing when there are no findings", () => {
  const { container } = render(<FindingsPanel warnings={[]} testCoverage={null} secretsFound={[]} />);
  expect(container.firstChild).toBeNull();
});

test("shows warnings when present", () => {
  render(<FindingsPanel warnings={["Missing AndroidManifest.xml"]} testCoverage={null} secretsFound={[]} />);
  expect(screen.getByText("Missing AndroidManifest.xml")).toBeInTheDocument();
  expect(screen.queryByText(/test coverage/i)).not.toBeInTheDocument();
});

test("shows test coverage and secrets when present", () => {
  render(
    <FindingsPanel
      warnings={[]}
      testCoverage={82.5}
      secretsFound={[{ file: "Constants.java", line: 42, pattern: "api_key" }]}
    />
  );
  expect(screen.getByText(/82\.5%/)).toBeInTheDocument();
  expect(screen.getByText(/Constants\.java:42/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx react-scripts test src/components/FindingsPanel.test.jsx --watchAll=false`
Expected: FAIL — `Cannot find module './FindingsPanel'`

- [ ] **Step 3: Implement FindingsPanel.jsx**

`frontend/src/components/FindingsPanel.jsx`:
```jsx
export default function FindingsPanel({ warnings, testCoverage, secretsFound }) {
  const hasWarnings = warnings && warnings.length > 0;
  const hasSecrets = secretsFound && secretsFound.length > 0;
  const hasCoverage = testCoverage !== null && testCoverage !== undefined;

  if (!hasWarnings && !hasSecrets && !hasCoverage) {
    return null;
  }

  return (
    <div className="border rounded p-4 space-y-3 bg-gray-50">
      <h3 className="font-medium">Findings</h3>
      {hasCoverage && (
        <p className="text-sm">
          Test coverage: <span className="font-semibold">{testCoverage}%</span>
        </p>
      )}
      {hasWarnings && (
        <div>
          <p className="text-sm font-medium text-yellow-700">Warnings</p>
          <ul className="list-disc list-inside text-sm text-yellow-700">
            {warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
      {hasSecrets && (
        <div>
          <p className="text-sm font-medium text-red-700">Potential secrets found</p>
          <ul className="list-disc list-inside text-sm text-red-700">
            {secretsFound.map((secret, index) => (
              <li key={index}>{secret.file}:{secret.line} ({secret.pattern})</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx react-scripts test src/components/FindingsPanel.test.jsx --watchAll=false`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/FindingsPanel.jsx frontend/src/components/FindingsPanel.test.jsx
git commit -m "feat: add FindingsPanel component for warnings/coverage/secrets"
```

---

### Task 6: StatsDisplay component

**Files:**
- Create: `frontend/src/components/StatsDisplay.jsx`
- Test: `frontend/src/components/StatsDisplay.test.jsx`

**Interfaces:**
- Consumes: `getDownloadUrl(downloadPath: string) -> string` (Task 2, `../services/api`).
- Produces: `<StatsDisplay stats={object} downloadUrl={string} />` — consumed by Task 7 (`App.jsx`).

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/StatsDisplay.test.jsx`:
```javascript
import { render, screen } from "@testing-library/react";
import StatsDisplay from "./StatsDisplay";

test("shows timing breakdown for each provided stat", () => {
  const stats = {
    ingest_time_ms: 100, analysis_time_ms: 200, scoring_time_ms: 300,
    generation_time_ms: 50, total_time_ms: 650,
  };
  render(<StatsDisplay stats={stats} downloadUrl="/api/reviews/abc-123/download" />);

  expect(screen.getByText(/Ingest: 100ms/)).toBeInTheDocument();
  expect(screen.getByText(/Total: 650ms/)).toBeInTheDocument();
});

test("renders a download link pointing at the constructed download URL", () => {
  render(<StatsDisplay stats={{}} downloadUrl="/api/reviews/abc-123/download" />);
  const link = screen.getByRole("link", { name: /download result/i });
  expect(link).toHaveAttribute("href", "http://localhost:8000/api/reviews/abc-123/download");
  expect(link).toHaveAttribute("download");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx react-scripts test src/components/StatsDisplay.test.jsx --watchAll=false`
Expected: FAIL — `Cannot find module './StatsDisplay'`

- [ ] **Step 3: Implement StatsDisplay.jsx**

`frontend/src/components/StatsDisplay.jsx`:
```jsx
import { getDownloadUrl } from "../services/api";

export default function StatsDisplay({ stats, downloadUrl }) {
  return (
    <div className="space-y-3">
      <h3 className="font-medium">Review Complete</h3>
      <ul className="text-sm text-gray-600 space-y-1">
        {stats.ingest_time_ms !== undefined && <li>Ingest: {stats.ingest_time_ms}ms</li>}
        {stats.analysis_time_ms !== undefined && <li>Analysis: {stats.analysis_time_ms}ms</li>}
        {stats.scoring_time_ms !== undefined && <li>Scoring: {stats.scoring_time_ms}ms</li>}
        {stats.generation_time_ms !== undefined && <li>Generation: {stats.generation_time_ms}ms</li>}
        {stats.total_time_ms !== undefined && <li className="font-medium">Total: {stats.total_time_ms}ms</li>}
      </ul>
      <a
        href={getDownloadUrl(downloadUrl)}
        download
        className="inline-block bg-green-600 text-white px-4 py-2 rounded"
      >
        Download Result
      </a>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx react-scripts test src/components/StatsDisplay.test.jsx --watchAll=false`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StatsDisplay.jsx frontend/src/components/StatsDisplay.test.jsx
git commit -m "feat: add StatsDisplay component with timing breakdown and download link"
```

---

### Task 7: App.jsx — wire the state machine together

**Files:**
- Create: `frontend/src/App.jsx`
- Test: `frontend/src/App.test.jsx`
- Delete: `frontend/src/App.js`, `frontend/src/App.css`, `frontend/src/App.test.js`, `frontend/src/logo.svg` (CRA boilerplate, replaced by the above)

**Interfaces:**
- Consumes: `UploadForm` (Task 3), `ProgressTracker` (Task 4), `FindingsPanel` (Task 5), `StatsDisplay` (Task 6), `createReview` (Task 2).
- Produces: the app's root component, rendered by `src/index.js` (already imports `./App` — CRA's webpack config resolves `.jsx`, no change needed there).

- [ ] **Step 1: Delete CRA boilerplate**

```bash
cd frontend
rm src/App.js src/App.css src/App.test.js src/logo.svg
```

- [ ] **Step 2: Write the failing tests**

`frontend/src/App.test.jsx`:
```javascript
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { createReview, getProgress } from "./services/api";

jest.mock("./services/api");

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

async function uploadValidFiles(user) {
  const zip = buildFile("project.zip", "application/zip");
  const xlsx = buildFile("template.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  await user.upload(screen.getByLabelText(/android project/i), zip);
  await user.upload(screen.getByLabelText(/review template/i), xlsx);
  await user.click(screen.getByRole("button", { name: /start review/i }));
}

test("full happy path: upload, poll, complete, download link, reset", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "completed", phase: "completed", progress: 100, message: "Done",
    stats: { total_time_ms: 500 }, download_url: "/api/reviews/abc-123/download", error: null,
    warnings: ["Missing AndroidManifest.xml"], test_coverage: 90.0, secrets_found: [],
  });

  render(<App />);
  await act(async () => {
    await uploadValidFiles(user);
  });
  await act(async () => {
    await Promise.resolve();
  });

  expect(screen.getByText(/review complete/i)).toBeInTheDocument();
  expect(screen.getByText("Missing AndroidManifest.xml")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /download result/i })).toHaveAttribute(
    "href",
    "http://localhost:8000/api/reviews/abc-123/download"
  );

  await user.click(screen.getByRole("button", { name: /start new review/i }));
  expect(screen.getByLabelText(/android project/i)).toBeInTheDocument();
});

test("shows an error message when review creation fails", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockRejectedValue(new Error("network error"));

  render(<App />);
  await act(async () => {
    await uploadValidFiles(user);
  });

  expect(screen.getByText(/failed to start review/i)).toBeInTheDocument();
});

test("shows an error message when the review itself fails during processing", async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  createReview.mockResolvedValue({ review_id: "abc-123", status: "processing" });
  getProgress.mockResolvedValue({
    status: "error", phase: "error", progress: 0, message: "Queued",
    stats: {}, download_url: null, error: "No source files found (.java/.kt)",
    warnings: [], test_coverage: null, secrets_found: [],
  });

  render(<App />);
  await act(async () => {
    await uploadValidFiles(user);
  });
  await act(async () => {
    await Promise.resolve();
  });

  expect(screen.getByText("No source files found (.java/.kt)")).toBeInTheDocument();
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npx react-scripts test src/App.test.jsx --watchAll=false`
Expected: FAIL — `Cannot find module './App'`

- [ ] **Step 4: Implement App.jsx**

`frontend/src/App.jsx`:
```jsx
import { useCallback, useState } from "react";
import UploadForm from "./components/UploadForm";
import ProgressTracker from "./components/ProgressTracker";
import FindingsPanel from "./components/FindingsPanel";
import StatsDisplay from "./components/StatsDisplay";
import { createReview } from "./services/api";

export default function App() {
  const [state, setState] = useState("idle"); // idle | uploading | polling | completed | error
  const [reviewId, setReviewId] = useState(null);
  const [progressData, setProgressData] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");

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

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold">Android Code Review Automation</h1>

      {(state === "idle" || state === "uploading") && (
        <UploadForm onSubmit={handleUpload} disabled={state === "uploading"} />
      )}

      {state === "polling" && reviewId && (
        <ProgressTracker reviewId={reviewId} onUpdate={handleProgressUpdate} />
      )}

      {progressData && (state === "polling" || state === "completed") && (
        <FindingsPanel
          warnings={progressData.warnings}
          testCoverage={progressData.test_coverage}
          secretsFound={progressData.secrets_found}
        />
      )}

      {state === "completed" && progressData && (
        <StatsDisplay stats={progressData.stats} downloadUrl={progressData.download_url} />
      )}

      {state === "error" && (
        <div className="space-y-3">
          <p className="text-red-600">{errorMessage}</p>
        </div>
      )}

      {(state === "completed" || state === "error") && (
        <button onClick={handleReset} className="text-blue-600 underline">
          Start New Review
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx react-scripts test src/App.test.jsx --watchAll=false`
Expected: PASS (3 passed). If the fake-timer/async interaction is flaky, add extra `await act(async () => { await Promise.resolve(); })` flushes — same known fiddly area as Task 4.

- [ ] **Step 6: Run the full frontend test suite**

Run: `cd frontend && CI=true npx react-scripts test --watchAll=false`
Expected: All tests PASS (17 tests: 3 api + 3 UploadForm + 3 ProgressTracker + 3 FindingsPanel + 2 StatsDisplay + 3 App)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.jsx frontend/src/App.test.jsx
git add -u frontend/src
git commit -m "feat: wire App.jsx state machine, remove CRA boilerplate"
```

---

### Task 8: Frontend Dockerfile and full-stack docker-compose.yml

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/.dockerignore`
- Create: `docker-compose.yml` (repository root)

**Interfaces:**
- Consumes: `frontend/package.json` (Task 1), `backend/Dockerfile` (already merged from the backend plan).
- Produces: a buildable frontend image and a working full-stack `docker-compose.yml`.

- [ ] **Step 1: Write the Dockerfile**

`frontend/Dockerfile`:
```dockerfile
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG REACT_APP_API_URL=http://localhost:8000/api
ENV REACT_APP_API_URL=$REACT_APP_API_URL
RUN npm run build

FROM node:20-slim
WORKDIR /app
RUN npm install -g serve
COPY --from=build /app/build ./build
EXPOSE 3000
CMD ["serve", "-s", "build", "-l", "3000"]
```

The `ARG`/`ENV` pair before `RUN npm run build` is required — CRA bakes `REACT_APP_*` values into the static bundle at build time, so this must happen before the build step, not as a container-runtime `environment:` entry (see Global Constraints).

- [ ] **Step 2: Write .dockerignore**

`frontend/.dockerignore`:
```
node_modules/
build/
.env
```

- [ ] **Step 3: Build the image to verify the Dockerfile is correct**

Run: `docker build -t android-review-frontend frontend/`
Expected: build completes successfully (exit code 0).

- [ ] **Step 4: Sanity-check the built image actually serves**

```bash
docker run --rm -d -p 3001:3000 --name frontend-sanity-check android-review-frontend
sleep 2
curl -s -o /dev/null -w "%{http_code}" http://localhost:3001
docker stop frontend-sanity-check
```

Expected: HTTP 200.

- [ ] **Step 5: Write docker-compose.yml**

`docker-compose.yml` (repository root):
```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_BASE=${OPENAI_API_BASE:-}
      - OPENAI_API_VERSION=${OPENAI_API_VERSION:-}
      - OPENAI_DEPLOYMENT_NAME=${OPENAI_DEPLOYMENT_NAME:-}
      - AZURE_OPENAI_KEY=${AZURE_OPENAI_KEY:-}
    networks:
      - review-network

  frontend:
    build:
      context: ./frontend
      args:
        REACT_APP_API_URL: http://localhost:8000/api
    ports:
      - "3000:3000"
    depends_on:
      - backend
    networks:
      - review-network

networks:
  review-network:
    driver: bridge
```

Note `frontend.build.args` (not `frontend.environment`) for `REACT_APP_API_URL` — this is the fix for the CRA build-time-vs-runtime env var gotcha documented in Global Constraints.

- [ ] **Step 6: Full-stack sanity check**

```bash
docker compose up -d --build
sleep 3
curl -s http://localhost:8000/api/health
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
docker compose down
```

Expected: health check returns `{"status":"ok",...}`, frontend returns HTTP 200. If `docker compose` (v2 syntax) is unavailable, try `docker-compose` (v1 syntax) instead — use whichever this environment has installed.

- [ ] **Step 7: Commit**

```bash
git add frontend/Dockerfile frontend/.dockerignore docker-compose.yml
git commit -m "chore: add frontend Dockerfile and full-stack docker-compose.yml"
```
