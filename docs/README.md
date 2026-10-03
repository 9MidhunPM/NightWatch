# NightWatch documentation

[← Project README](../README.md) · [Contributor guide](../CONTRIBUTING.md)

The public homepage introduces the product. The operator console observes and changes real infrastructure after sign-in. Choose a guide by the task you are doing; a screenshot or illustrative incident is not a current operational observation.

## Understand the project

| Guide | Use it to understand |
| --- | --- |
| [Architecture](architecture.md) | Service boundaries, reconciliation, graph semantics, persistence, and agent execution |
| [Engineering story](engineering.md) | The integration and lifecycle failures that shaped the implementation |
| [API and workflows](reference.md) | Route groups, deployment intent, approvals, incident records, and the meaning of verification |
| [Product context](../PRODUCT.md) | Audience, purpose, supported capabilities, and evidence boundaries |
| [Public design system](../DESIGN.md) | The shipped public palette, typography, components, and responsive rules |

## Develop and maintain

| Task | Start here |
| --- | --- |
| Run the public page without integrations | [Frontend development](frontend-development.md) |
| Configure backend and integration services | [Setup and operations](operations.md) |
| Diagnose sign-in or an expired session | [Operator access](operator-access.md) |
| Interpret liveness and readiness responses | [Health checks](health-checks.md) |
| Change the public narrative, routes, or animation | [Public showcase](public-showcase.md) |
| Replace a screenshot, event image, or scene poster | [Showcase assets](showcase-assets.md) |
| Publish or restore a frontend release | [Frontend release](frontend-release.md) |
| Prepare a focused code or documentation contribution | [Contributing](../CONTRIBUTING.md) |

## Follow the source of truth

- Route and request behavior comes from the frontend handlers and backend models, not from a prose example.
- Live deployment settings must be rechecked in Dokploy. The Dockerfiles describe how images are built; they do not establish the current hostname, network, or credentials.
- Recorded product images come from [screenshots](screenshots/). Published hackathon material lives in [hackathon](hackathon/). Public derivatives and synthetic artwork are tracked in [asset notes](../frontend/public/showcase/ASSET_NOTES.md).
- [Texture licenses](../frontend/public/textures/ASSET_LICENSES.md) cover the infrastructure world's texture sources.

Report static checks, browser behavior, deployed artifact identity, and dependent-service health separately. Refer to exact timestamps and recorded evidence when describing an operational outcome.
