# Clickable Warnings/Secrets Popup Design Spec

**Status:** Approved
**Date:** 2026-07-31

## Purpose

On the completed-review screen (`StatsDisplay.jsx`), the `{n} warnings` / `{n} secrets`
tag badges currently show only a count with no way to see the actual list from that
screen. Tapping either tag should open a popup dialog listing the real warnings/secrets.

## Scope

- `StatsDisplay.jsx`'s two `tag-outline` badges only.
- Not in scope: `FindingsPanel.jsx`'s existing inline click-to-expand cards (Warnings,
  Secrets found, Lint issues), which are unchanged.

## Design

Replace the two plain `<span className="tag tag-outline">` badges with a `<button>`
carrying the same `tag tag-outline` class (border/background/font reset via inline
style so it renders identically to the current span, gaining only a pointer cursor)
when the corresponding list is non-empty. At count 0 the badge stays a plain,
non-interactive `<span>` — nothing to show.

Clicking a badge opens a popup dialog, reusing the exact `dialog-backdrop` /
`dialog` / `dialog-title` / `dialog-body` / `dialog-actions` CSS classes already
used by the existing "Performance breakdown" popup in the same file (click-outside
via the backdrop's `onClick`, `event.stopPropagation()` on the inner dialog, a
"Close" button in `dialog-actions`).

Dialog content:
- Warnings dialog: `<ul>` of warning strings, one `<li>` per warning — same
  rendering `FindingsPanel` already uses for its inline warnings list.
- Secrets dialog: `<ul>` of `{secret.file}:{secret.line} ({secret.pattern})`,
  one `<li>` per secret — same format `FindingsPanel` already uses for its
  inline secrets list.

## State

Consolidate the existing `showPerf` boolean into a single `activeDialog` state:
`null | "performance" | "warnings" | "secrets"`. Only one dialog can be open at a
time; the existing "Performance breakdown" button now sets `activeDialog` to
`"performance"` instead of `showPerf` to `true`, with no behavior change for it.

## Testing

Extend `StatsDisplay.test.jsx`:
- Clicking the warnings tag when warnings exist opens a dialog listing every warning.
- Clicking the secrets tag when secrets exist opens a dialog listing every secret in
  `file:line (pattern)` format.
- At count 0, the badge is a plain `<span>`, not a button, and there is nothing to
  click.
- The existing "Performance breakdown" dialog still opens/closes correctly after the
  `showPerf` → `activeDialog` refactor.
- Only one dialog is visible at a time (opening one closes any other, since
  `activeDialog` holds a single value).
