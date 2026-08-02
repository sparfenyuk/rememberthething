## Purpose

Give a person a persistent, editable todo list for each journey while preserving reusable blueprints for the next journey.

## ADDED Requirements

### Requirement: Blueprint lifecycle

The system SHALL let the user create, name, inspect, and reuse a blueprint containing checklist items. Starting a journey from a blueprint SHALL copy its items into an independent journey checklist; changing the journey SHALL NOT change the blueprint implicitly.

#### Scenario: Start a journey from a blueprint

- **WHEN** the user starts a journey from blueprint `business-trip`
- **THEN** the system creates a new journey with a distinct identifier and a copy of the blueprint's current items

#### Scenario: Journey edits do not mutate the blueprint

- **WHEN** the user removes or edits an item on a journey created from a blueprint
- **THEN** the blueprint remains unchanged

#### Scenario: Empty journey becomes a blueprint

- **WHEN** the user saves an ad-hoc journey as a new named blueprint
- **THEN** the system stores the journey's current items and does not require an existing blueprint

### Requirement: Mutable journey checklist

The system SHALL let the user create a journey, update its context, add items, edit item details, remove items, and mark items packed or not needed at any time before, during, or after the journey.

#### Scenario: Create a contextual journey

- **WHEN** the user provides a name and any subset of destination, purpose, dates, duration, or season
- **THEN** the system creates a journey that retains the supplied context and returns its checklist state

#### Scenario: Add and pack an item

- **WHEN** the user adds `power bank` and marks it packed
- **THEN** the item appears in the journey with its packed state and remains persisted after a later read

#### Scenario: Remove an unnecessary item

- **WHEN** the user removes `formal shoes` from the current journey
- **THEN** the item is absent from that journey's active checklist and the source blueprint is unchanged

#### Scenario: Update a journey after creation

- **WHEN** the user changes the destination, season, item quantity, note, or packed state
- **THEN** the next checklist read reflects the new value without requiring journey recreation

### Requirement: Explicit blueprint carry-forward

The system SHALL distinguish items copied from a blueprint from items added directly to a journey. Directly added items SHALL NOT be added to the blueprint automatically; the user SHALL be able to explicitly select direct items to carry into an existing or new blueprint.

#### Scenario: Ad-hoc item is not silently promoted

- **WHEN** the user adds `portable umbrella` to a journey
- **THEN** the item is available on that journey only and the originating blueprint remains unchanged

#### Scenario: User remembers an ad-hoc item

- **WHEN** the user explicitly saves `portable umbrella` to the journey's blueprint
- **THEN** the blueprint contains the item for future journeys and the current journey remains unchanged

#### Scenario: Removed item stays removed for the current journey

- **WHEN** the user removes a copied blueprint item from a journey
- **THEN** the item is not reintroduced by later reads or edits to that journey

### Requirement: Contextual next-step hints

Relevant journey, blueprint, and pack tool results SHALL include a structured `next_steps` array when a useful follow-on operation is evident. Each hint SHALL identify an existing tool, explain its purpose, include known identifiers or arguments, identify missing inputs, and state whether user confirmation is required. Hints SHALL guide the LM without performing another mutation automatically.

#### Scenario: Blueprint flow exposes pack discovery

- **WHEN** the user starts a journey from a blueprint that has no selected seasonal or activity pack
- **THEN** the result includes a hint for `list_packs` or `include_pack`, identifies the journey, and names any missing context such as season without adding a pack

#### Scenario: Ad-hoc item exposes carry-forward choices

- **WHEN** the user adds one or more direct items to a journey
- **THEN** the result includes actionable hints for `promote_items` and, when appropriate, `create_pack` or `update_pack`, using the new item identifiers

#### Scenario: Hints do not chain mutations

- **WHEN** a tool result contains one or more next-step hints
- **THEN** the server performs only the requested operation and waits for a separate tool call or explicit UI action before applying any hinted operation

#### Scenario: Unknown context avoids invented advice

- **WHEN** the server lacks enough context to identify a meaningful follow-on operation
- **THEN** it returns no speculative domain hint rather than inventing a pack or recommendation

### Requirement: Predictable list operations

The system SHALL reject unknown journey, blueprint, or item identifiers with a clear error and SHALL leave the affected checklist unchanged when a requested mutation cannot be applied.

#### Scenario: Unknown item mutation

- **WHEN** an item update names an item that is not in the target journey
- **THEN** the system returns a validation error and persists no partial item change
