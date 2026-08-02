## Purpose

Let an LM and a person assemble a journey from reusable modules while keeping the final checklist concrete, editable, and understandable in the MCP App.

## ADDED Requirements

### Requirement: Reusable module definitions

The system SHALL provide named reusable modules as the canonical replacement for packs. A module SHALL contain stable item keys, item definitions, optional nested module references, optional named variants, and optional mutually exclusive choice groups.

#### Scenario: Create a module

- **WHEN** a user creates an `Everyday` module with passport and laptop items
- **THEN** the module is persisted with stable item keys and can be read independently of any journey

#### Scenario: Module item identity is stable

- **WHEN** a module item is renamed or its note changes
- **THEN** its item key remains stable so variant removals, provenance, and materialized checklist rows continue to refer to the same definition

### Requirement: Delta variants

Module variants SHALL be represented as deltas containing `add` item definitions and `remove` item keys. A variant SHALL apply to the module's own common items without requiring a duplicated full list.

#### Scenario: Apply a variant delta

- **WHEN** a module has common `passport` and `macbook` items and its `car` variant adds `car documents` and removes `passport`
- **THEN** materializing the `car` variant produces `macbook` and `car documents`, without producing `passport`

#### Scenario: Read variant metadata

- **WHEN** an LM reads a module
- **THEN** the response identifies common items and each variant's `add` and `remove` operations separately

### Requirement: Nested module composition

Modules SHALL be composable from other modules. The system SHALL reject a direct or indirect include cycle and SHALL preserve the module path in materialized item provenance.

#### Scenario: Compose modules

- **WHEN** `Roadtrip` includes `Everyday`, `Car`, and `Video`
- **THEN** including `Roadtrip` exposes the resolved items from all referenced modules in deterministic order

#### Scenario: Reject a module cycle

- **WHEN** a user attempts to make `Everyday` include `Roadtrip` while `Roadtrip` already includes `Everyday`
- **THEN** the operation is rejected without changing either module

### Requirement: Journey and blueprint composition

Journeys and reusable trip blueprints SHALL persist selected module references and ad-hoc extras separately from the materialized checklist items. Including a module SHALL materialize its current resolved items into the target while retaining the selected composition.

#### Scenario: Start a journey from a composed blueprint

- **WHEN** a user starts a journey from a blueprint selecting `Everyday` and `Work`
- **THEN** the journey stores those module selections, copies blueprint extras, and exposes one concrete checklist containing the resolved module items

#### Scenario: Add an ad-hoc extra

- **WHEN** a user adds `drone` directly to a journey
- **THEN** `drone` is a direct journey item and does not become part of a module or blueprint without an explicit promotion operation

### Requirement: Safe materialization and refresh

The system SHALL support explicit composition refresh for a journey or blueprint. Refresh SHALL add newly resolved module items, preserve user-edited materialized items, preserve explicit removals through durable exclusions, and report duplicate/conflicting definitions without silently overwriting the target.

#### Scenario: Refresh after module maintenance

- **WHEN** a module gains `rain jacket` and the user refreshes a journey that includes it
- **THEN** `rain jacket` is added with module provenance while existing checklist state remains unchanged

#### Scenario: Preserve a removed module item

- **WHEN** a user removes a materialized module item from a journey and later refreshes the composition
- **THEN** that item remains absent unless the user explicitly restores it

#### Scenario: Preserve an edited duplicate

- **WHEN** a refreshed module contains an item whose target copy was manually edited
- **THEN** the edited target row remains authoritative and the result reports the conflict

### Requirement: Explicit one-of choices

Modules SHALL support `one_of` choice groups with stable choice identifiers and item options. The system SHALL never silently select an option. An unresolved choice SHALL be visible in structured results and the UI until the user or LM selects an option.

#### Scenario: Resolve a choice

- **WHEN** a `Video` module offers `24-70` or `35mm` in one choice group and the user selects `35mm`
- **THEN** the materialized checklist contains `35mm` and not `24-70`, with the choice recorded in the target composition

#### Scenario: Keep an unresolved choice explicit

- **WHEN** a module with a required one-of group is included without a selection
- **THEN** the result lists the unresolved choice and offers an explicit selection action without inventing an item

### Requirement: Composable MCP contract

The MCP SHALL expose non-overlapping module and composition operations for module CRUD, module inclusion, choice selection, and explicit refresh. Existing concrete checklist operations SHALL remain available. Tool results SHALL include stable IDs, resolved state, unresolved choices, conflicts, and bounded `next_steps` sufficient for an LM to continue without guessing tool names or argument shapes.

#### Scenario: Discover module follow-ups

- **WHEN** an LM includes a module with available variants or unresolved choices
- **THEN** the result identifies the relevant module/choice IDs and provides a structured next step for selecting or refreshing them

#### Scenario: Tool-only client remains usable

- **WHEN** an MCP client does not render the MCP App
- **THEN** the client can create/read/update modules, compose a journey, resolve choices, refresh composition, and mutate concrete checklist items through structured results

### Requirement: Composition-aware checklist UI

The MCP App SHALL keep the concrete todo list as the primary interaction and SHALL expose selected modules, item provenance, unresolved choices, conflicts, and explicit refresh/selection actions without maintaining a second state store.

#### Scenario: Inspect module provenance

- **WHEN** a journey contains items from `Roadtrip → Car`
- **THEN** the checklist can show that source path while still allowing the item to be packed, edited, or removed

#### Scenario: Resolve a choice in the UI

- **WHEN** the journey has an unresolved lens choice
- **THEN** the UI presents the available options and updates the shared MCP state only after the user selects one
