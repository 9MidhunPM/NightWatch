# Public showcase

[← README](../README.md) · [Showcase assets](showcase-assets.md) · [Architecture](architecture.md)

NightWatch's public root page explains the product without operator credentials. It is a cinematic showcase for builders and recruiters: a representative incident story, recorded product views, engineering details, and the Calicut hackathon build. The live operator console remains a separate, authenticated experience.

The direction and content boundaries are recorded in [PRODUCT.md](../PRODUCT.md) and [DESIGN.md](../DESIGN.md). Public copy must distinguish observations, hypotheses, approval, execution, and verification, just as the console does.

## Page and content manifest

The server-rendered [root page](../frontend/app/page.tsx) supplies the headings, incident evidence rows, architecture, event story, links, and no-JavaScript alternatives. [showcase-content.ts](../frontend/lib/showcase-content.ts) holds the shared incident chapters, capability descriptions, screenshot references, engineering disclosures, and narrated walkthrough URL.

| Region | Target | Content and behavior |
| --- | --- | --- |
| Infrastructure Theatre | `#theatre` | “Infrastructure, alive.”, award link, primary exploration link, walkthrough, and illustrative diorama. |
| Incident introduction | `#how-it-works` | Visible representative-simulation label and a “Skip animation” link to the product. |
| Observe | `#observe` | A running container and a public HTTP 502 remain separate observations. |
| Investigate | `#investigate` | Dokploy, Docker, Beszel, Traefik, and HTTP evidence are correlated around the illustrative resource. |
| Understand | `#understand` | Port 8000 versus route target 9999 supports an upstream-port-mismatch hypothesis. |
| Review | `#review` | The illustrative 9999 → 8000 change requires exact-version approval and target revalidation. |
| Verify | `#verify` | Management acceptance is separated from an illustrative public HTTP 200 and preserved verification. |
| Inside NightWatch | `#inside` | Four capability tabs with recorded screenshots, plus the reconciled-source strip. |
| Under the surface | `#engineering` | Frontend, backend, persistence, and observer boundaries; six native technical disclosures. |
| Built in Calicut | `#build-story` | Second Prize, event dates, Midhun P M, Codex's engineering role, two photographs, and the event result graphic. |
| Closing and footer | No section target | Narrated walkthrough, operator sign-in, public home, and creator website. |

The gallery groups the current product into **World & telemetry**, **Investigation & incidents**, **Agent & approvals**, and **Deployments & operations**. The engineering disclosures explain reconciliation, persisted approvals, the two bounded model roles, lifecycle edges, service boundaries, and the limits of the build. Their exact copy lives in the content manifest rather than in this guide.

The port mismatch, status colors, moving signal, and successful check in the incident sequence are authored simulation data. They neither query nor change infrastructure. The product gallery uses recorded screenshots rather than current telemetry; its visible captions preserve that distinction. See the [asset guide](showcase-assets.md) for provenance.

## Public and private routing

The root page does not mount the operator [Shell](../frontend/components/shell.tsx), subscribe to its `/api/events` stream, or import live world components. Its scene is a dedicated public renderer with deterministic geometry. Public visitors can read the story, switch gallery tabs, open technical disclosures, and watch the linked recording without invoking private infrastructure or paid model investigations.

| URL | Boundary |
| --- | --- |
| `/` | Public showcase, including when an operator is already signed in. |
| `/login` | Operator sign-in; successful authentication navigates to `/world`. |
| `/world` | Authenticated infrastructure world. |
| `/overview`, `/infrastructure`, `/agent`, `/deployments`, `/reports`, `/settings` | Existing authenticated console sections. |
| `/incidents`, `/incidents/<id>` | Authenticated incident list and detail views. |

The [console layout](<../frontend/app/(console)/layout.tsx>) checks the signed session through [authenticated()](../frontend/lib/server.ts) before rendering the Shell and redirects unauthenticated requests to `/login`. The [required catch-all page](<../frontend/app/(console)/[...section]/page.tsx>) dispatches the console sections. It rejects unknown sections, paths with more than two segments, and a second segment on sections other than incidents. The [login page](../frontend/app/login/page.tsx) sends the passphrase to `/api/session` and replaces the route with `/world` after success; it does not turn the public root into an operator dashboard.

### Indexing and previews

The [root layout metadata](../frontend/app/layout.tsx) declares the production metadata base `https://nightwatch.midhunpm.in`, root canonical, index/follow policy, and the 1200 × 630 social preview. The [login layout](../frontend/app/login/layout.tsx) and console layout override robots to noindex/nofollow and clear the inherited canonical.

[robots.ts](../frontend/app/robots.ts) allows `/` and disallows login, the console sections, and `/api/`. [sitemap.ts](../frontend/app/sitemap.ts) contains only the production root. [next.config.ts](../frontend/next.config.ts) adds `X-Robots-Tag: noindex, nofollow` to login, console, and API path families. These indexing controls accompany the session boundary; the session check is what protects the operator views.

If the public production hostname changes, update the metadata base, robots host/sitemap, and sitemap URL together. A successful deployment or an available sitemap does not establish that a search engine has indexed the page.

## Scene and native scroll lifecycle

[ShowcaseStage](../frontend/components/showcase-stage.tsx) server-renders the poster and dynamically imports [the R3F scene](../frontend/components/showcase-scene.tsx) with server-side rendering disabled. The canvas activates only when all of these conditions hold:

- Viewport width is at least 1024px.
- The primary pointer is fine.
- The visitor has not requested reduced motion.
- A browser probe can obtain a WebGL2 context.

The experience keeps native document scrolling. [showcase.css](../frontend/app/showcase.css) makes the desktop stage sticky beneath the header; ScrollTrigger itself does not set `pin` or replace scrolling. A GSAP tween maps the theatre's `top top` → `bottom bottom` range to controller progress 0 → 1 with a 0.55-second scrub response. Small pointer offsets add perspective.

[createShowcaseController()](../frontend/lib/showcase-motion.ts) holds progress and pointer coordinates and notifies subscribed listeners. R3F subscribes its `invalidate` function and uses `frameloop="demand"`, with device pixel ratio limited to 1–1.5. There is no permanent animation render loop. The stage withholds controller notifications from scroll updates when the theatre is offscreen or the document is hidden; pointer updates use the same visibility gates and are limited to one pending animation frame. Resize, loading, and other renderer invalidations can still produce frames.

The scene loads the existing rock and ground textures, then reports readiness after a rendered frame. Until readiness, the poster remains visible. The stage restores or retains the poster when WebGL is unavailable, the scene throws, initialization has not completed within 15 seconds, or `webglcontextlost` fires. There is no automatic retry control. GSAP context cleanup, observer/listener cleanup, subscription cleanup, and cancellation of pending pointer/readiness frames prevent duplicate handlers when the component unmounts or its eligibility changes.

### Static and no-JavaScript reading

Below 1024px or with a coarse primary pointer, the canvas is not mounted. Tablet and mobile layouts show the poster and normal reading sections. Reduced-motion CSS also removes transitions and changes the stage to ordinary relative positioning while shortening chapter spacing.

With JavaScript disabled, the poster, all five incident chapters, architecture, native disclosures, event story, and ordinary links are still in the HTML. A `<noscript>` section lists all four capabilities and links directly to their recorded images. Additional no-JavaScript styles hide the interactive gallery and mobile menu button and expose the navigation as ordinary wrapped links.

## Accessible interactions

[showcase-interactions.tsx](../frontend/components/showcase-interactions.tsx) implements the public navigation and capability gallery. The mobile navigation button exposes an accessible open/close label, `aria-expanded`, and `aria-controls`; selecting a section link closes the menu. The first keyboard-reachable skip link leads to `#inside`, and the incident introduction supplies a separate skip-animation link. Main section targets, chapter targets, and `#how-it-works` have a 95px scroll margin to clear the sticky header.

The gallery uses a labelled tablist, associated tabs and panels, selected-state semantics, and roving tab focus. Left/right arrows wrap through the four tabs; Home and End select the first and last. The chosen panel is focusable, inactive panels use `hidden`, and a polite live region announces the selection. Tabs remain horizontally scrollable on narrow screens. Each image has descriptive alt text, a recorded-state caption, and a direct link to the full screenshot.

Engineering explanations use native `<details>` and `<summary>` elements. The decorative diorama and poster region are hidden from assistive technology; the incident meaning remains in ordinary text and definition lists. Visible focus outlines, simulation labels, and recorded-image captions are part of the public design rather than optional animation overlays.

## Focused manual QA matrix

These are acceptance checks to run after changing the showcase, not a record of tests performed by this document. Record the URL, date, browser, viewport, input type, and motion setting with any result. Public-page rendering does not verify backend or integration health.

| Case | Check | Expected result |
| --- | --- | --- |
| Desktop, fine pointer, 1440 × 960 | Load `/`, scroll through all five chapters, move the pointer lightly. | Poster loads first, canvas replaces it after readiness, camera and fault/recovery cues follow native scroll, copy stays readable. |
| Tablet, 768 × 1024; mobile, 390 × 844 | Read the hero, chapters, gallery, engineering, and event story. | Poster-based layout, complete headings/actions, no page-level horizontal overflow; tab row alone can scroll. |
| Reduced motion on desktop | Reload with reduced motion enabled. | No canvas or large motion; poster and compact linear chapters preserve the whole story. |
| WebGL2 unavailable | Disable WebGL for a reload. | Poster remains; product, navigation, and chapter content remain usable. |
| Scene failure or delayed readiness | In a test browser, block a scene texture/module load or induce context loss. | Poster remains or returns; a not-ready scene times out after 15 seconds without hiding narrative content. |
| No JavaScript | Reload with JavaScript disabled. | Visible navigation links, all chapters, four static capability summaries and image links, native disclosures, and event content. |
| Keyboard only | Use the skip link, mobile menu, anchors, tab arrows/Home/End, panels, screenshot links, and disclosures. | Visible focus, correct selected/expanded states, and anchor introductions clear the header. |
| Public network boundary | Load `/` without a session and inspect requests while using public controls. | No private `/api/` calls or event stream from the showcase; scene textures and public images are sufficient. |
| Console boundary | Open `/world` and an incident URL without a session; sign in with the configured operator account for a separate check. | Anonymous requests redirect to `/login`; successful sign-in opens `/world`; console sections retain their existing routes. |
| SEO and social preview | Inspect rendered metadata, response headers, `/robots.txt`, and `/sitemap.xml`. | Root canonical/index policy and social image; private noindex policy, no inherited private canonical, and a root-only sitemap. |
| Media truth | Open every gallery tab and the event section. | Recorded labels remain visible; result graphic and badge retain their full evidence; simulated HTTP 200 is never presented as live health. |
