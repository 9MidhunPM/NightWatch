---
name: NightWatch Public Showcase
description: Infrastructure Theatre with tangible worlds and precise evidence.
colors:
  mint: "#76dcb0"
  mint-hover: "#9aebc5"
  amber: "#eab970"
  coral: "#f47d7a"
  charcoal: "#0b1215"
  silver-text: "#eef4f2"
  muted-text: "#acbbb9"
  divider: "#34464a"
  action-ink: "#10281e"
typography:
  display:
    fontFamily: "Manrope Variable, Arial, sans-serif"
    fontSize: "clamp(65px, 7.3vw, 112px)"
    fontWeight: 650
    lineHeight: 1.025
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "Manrope Variable, Arial, sans-serif"
    fontSize: "clamp(30px, 3.4vw, 48px)"
    fontWeight: 550
    lineHeight: 1.2
    letterSpacing: "-0.035em"
  title:
    fontFamily: "Manrope Variable, Arial, sans-serif"
    fontSize: "25px"
    fontWeight: 550
    lineHeight: 1.3
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Manrope Variable, Arial, sans-serif"
    fontSize: "12px"
    lineHeight: 1.9
  label:
    fontFamily: "Manrope Variable, Arial, sans-serif"
    fontSize: "11px"
rounded:
  control: "7px"
  media: "12px"
  circular: "50%"
spacing:
  inline: "10px"
  compact: "12px"
  content: "20px"
  roomy: "24px"
  column: "40px"
components:
  button-primary:
    backgroundColor: "{colors.mint}"
    textColor: "{colors.action-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "14px 20px"
  button-primary-hover:
    backgroundColor: "{colors.mint-hover}"
  button-outline:
    textColor: "#d9e5dd"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "14px 20px"
  button-outline-hover:
    backgroundColor: "#1b2b24"
  operator-link:
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  recorded-media:
    backgroundColor: "{colors.charcoal}"
    rounded: "{rounded.media}"
---

# Design System: NightWatch Public Showcase

## Overview

**Creative North Star: "Infrastructure Theatre"**

Infrastructure Theatre makes the public NightWatch showcase feel like a precise instrument surrounding a tangible world. Charcoal surfaces, mint signals, faceted rock, greenery, and silver equipment connect the interface to the infrastructure it describes. Spacious reading pauses balance the sculptural scene with measured, evidence-oriented panels.

This system applies to the public root showcase only. The private operator console and login retain their incumbent typography, controls, and density. Within the showcase, simulation labels, recorded-media captions, visible focus, and a complete linear fallback are part of the visual contract.

**Key Characteristics:**

- Sculptural infrastructure with precise, quiet interface framing.
- One variable sans-serif family with a large, closely spaced display tier.
- Mint continuity, contextual amber and coral, and layered charcoal surfaces.
- Native scrolling, restrained state transitions, and readable static fallbacks.

## Colors

A cool charcoal foundation supports silver reading text, a continuous mint accent, and restrained contextual warmth.

### Primary

- **Watchlight Mint:** Identity, primary calls to action, selected capability tabs, focus outlines, checks, and illuminated scene connections.
- **Mint Hover:** The lighter response of primary action surfaces.

### Secondary

- **Evidence Amber:** Investigation-stage cues and the award marker.
- **Incident Coral:** Failure-stage numbering and the first failed observation.

### Neutral

- **Theatre Charcoal:** Page foundation, scene fog, image framing, and vignette integration.
- **Silver Text:** The inherited foreground for public content.
- **Muted Text:** Supporting paragraphs before local contrast adjustments.
- **Measured Divider:** Shared capability and source-strip separators.
- **Action Ink:** Dark text on the mint primary action.

The frontmatter is normative for color values. Scene materials also use rock, foliage, and metal shades; those belong to the diorama rather than to the interface palette.

### Named Rules

**The Mint Thread Rule.** Mint connects identity, primary actions, selected tabs, keyboard focus, and healthy or verified story cues. Amber and coral add contextual signals, including investigation, failure, and award evidence, without replacing the primary accent.

## Typography

**Display Font:** Manrope Variable, with Arial and sans-serif fallbacks.
**Body Font:** Manrope Variable, with the same fallbacks.

**Character:** The same family moves from large, closely spaced statements to compact factual labels. Variable weights produce a measured hierarchy without a separate decorative or monospaced face.

### Hierarchy

- **Display:** The largest tier uses the frontmatter display recipe. Tablet rendering uses an explicit larger fixed size; the mobile recipe is a responsive clamp (48px to 78px) with looser leading (1.1).
- **Headline:** Balanced section headings follow the headline recipe. Story headings use a closely related clamp (30px to 46px), stronger weight (600), and leading (1.18).
- **Title:** Capability titles use the title recipe, shifting to compact mobile titles (24px).
- **Body:** Most product and engineering explanations use compact text with generous leading. Introductory and incident copy may grow to 13px or 15px; typical desktop reading widths are 270px to 390px.
- **Label:** Navigation, tabs, and section identifiers use the compact label tier. Weights vary by role; primary actions are emphatic (750). Small media captions remain subordinate and are not a general body-text scale.

### Named Rules

**The One Family Rule.** Use Manrope Variable throughout the public showcase. Establish hierarchy through size, weight, spacing, and line height rather than introducing another typeface.

## Layout

Use a centered content container capped at 1376px with desktop side gutters of 56px. The observed responsive gutters step to 40px, 32px, and 20px as the viewport narrows. Copy stays narrower than its accompanying visual region; product, engineering, and build content use paired columns before stacking.

Recurring internal spacing uses the frontmatter steps, while the public sections keep broad vertical pauses of roughly 65px to 115px. On tablet, supporting copy can use two columns within a stacked section. At 700px and below, reading blocks become linear and actions can wrap; capability tabs remain a horizontally scrollable row.

The desktop header is sticky (84px), then reduces to 74px and 68px at narrower widths. Anchor targets preserve a scroll margin (95px) so navigation does not cover their headings. Large scene motion is reserved for fine-pointer desktop viewports at least 1024px wide; other visitors receive the poster and linear chapter layout.

## Elevation & Depth

The public interface uses tonal layering and thin borders, with no box-shadow vocabulary. Its physical depth comes from faceted islands, grounded equipment, cast scene shadows, a restrained vignette, and deliberate overlap between the diorama and reading region. Buttons lift subtly on hover (2px); ordinary information panels stay still.

### Named Rules

**The Grounded Depth Rule.** Let the diorama carry sculptural depth. Reading surfaces use tonal separation and thin borders; their default treatment does not add box shadows.

## Shapes

Controls have gently curved corners; recorded screenshots and result media use a softer media radius. The architecture panel is a slightly more enclosed variation (14px). Small circles belong to status dots, window markers, and the play control; they do not turn reading containers into pills.

One-pixel rules organize tabs, evidence, disclosure rows, and service boundaries. Scene forms retain their native faceted rock, softened server boxes, cylinders, arches, and connecting curves rather than inheriting a flat-interface radius.

## Components

### Buttons

Confident, compact actions keep the sculptural scene dominant.

- **Primary:** Mint surface, dark action text, control radius, and the frontmatter padding. Hover lightens the surface and lifts it slightly.
- **Outline:** A quiet bordered alternative for operator entry, with a darker tonal hover fill.
- **Focus:** Mint outline (2px) separated from the control by a clear offset (5px).
- **Responsive:** Mobile actions reduce padding (12px 16px), text (10px), and icon gap, and may wrap naturally.

### Navigation

A quiet sticky header pairs the mint mark and compact wordmark with understated anchor links. Links brighten to mint on hover. Operator entry is bordered rather than competing with the primary action. The mobile menu uses a native button with visible expanded state, then exposes a vertical list beneath the header.

### Capability Tabs

A horizontal reading index uses compact labels and a thin divider. Selection brightens the label and adds a mint underline (2px). Roving focus, left/right arrows, Home, and End operate the tab sequence; every selected tab remains connected to its panel. Tabs scroll horizontally instead of shrinking their labels.

### Recorded Media

Rounded screenshot frames combine a quiet window bar, the actual image, and a visible recorded-state caption. The frame establishes context without imitating live telemetry. Result graphics and badge photographs retain their full evidence through contain fitting; ordinary photographic context can use cover fitting.

### Evidence Rows

Compact definition lists align descriptive labels left and observed values right. Horizontal rules contain the group, tabular numbering keeps chapter markers steady, and a contextual status color highlights the failed value. Simulation labeling stays visible beneath the evidence.

### Engineering Disclosures

Native disclosure rows expose technical depth without making a dense wall of text. A thin rule separates each row; the plus icon turns when the item opens. Keyboard focus uses the same mint outline as other controls, while the descriptive text keeps generous leading.

### Infrastructure Diorama

Repeated silver server forms and cylindrical database tiers sit on rock-and-greenery islands. Mint routes become coral during the illustrative fault sequence, then return to mint. Camera movement follows native scroll progress with a short scrub response; pointer movement adds slight perspective. The poster remains available during loading, reduced motion, unavailable WebGL, and scene failure.

## Do's and Don'ts

### Do:

- **Do** keep these rules scoped to the public showcase.
- **Do** preserve mint across identity, actions, selection, and visible keyboard focus.
- **Do** keep reading columns narrow beside larger media regions and retain generous section spacing.
- **Do** identify illustrative scene evidence and recorded product images in visible text.
- **Do** preserve full result graphics and badge imagery with contain fitting where cropping would remove evidence.
- **Do** keep navigation, tabs, and disclosures usable by keyboard, and provide the linear poster-based experience for reduced motion and smaller screens.

### Don't:

- **Don't** apply this showcase's display scale or spacing to the private operator console.
- **Don't** make a successful canvas load or animation a prerequisite for reading the product narrative.
- **Don't** present a simulated status color or recorded screenshot as current infrastructure health.
- **Don't** add box shadows to ordinary reading panels when the existing tonal and border treatment already supplies separation.
- **Don't** turn individual camera coordinates, material variations, or image-placement measurements into global design tokens.
