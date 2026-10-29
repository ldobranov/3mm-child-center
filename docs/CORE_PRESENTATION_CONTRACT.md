# Core-owned theme and application locale

## Requested general capability: system time zone, 2026-10-28

Child Center currently formats timestamps and interprets calendar-day filters
in Europe/Sofia. The public presentation info above exposes only locale; it does
not expose a Core system time zone. The maintenance-window time zone in Core is
specific to updates and must not be assumed to be a global application setting.
The browser's local time zone can differ from the Core device, and its OS setting
must not silently control shared business-day filters.

Proposed Core contract for all applications: expose the effective, validated
IANA time-zone identifier from the Core system setting through the public UI
presentation info and through the application service SDK. Both surfaces must
refer to the same Core installation and be available before application work;
the presentation subscription must report changes. Define how a service learns
of changes and how concurrent requests obtain a consistent value. A missing or
invalid setting must have an explicit, documented Core policy rather than an
application silently choosing the browser's zone. Applications remain responsible
for storing instants in UTC, converting calendar-day filter bounds with the
provided IANA zone including DST, and displaying timestamps in that same zone.

Acceptance: configure at least two zones; confirm two clients with different OS
zones display and filter the same instants consistently; verify local midnight,
both DST changes and repeated hours; change the system setting while routes are
open and check the documented update behavior and server/UI agreement. No
application-specific Core code or direct access to Core internals is needed.
Until this contract exists, Child Center keeps the explicit Sofia behavior rather
than claiming system-zone support.

Owner decision, 2026-10-27: theme, typography, density, button/card variants and
the active language belong to Core. Applications declare their own translations;
English is the required source and fallback, Bulgarian is an optional reference.
No per-application theme/language selector or second preference store.

## Already supported: presentation

Applications wrap routes in public `UiSurface` and use `UiButton`, `UiField` and
other exports from `@3mm/ui/v1`. UiSurface consumes Core's reactive button/card
appearance. The loaded Core stylesheet and `--ui-*` tokens own surfaces, colors,
fonts, size/line height, spacing, radii, focus and control height. Layout may adapt
to viewport size; it must not infer light/dark from the OS or override the palette.
Core's dark-mode and saved appearance choices remain authoritative.

Child Center now follows this contract. Tests use the actual public components
and simulate a Core-provided appearance ref changing outline/raised to
solid/bordered. This proves wiring, not installed visual appearance; owner review
on light/dark, card/button/font/density settings and phone is still pending.

## Implemented public capability: initial and live locale

The current `@3mm/application-ui/v1` exposes `host.presentation.version = 1`,
initial synchronous `getInfo()` and a live `subscribe()` returning an unsubscribe
function. `host.getInfo().features.presentation_version` advertises version 1.
Core's compiled-route loader also supplies a reactive root `locale` prop and
patches the same component instance when the language changes. Core source was
read only during this Child Center integration.

Current public API:

```typescript
type PresentationInfo = { readonly locale: string }
interface ApplicationPresentation {
  readonly version: 1
  getInfo(): PresentationInfo
  subscribe(listener: (info: PresentationInfo) => void): () => void
}
// Added to the existing mounted ApplicationHost: readonly presentation.
```

Core provides the current effective user/session language before mounting an
application route. `subscribe` emits updates from the same source used by the
Core header. It grants no action, token, URL or private store. Host disposal/unmount
removes subscriptions, and no application setter is exposed.
No duplicate theme service is needed: presentation components/CSS already carry it.

Child Center uses that public facade for its initial/live locale and unsubscribes
on unmount. A supplied root prop (the real loader's same Core language, or an
explicit preview input) takes precedence. Root components no longer inject an
artificial default `en` prop that masks host presentation. There is no independent
application language selector/store or private Core import.

## Application translation contract

- `locales/en.json`: mandatory, nonempty English source values with stable keys.
- Other locale JSON files are optional. Register a new catalogue in the app's
  catalogue registry; no Core source edit is needed to add its translated strings.
- Lookup: normalized requested locale, its base language, then English, per key.
  An unsupported language or missing translated key therefore shows English.
- Bulgarian is just one optional reference, never the universal fallback.
- A missing English source key is an authoring error checked before delivery;
  it must not be hidden by a Bulgarian value.
- Core remains responsible for which global languages users may select. Adding
  an application catalogue does not silently install a global Core language pack.

Acceptance for the Core addition: open a route when Core is already on a non-EN
locale; change the Core language with a filled form/error visible; verify updates
without losing state; use an unsupported application language and a partial
translation and verify EN fallback; unmount and verify subscription disposal.
Tests cover actual public presentation-method consumption, initial BG, live
switch/fallback with a populated form, unsubscribe, and reactive input-prop
updates. A disposable browser fixture uses the public facade with real Core
components/design tokens. Actual installed Core/device acceptance remains manual;
the lack of a public language contract is no longer a platform blocker.
