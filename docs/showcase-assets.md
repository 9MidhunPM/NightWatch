# Showcase assets

[Documentation index](README.md) · [← README](../README.md) · [Public showcase](public-showcase.md) · [Design system](../DESIGN.md)

The public showcase uses three kinds of visual evidence: recorded product screenshots, genuine hackathon material, and synthetic infrastructure artwork. Keep those distinctions in filenames, alt text, visible captions, and future updates. A recorded console image does not report current health, and an illustrative connection does not prove an application dependency.

The committed derivatives live in [frontend/public/showcase/](../frontend/public/showcase/). [ASSET_NOTES.md](../frontend/public/showcase/ASSET_NOTES.md) records their optimization settings, provenance, privacy inspection, dimensions, and byte sizes. Original product captures remain in [docs/screenshots/](screenshots/); original event material remains in [docs/hackathon/](hackathon/). Do not replace those originals with a compressed derivative.

## Evidence and recording provenance

The [README](../README.md) describes the product screenshots as captures made with Playwright MCP against the authenticated production application. The public gallery selects four of the six README captures. These are historical recordings of the actual console, including its rendered conversations, resource identifiers, observations, and operation results. Dates shown inside an incident image are recorded incident times; they do not establish an image capture time or current state.

| Source class | Files | What they establish |
| --- | --- | --- |
| Recorded product UI | `world-3d`, `incident-timeline`, `agent-investigation`, `agent-deployment` | What the console displayed in the captured session. Their presence on a public page does not create a live integration. |
| Genuine photographs | `codex-hackathon-calicut-builders`, `midhun-builder-badge` | The supplied event scene and Midhun P M's builder badge. |
| Supplied result graphic | `top-three-winners` | The event's published top-three result graphic; this is a graphic, not a photograph or generated award claim. |
| Synthetic concept artwork | `islands-poster`, `nightwatch-social` | The Infrastructure Theatre visual direction and static/social presentation; not a screenshot or telemetry snapshot. |

The event caption source is the README's Hackathon Award section: **Second Prize — Codex Community Hackathon Calicut**, held at **TinkerSpace on 19–20 September 2026**. The result graphic names M. Mohith's Kea first, Midhun P M's NightWatch second, and Mohammed Shaad N's Loop third. Preserve the creator's name exactly as **Midhun P M** in authored copy.

The five-chapter incident story in [showcase-content.ts](../frontend/lib/showcase-content.ts) is separate from these recorded images. Its HTTP 502, ports 8000/9999, approval, and illustrative HTTP 200 are a representative simulation. Do not imply that the selected incident screenshot records that complete simulated repair sequence; it shows its own recorded failure and subsequent checks.

## Derivative manifest

The values below describe the committed image files, not the browser's responsive Next.js image variants. Combined encoded size is **904,482 bytes (883.3 KiB)** across nine images.

| Public derivative | Original/source | Dimensions | Bytes | Encoding recipe |
| --- | --- | --- | ---: | --- |
| [world-3d.webp](../frontend/public/showcase/world-3d.webp) | [world-3d.png](screenshots/world-3d.png) | 1600 × 960 | 67,532 | WebP, quality 82; max width 1600. |
| [incident-timeline.webp](../frontend/public/showcase/incident-timeline.webp) | [incident-timeline.png](screenshots/incident-timeline.png) | 1585 × 1082 | 51,322 | WebP, quality 82; max width 1600. |
| [agent-investigation.webp](../frontend/public/showcase/agent-investigation.webp) | [agent-investigation.png](screenshots/agent-investigation.png) | 1600 × 960 | 72,320 | WebP, quality 82; max width 1600. |
| [agent-deployment.webp](../frontend/public/showcase/agent-deployment.webp) | [agent-deployment.png](screenshots/agent-deployment.png) | 1600 × 960 | 56,898 | WebP, quality 82; max width 1600. |
| [codex-hackathon-calicut-builders.webp](../frontend/public/showcase/codex-hackathon-calicut-builders.webp) | [builders JPEG](hackathon/codex-hackathon-calicut-builders.jpeg) | 960 × 1280 | 170,158 | WebP, quality 84; max width 1400. |
| [midhun-builder-badge.webp](../frontend/public/showcase/midhun-builder-badge.webp) | [badge JPEG](hackathon/midhun-builder-badge.jpeg) | 1204 × 1600 | 145,048 | WebP, quality 84; max width 1400. |
| [top-three-winners.webp](../frontend/public/showcase/top-three-winners.webp) | [result JPEG](hackathon/top-three-winners.jpeg) | 1024 × 1536 | 67,104 | WebP, quality 84; max width 1400. |
| [islands-poster.webp](../frontend/public/showcase/islands-poster.webp) | Built-in imagegen concept artwork | 1536 × 1024 | 140,608 | WebP, quality 86; max width 1536. |
| [nightwatch-social.jpg](../frontend/public/showcase/nightwatch-social.jpg) | Same generated artwork as the poster | 1200 × 630 | 133,492 | JPEG, quality 88; centre cover crop. |

The width-limited transforms preserve aspect ratio and do not enlarge smaller originals. The social preview intentionally uses a fixed crop instead. The original preparation used Sharp's orientation-aware rotation before resizing and encoding. Sharp's default output behavior strips embedded metadata; the committed derivatives contain no EXIF, XMP, or IPTC metadata.

The poster was made with the built-in imagegen tool. Its concise prompt is: **Three floating infrastructure islands with silver server towers, charcoal surroundings, mint light and connections, no text.** The live public canvas is a separately authored Three.js scene; the poster remains its loading and static fallback. The JPEG preview is artwork derived from that poster, not a recording of the canvas.

## Alt text, captions, and fitting

The exact gallery alt strings and capability names are maintained in [showcase-content.ts](../frontend/lib/showcase-content.ts). [ProductExplorer](../frontend/components/showcase-interactions.tsx) renders the caption as `<capability label> · Recorded screenshot, not current telemetry` and adds **Recorded product view** to the frame's window bar. Every panel also offers **Open recorded screenshot** for the full derivative.

| Gallery image | Capability label | Current alt text |
| --- | --- | --- |
| `world-3d.webp` | World & telemetry | Recorded NightWatch infrastructure world with project islands and service connections |
| `incident-timeline.webp` | Investigation & incidents | Recorded NightWatch incident timeline showing failure observations and recovery checks |
| `agent-investigation.webp` | Agent & approvals | Recorded NightWatch agent investigation with evidence citations |
| `agent-deployment.webp` | Deployments & operations | Recorded NightWatch deployment plan and independently checked HTTP response |

Event alt text is defined in [the root page](../frontend/app/page.tsx):

| Event image | Current alt text | Caption/context |
| --- | --- | --- |
| `top-three-winners.webp` | Event result graphic naming Midhun P M’s NightWatch as Second Prize at Codex Community Hackathon Calicut | “The event result graphic. Calicut, September 2026.” |
| `codex-hackathon-calicut-builders.webp` | Builders working together at the Codex Community Hackathon at TinkerSpace | No separate figure caption; the adjacent event story supplies venue, dates, and award context. |
| `midhun-builder-badge.webp` | Midhun P M’s Codex Community Hackathon builder badge | No separate figure caption; the adjacent event story identifies the creator and event. |

[showcase.css](../frontend/app/showcase.css) uses contain fitting for the result graphic and badge so their evidence stays visible. The builders photograph uses cover fitting for its context image. Product screenshots scale proportionally rather than being cropped to hide content.

The poster has empty alt text inside the decorative, `aria-hidden` stage in [ShowcaseStage](../frontend/components/showcase-stage.tsx). Its visible stage labels distinguish **An illustrative infrastructure world** and **Representative incident simulation**, while meaningful incident evidence remains outside the decorative stage in ordinary HTML. The social preview's Open Graph alt is **NightWatch infrastructure world and evidence-backed operations**, defined with its 1200 × 630 dimensions in [root metadata](../frontend/app/layout.tsx).

## Privacy boundary

ASSET_NOTES records a source-resolution visual inspection of every selected screenshot and event asset before public optimization. That inspection identified no visible passphrase, authentication token, API key, or credential. Public domains, project names, resource identifiers, conversation text, and a plan identifier remain visible in the product images, as they already do in the README source images. People and published event details remain visible in the supplied photographs.

That review describes the current selections. New captures need their own review, including expanded evidence drawers, chat context, logs, browser chrome, and metadata. Removing EXIF or XMP does not remove a secret rendered into pixels. Preserve the original privately when a future image needs redaction, and document the redaction in the public derivative's provenance rather than silently presenting edited evidence as an untouched capture.

## Updating an asset

1. Establish the source class and recording context. For a fresh product capture, record the application URL, capture date, displayed state, and any redaction. For event media, retain its supplied provenance; for generated art, retain the tool and prompt. Do not infer missing capture details from an incident timestamp.
2. Inspect the full-resolution source for visible credentials and unintended private content before copying it into a public path. Keep public evidence labels and the historical/current-state distinction accurate.
3. Generate a new derivative using the manifest's encoding recipe and orientation-aware transform. Preserve originals, avoid upscaling, and inspect the fixed social crop separately. There is no asset-generation npm script in [frontend/package.json](../frontend/package.json); asset preparation is a separate image operation.
4. Verify that the output decodes, its dimensions and bytes match the new manifest entry, and EXIF/XMP/IPTC are absent. Inspect readable screenshot text, event names, badge text, and result graphics at the intended display sizes.
5. Update ASSET_NOTES and this manifest together. Update the content manifest or root-page alt/caption when meaning changes, and update the metadata image dimensions if the social preview changes. Next.js image width/height must describe the replacement's actual aspect ratio.
6. Run the media, fallback, narrow-screen, and keyboard checks in the [public showcase QA matrix](public-showcase.md#focused-manual-qa-matrix). Record those outcomes separately from any live backend or integration-health checks.
