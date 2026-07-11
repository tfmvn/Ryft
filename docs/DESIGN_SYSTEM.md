# Ryft — Design System

A single visual language for the entire application. Every screen — dashboard,
panels, dialogs, diff viewer, command palette, status bar — is built from
these primitives. The implementation lives in `ryft/ui/theme/`.

Philosophy: **professional, minimal, information-dense.** Calm dark base,
one violet primary, restrained accents, generous structure. No gradients
begging for attention. Like Lazygit, btop, and gitui: you should be able to
read the whole project state at a glance.

---

## 1. Color palette

### Base (backgrounds)

| Token | Hex | Use |
|---|---|---|
| `bg.base` | `#0d1117` | app background (GitHub dark) |
| `bg.raised` | `#161b22` | panels, cards, toolbars |
| `bg.overlay` | `#1a1f28` | popovers, palette, inputs |
| `bg.inset` | `#010409` | code wells, diff gutters |

### Primary & secondary

| Token | Hex | Use |
|---|---|---|
| `violet` | `#ae80ff` | primary accent, focus, brand |
| `violet.dim` | `#7b5cb8` | secondary accent, inactive pills |
| `cyan` | `#79c0ff` | secondary info, links, files |
| `teal` | `#39d3c3` | AI / intelligence surfaces |

### Semantic status

| Token | Hex | Meaning |
|---|---|---|
| `success` / `mint` | `#56d364` | ok, added, done, online |
| `warning` / `amber` | `#e3b341` | caution, modified, pending |
| `danger` / `coral` | `#ff7b72` | error, deleted, offline, fail |
| `info` / `blue` | `#58a6ff` | informational |

### Text

| Token | Hex | Use |
|---|---|---|
| `text.hi` | `#f0f6fc` | headings, active values |
| `text.mid` | `#c9d1d9` | body |
| `text.dim` | `#6e7681` | labels, secondary |
| `text.ghost` | `#3d444d` | hairlines, disabled, separators |

### Diff

| Token | Hex | Use |
|---|---|---|
| `diff.add.bg` | `#0d2a16` | added-line wash |
| `diff.del.bg` | `#2a0d0d` | deleted-line wash |
| `diff.hunk.bg` | `#1a1830` | hunk-header wash |

---

## 2. Spacing scale

A 4px base unit (`u`). Never use ad-hoc margins.

```
1u = 4px   2u = 8px   3u = 12px   4u = 16px
5u = 20px  6u = 24px  8u = 32px
```

- Panel padding: `3u` (12px) internal, `2u` between panels.
- Gutter between list icon and text: `2u`.
- Section gap in a panel: `2u`.

---

## 3. Typography

Monospace everywhere (it's a terminal). One family, three weights.

| Role | Weight | Size | Example |
|---|---|---|---|
| Display (app title) | bold | 1.0× | `ryft` |
| Heading (panel title) | bold | 1.0× | `PROJECT` |
| Value | bold | 1.0× | `main` |
| Body | regular | 1.0× | file paths, messages |
| Label | regular | dim | `branch` |
| Micro (status bar) | regular | dim | hints |

Uppercase + letter-spacing for panel titles and section labels only. Body
text is sentence case.

---

## 4. Borders & corners

- **Hairline** `text.ghost` 1px for panel edges and tables.
- **Corner radius**: terminal boxes are square by default; rounded only for
  inputs/palette (`radius = 1` char of padding, not literally rounded).
- **Focus ring**: a `violet` left-border or `▍` marker on the focused panel.
- **Separators**: a single `text.ghost` rule, labeled when a section starts
  (`── branch ──`).

---

## 5. Icons & emoji policy

- **Icons**: a small curated glyph set in `ui/theme/components.py` (`_I`).
  Drawn from box-drawing / geometric unicode that renders on any font — **no
  Nerd Font dependency**. If a glyph can't render, it degrades to ASCII.
- **Emoji**: **avoid in the core UI.** Emoji are noisy, render inconsistently
  across terminals, and break alignment. Use them only in optional
  notifications the user can disable.
- Status is conveyed by **color + a single geometric glyph**, not emoji.

```
✓ ok   ✗ error   ⚑ warn   ● commit   ↑ push   ↓ pull
⟳ sync  ⬡ model  ◻ file   ◼ folder   ◆ insight   ▸ bullet
```

---

## 6. Components

All built on Rich + a thin `Box`/`Panel` helper. Defined once, reused
everywhere.

| Component | Spec |
|---|---|
| **Panel** | titled box, `bg.raised`, hairline border, `3u` padding, optional focus marker. |
| **KPI** | big `text.hi` value + `text.dim` label, used in dashboard. |
| **StatBar** | inline `label: value` row with semantic color. |
| **Table** | hairline rows, header in `text.dim`, zebra-free, key column `cyan`. |
| **Tree** | `├─ └─` connectors, dir `text.dim`, file `text.mid`, active `text.hi`. |
| **Bar** | progress bar, `violet` filled / `bg.overlay` track; pulse when indeterminate. |
| **Pill** | status chip: `text` on semantic bg (ok/warn/fail/inactive). |
| **Badge** | tiny tag for counts/versions. |
| **Diff viewer** | GitHub-style: line numbers, gutter, tinted bg, optional inline highlight. |
| **Command palette** | `bg.overlay` overlay, fuzzy filter, `↑↓` navigate, `↵` run, `esc` close. |
| **Confirm** | centered question, `Y/n`, never blocks non-interactive mode. |
| **Toast** | transient bottom-right note for background events. |
| **Empty state** | centered icon + one-line guidance + a suggested next command. |
| **Loading** | spinner (`dots`) + single violet line; never a blank screen. |

---

## 7. Motion & animation philosophy

- Animations are **functional, not decorative**: spinners show work; bars show
  progress; the palette fades in. No easing curves, no bouncing.
- Respect a terminal's low refresh: cap live updates at 12–15 fps.
- `prefers-reduced-motion` equivalent: if `TERM` is dumb or output is piped,
  render statically (no spinner, no live bar).

---

## 8. Keyboard model

Global, vim-flavored, documented in the status bar and `?` help.

| Key | Action |
|---|---|
| `Tab` / `Shift+Tab` | move focus between panels |
| `j` / `k` or `↑` / `↓` | move within a list panel |
| `:` or `Ctrl+P` | command palette |
| `g` then `d` | jump to dashboard; `g` then `g` → git; etc. |
| `?` | context help |
| `q` / `Esc` | back / close |
| `Ctrl+C` | stop current op (cooperative) |
| `Ctrl+Q` | quit |

Every screen shows its relevant hints in the status bar. No hidden shortcuts.

---

## 9. Status bar

Single line, `bg.raised`:

```
 branch  main   │  ⬡ qwen3   │  ⟳ 3 commits   │  ✗ ollama offline   │  ? help
```

Left = identity (project/branch), middle = live state (model, sync, workers),
right = hints. Never truncates aggressively — de-prioritize from the right.

---

## 10. Notification & error language

- **Errors**: `✗` + `text.mid` message + `text.dim` cause on the next line.
  Never blame the user. Always suggest a fix.
- **Warnings**: `⚑` + actionable note.
- **Success**: `✓` + terse confirmation; no celebration.
- **Toasts** (background): appear bottom-right, auto-dismiss in 4s, stack
  upward, never steal focus.
