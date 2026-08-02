## Purpose

Make the rendered MCP App checklist the fastest way to inspect and update a journey while keeping conversational LM control fully synchronized with it.

## ADDED Requirements

### Requirement: Rendered journey checklist

When the MCP client supports MCP Apps rendering, the system SHALL provide a rendered journey checklist that shows the selected journey's context, item groups, item states, and remaining work as a todo-like list.

#### Scenario: Open a journey

- **WHEN** the user opens the journey UI for an existing journey
- **THEN** the UI shows the persisted journey name/context and its current grouped items without requiring the user to restate them to the LM

#### Scenario: Scan remaining work

- **WHEN** the journey contains packed, pending, and not-needed items
- **THEN** the UI makes the remaining pending items and completion summary visually distinguishable

### Requirement: Direct checklist editing

The UI SHALL let the user check or uncheck an item, add an item, edit item details, remove an item, and open available packs without leaving the checklist surface.

#### Scenario: Check an item in the UI

- **WHEN** the user checks `passport`
- **THEN** the UI invokes the checklist mutation, reflects the packed state, and a later LM/tool read returns the same state

#### Scenario: Add an ad-hoc item in the UI

- **WHEN** the user adds `portable umbrella` from the checklist surface
- **THEN** the item appears immediately after the persisted mutation and is marked as a direct journey item eligible for explicit carry-forward

#### Scenario: Remove an item in the UI

- **WHEN** the user removes an item
- **THEN** the item disappears from the active list after the mutation succeeds and the UI does not mutate the blueprint implicitly

### Requirement: Shared state with the LM

The UI SHALL use the same authorized MCP tools and persisted state as the LM. After a tool mutation from chat, the next UI refresh SHALL display the updated state; after a UI mutation, the next tool read SHALL display the updated state.

#### Scenario: LM adds an item while the UI is open

- **WHEN** the LM adds `rain jacket` to the open journey
- **THEN** a UI refresh shows `rain jacket` in the correct group with its source marked as direct

#### Scenario: UI mutation fails

- **WHEN** a checklist mutation is rejected
- **THEN** the UI keeps the last confirmed state, shows a recoverable error, and does not present the rejected change as saved

### Requirement: Guided next-step actions

The UI SHALL render structured `next_steps` hints returned by checklist, blueprint, or pack tools as explicit follow-on actions. A hint action SHALL invoke only the referenced existing tool, show or collect missing inputs, and require confirmation when the hint says confirmation is required.

#### Scenario: Ad-hoc item suggests blueprint and pack actions

- **WHEN** the user adds `portable umbrella` and the tool result includes carry-forward hints
- **THEN** the UI presents actions to promote the item to a blueprint or save it through a pack, using the returned item identifier

#### Scenario: Seasonal pack hint asks for missing context

- **WHEN** a hint says that `season` is required before including a pack variant
- **THEN** the UI asks for or accepts the season and does not include a variant before the user or LM supplies it

#### Scenario: Hints never mutate by themselves

- **WHEN** the UI receives a next-step hint
- **THEN** it displays the action without invoking the hinted tool until the user activates it or the LM makes a separate authorized call

### Requirement: Non-UI client fallback

When the MCP client does not support MCP Apps rendering, the system SHALL keep all checklist, blueprint, and pack operations available through structured MCP tool results that are readable by an LM.

#### Scenario: Tool-only client

- **WHEN** a client calls the MCP server without UI rendering support
- **THEN** the client can list, create, read, and mutate journeys using structured results without relying on browser-only state

### Requirement: Blueprint output schema

The `create_blueprint` tool SHALL advertise an MCP output schema for its structured result. Successful results SHALL describe the created blueprint and its complete item state; rejected results SHALL retain the existing error envelope.

#### Scenario: Client discovers the blueprint result contract

- **WHEN** a client lists the available tools
- **THEN** `create_blueprint` includes an output schema for its structured content

#### Scenario: Blueprint result validates against the advertised schema

- **WHEN** a client creates a blueprint with checklist items
- **THEN** the structured result validates against the advertised schema and the existing text content, error signaling, and MCP Apps behavior remain unchanged
