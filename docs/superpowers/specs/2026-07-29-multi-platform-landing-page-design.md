# Multi-Platform Landing Page & Navigation — Design Spec

**Status:** Approved
**Date:** 2026-07-29
**Source:** "extend this solution to more platforms e-g iOS, .net, web (react)... start with main landing page to select the desired stack... for Android, direct the user to current flow, for other platform, show similar view but we'll work on them later, work on navigation part as for now... on subpage, add option to navigate back to home landing page... on landing page, add an option to select LLM (azure open AI paid vs ollama local model) — will work on it later for it to be workable, as for now just show this selection and persist it"

## Purpose

The tool has so far only reviewed Android projects. This round scaffolds the frontend to support multiple platforms (Android, iOS, .NET, Web/React) behind a shared landing page, without building out iOS/.NET/Web review functionality yet — that's future work. This round is navigation and layout only: a landing page to pick a platform (and, separately, an LLM provider), real URL-based routing between pages, and a "coming soon" placeholder for every platform except Android, which routes straight into the existing, fully-working review flow.

## Out of Scope

- Any actual iOS/.NET/Web review logic (upload handling, backend endpoints, scoring) — those platforms get a disabled, non-functional form only.
- Making the LLM provider selection functional — Azure OpenAI remains the only provider the backend actually calls. This round only captures and persists the user's choice in the browser.
- Any backend changes at all — this is a frontend-only round.

## 1. Routing architecture

Adds the `react-router-dom` dependency (the standard React routing library — real URLs per page, working browser back/forward, bookmarkable links; the alternative of extending the existing internal state-string pattern was considered and rejected since this is now genuinely a multi-page app).

Two routes:
- `/` → `HomePage`
- `/review/:platform` → `ReviewPage`, a dispatcher: if `platform === "android"`, renders `AndroidReviewFlow` (the existing, fully-working review flow, extracted — see Section 4); for any other value present in the platform config (Section 2), renders `PlaceholderReviewFlow` (Section 5); for a `platform` value not present in the config at all, redirects to `/` via `<Navigate to="/" replace />`.

`App.jsx` becomes purely the router shell:

```jsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import HomePage from "./pages/HomePage";
import ReviewPage from "./pages/ReviewPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/review/:platform" element={<ReviewPage />} />
      </Routes>
    </BrowserRouter>
  );
}
```

`HomePage` and `ReviewPage` live under a new `frontend/src/pages/` directory (page-level components, as distinct from the existing `frontend/src/components/` directory of reusable pieces).

## 2. Platform config (single source of truth)

New `frontend/src/platforms.js`:

```js
export const PLATFORMS = [
  { id: "android", label: "Android", available: true },
  { id: "ios", label: "iOS", available: false },
  { id: "dotnet", label: ".NET", available: false },
  { id: "web", label: "Web (React)", available: false },
];
```

Both `HomePage` (rendering the four cards) and `ReviewPage` (looking up the label for the current `:platform` param, and validating it's a known id) read from this single list. Adding a fifth platform later, or flipping `available` to `true` once a platform's review flow is built, is a one-line change here — nothing else needs to change.

## 3. Home page

`HomePage` renders:
- A page title/intro (reusing the existing header style: `--font-heading`, same sizing as today's `<h1>`).
- Four platform cards in a grid, one per `PLATFORMS` entry, each a `.card.blueprint` (matching the existing card style throughout the app) wrapped in a react-router `<Link to={`/review/${platform.id}`}>`. All four are clickable regardless of `available` — clicking a not-yet-available platform navigates to its placeholder page (Section 5), which is the whole point of previewing the eventual shape.
- Below the platform cards, an "LLM provider" section: a two-button toggle (visually matching the existing Report/Debug toggle pattern in `AndroidReviewFlow.jsx`) with options "Azure OpenAI" and "Ollama (local)". The selected option is highlighted (`btn-primary`), the other plain (`btn`).

Persistence: a new `frontend/src/services/llmProviderStorage.js`:

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

`HomePage` reads the stored value on mount (via `useState(() => getLlmProvider())`) and calls `setLlmProvider` whenever the user clicks a toggle option, updating local state so the highlighted button updates immediately. Nothing downstream reads this value yet — it round-trips through `localStorage` and back, which is the entire scope of "persist it" for this round.

## 4. Extracting the existing Android flow

The current `frontend/src/App.jsx` (the full upload → progress → report state machine, unchanged in every other respect) is renamed to `frontend/src/pages/AndroidReviewFlow.jsx`. The only functional change: its `<nav className="nav"><span className="nav-brand">...</span></nav>` markup is replaced with the new shared `<TopNav />` component (see Section 5 for its definition — introduced here, not there, since this is the first flow to need it):

```jsx
<TopNav />
```

Everything else in the file — state machine, upload handling, progress polling, the Report/Debug toggle, all of it — is untouched.

The existing `frontend/src/App.test.jsx` content (the full happy-path/error-path test suite) moves to `frontend/src/pages/AndroidReviewFlow.test.jsx` verbatim, updating only the import (`import AndroidReviewFlow from "./AndroidReviewFlow";` and rendering `<AndroidReviewFlow />` instead of `<App />`) and wrapping renders in a `<MemoryRouter>` (required now that the component contains a react-router `<Link>`).

## 5. Placeholder flow for iOS / .NET / Web

New shared `frontend/src/components/TopNav.jsx` (no props — always the same brand + home link, since every page other than the home page itself needs exactly this):

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

(Making the brand itself a home link too, alongside an explicit "← Home" button, since both are common conventions and neither costs anything extra.)

New `frontend/src/pages/PlaceholderReviewFlow.jsx`, taking a `platform` prop (`{ id, label }` from the config):

- `<TopNav />` (the same shared component `AndroidReviewFlow` now uses — see Section 4).
- A header reading `{platform.label} Code Review Automation` (matching the pattern of the Android flow's header once a project name is known — see the existing `project_name` header behavior — except here it's always the platform label, never a live project name, since no review ever actually runs).
- A banner card: kicker "Coming soon", title `"{platform.label} support is on the way"`, body text noting the review flow will work the same way once it ships.
- The existing `UploadForm` component, rendered with `disabled` and a new `disabledLabel="Coming soon"` prop.

`UploadForm.jsx` gains the `disabledLabel` prop (default `"Starting review…"`, preserving today's in-progress-upload behavior exactly):

```jsx
export default function UploadForm({ onSubmit, disabled, disabledLabel = "Starting review…" }) {
  // ...
  {disabled ? disabledLabel : "Start review"}
  // ...
}
```

`onSubmit` is never called on this page (the form is disabled and its inputs are inert), so no submit handler is wired — `PlaceholderReviewFlow` passes a no-op.

## 6. `ReviewPage` dispatcher

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

A new `App.test.jsx` covers routing behavior only (rendered with `<MemoryRouter initialEntries={[...]}>`):
- `/` renders the home page's platform cards and LLM toggle.
- `/review/android` renders the Android flow (e.g., the upload form's "Start review" button).
- `/review/ios` (and `.NET`/`web`) renders the placeholder banner and a disabled form.
- `/review/nonsense` redirects to `/`.

## Testing

- **`platforms.js`**: no dedicated test — it's static data, exercised indirectly through `HomePage`/`ReviewPage` tests.
- **`llmProviderStorage.js`**: new unit test — `getLlmProvider` defaults to `"azure"` when nothing is stored, returns a previously-stored value otherwise; `setLlmProvider` writes to `localStorage` under the expected key.
- **`HomePage.test.jsx`**: renders four platform links pointing at the right hrefs; LLM toggle defaults to Azure highlighted; clicking Ollama persists the change (verified by re-reading `localStorage` or by remounting and checking the toggle state).
- **`PlaceholderReviewFlow.test.jsx`**: renders the platform's label in the banner and header; the upload form's file inputs and submit button are disabled; the "← Home" link points at `/`.
- **`AndroidReviewFlow.test.jsx`**: the existing `App.test.jsx` suite, moved verbatim (see Section 4), plus one addition: a "← Home" link is present and points at `/`.
- **`App.test.jsx`**: new, routing-only tests as described in Section 6.

## Ambiguity resolved during self-review

- "Show similar view" for non-Android platforms was resolved via clarifying question to mean the full (disabled) upload form, not a bare coming-soon message — this previews the eventual shape of each platform's page.
- The LLM provider default (when nothing is yet in `localStorage`) is `"azure"`, matching the backend's current sole provider — so a fresh browser shows the toggle already reflecting how the app actually behaves today.
