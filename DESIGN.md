---
version: alpha
name: Copia
description: A focused dark workspace for a personal multi-provider AI assistant.
colors:
  primary: "#7b6ef6"
  primary-hover: "#8b80ff"
  on-primary: "#101014"
  canvas: "#101014"
  surface: "#16161c"
  surface-raised: "#1c1c24"
  surface-inset: "#181820"
  surface-accent: "#28243d"
  text-primary: "#f3f3f6"
  text-secondary: "#afafb9"
  text-muted: "#858592"
  border: "#2a2a36"
  border-strong: "#343440"
  success: "#10b981"
  danger: "#fb7185"
  warning: "#f5b942"
  focus: "#b4aaff"
typography:
  display:
    fontFamily: Source Sans 3
    fontSize: 28px
    fontWeight: 700
    lineHeight: 1.2
  heading:
    fontFamily: Source Sans 3
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.3
  body-md:
    fontFamily: Source Sans 3
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.55
  body-sm:
    fontFamily: Source Sans 3
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: 600
    lineHeight: 1.3
  telemetry:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: 400
    lineHeight: 1.5
rounded:
  compact: 4px
  control: 6px
  panel: 10px
  dialog: 14px
  pill: 999px
spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
components:
  primary-button:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.control}"
    padding: 10px
    height: 40px
  primary-button-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.on-primary}"
  secondary-button:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.control}"
    padding: 8px
---

## Overview

Copia is a personal workspace for continuing conversations, choosing an AI provider, configuring agents, and reviewing the tools or memory that affect a task. The primary user works in this interface repeatedly, so the design favors clear state, compact controls, and readable conversation content over a marketing dashboard. The dark neutral canvas and restrained violet accent continue the existing product direction.

Visual choices should make provider selection, data context, agent activity, and approval requests easy to inspect. Local storage in Copia does not mean a request to a selected remote provider is processed locally; interface copy must keep that distinction clear.

## Colors

Use the canvas for the full workspace background. Surfaces distinguish navigation, raised panels, inset editors, and selected states without adding a border or card around every group. Primary violet marks the main action or selected control. Use the darker `on-primary` text on violet action fills to keep button labels readable. Reserve success, warning, and danger colors for statuses and their related actions.

Primary and hover colors are calibrated for dark action labels. Text on dark surfaces uses primary or secondary text. Muted text is for supporting metadata; do not use it for essential instructions or controls. Borders separate adjacent regions and should remain quieter than text.

## Typography

Source Sans 3 is the default reading face for messages, forms, and screen headings. Inter is used sparingly for compact interface labels. JetBrains Mono is reserved for token counts, technical metadata, endpoints, and identifiers. If a web font is unavailable, fall back to the system sans-serif or monospace stack without changing layout or meaning.

Conversation content uses a comfortable 15px size and about 1.55 line height. Dense metadata may use 10–12px, but actions, errors, and explanatory text should remain easy to read at normal zoom.

## Layout

The desktop workspace uses a 260px navigation rail and a flexible conversation area. Conversation content stays near 720px wide for long-form reading. Supporting screens use a constrained central column or a compact grid sized for the task: roughly 760px for invariants, 840px for MCP setup, and up to 900px for scheduled summaries. Profile cards may use three columns on wide screens and collapse as the viewport narrows.

The interface must remain usable from 320px wide. Around 900px, reduce multi-column density; around 680px, stack MCP setup fields, wrap task controls, and keep dialogs within the viewport. Keep compact spacing within related controls and use wider gaps between separate task areas. Preserve enough message width for readable paragraphs and allow tables or code to scroll horizontally when needed.

## Elevation & Depth

Use borders and subtle surface changes as the default separation. Reserve shadows for overlays, dialogs, and controls that float above the workspace. Avoid decorative glow and large ambient gradients; a depth effect must explain layering or interaction.

## Shapes

Use compact radii for fields and small controls, medium radii for panels, and larger radii for dialogs. Pill shapes are for short status tags or compact toggles only. Avoid wrapping each piece of content in a rounded card when spacing or a divider communicates the grouping more clearly.

## Components

Give each screen one visually clear primary action. Secondary actions use neutral surfaces; destructive actions use the danger role and require a clear label. Show loading, empty, error, retry, approval, and success states near the control or data they describe. Preserve the result and consequence of agent or MCP actions in the conversation and task views.

All controls must have a visible keyboard focus ring with at least 2px thickness. Maintain logical keyboard order, visible labels or accessible names, and semantic status announcements. Respect reduced-motion preferences. Verify text contrast against its actual surface; the primary button label uses `on-primary`, and muted text is not a substitute for body copy.

## Do's and Don'ts

- Do show real provider, task, memory, connection, and session state where it changes the user's next action.
- Do keep error and retry feedback attached to the operation that failed.
- Do use the violet accent for a clear action or selected state, not as a decorative background.
- Do keep saved conversation history and the active conversation easy to distinguish.
- Don't add a generic dashboard hero, fabricated metrics, or unsupported product promises.
- Don't use gradients, shadows, icons, or cards only to make a screen look more elaborate.
- Don't hide focus, loading, failure, empty, or approval states to make a screen look cleaner.
- Don't describe provider requests as local processing unless the selected provider actually runs locally.
