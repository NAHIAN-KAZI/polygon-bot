# ADR-0013: Routing responses use the mobile app's real service.id, not an invented slug

## Status
Accepted

## Context
ADR-0007 established the `result` SSE event's `routing` object for handing navigation
information to the main application, but left the exact identifier values as Polygon-Bot-owned
slugs (since no real catalog was known at the time). `user-app-api-map.md` shows the mobile
app's own navigation (`LocalServiceCatalog.routeFor()` / `PayTransferServiceNavigator`) already
resolves a bare `service.id` string (e.g. `transaction_history`, `beneficiary`, `frezz_unfrezz`)
to a route via a local mapping it maintains itself.

## Decision
Since ADR-0011 already sources the taxonomy from the same catalog the mobile app uses, the
`routing.service` (and `routing.subservice`, if present) values in the `result` event are the
exact `id` strings from that catalog — never a value Polygon Bot invents or re-slugs.

## Consequences
The main application can route a customer with zero translation logic on its side — it hands
Polygon Bot's `routing.service` value straight to its own existing `LocalServiceCatalog`/
`PayTransferServiceNavigator`, the same code path it already uses for its own service grids. This
was made essentially free by ADR-0011's decision to source the taxonomy live from the same place
— had the taxonomy stayed a separately invented static file (ADR-0009), this mapping would have
needed its own translation table, another thing to keep in sync.

## Alternatives considered
**Keep Polygon-Bot-invented category/service/subservice slugs, let the frontend team maintain a
translation table** — was the only option before ADR-0011, now unnecessary complexity given the
taxonomy source is already the same as their own routing catalog; rejected.

## Related
FR-CONTRACT-05, FR-CONTRACT-06, F-06
