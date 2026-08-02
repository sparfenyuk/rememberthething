## Purpose

Let users maintain reusable groups of things and choose context-specific variants without duplicating every seasonal or activity checklist by hand.

## ADDED Requirements

### Requirement: Reusable pack management

The system SHALL let the user create, inspect, update, and delete named packs containing item definitions. Packs SHALL be usable for vacation, bathroom, hiking, commuting, or any user-defined category.

#### Scenario: Create a pack

- **WHEN** the user creates a `bathroom essentials` pack with several items
- **THEN** the pack is persisted and its items are available in a later pack read

#### Scenario: Include a pack in a target

- **WHEN** the user explicitly includes a pack in a journey or blueprint
- **THEN** the target receives independent item copies with pack provenance

#### Scenario: Pack changes do not rewrite existing checklists

- **WHEN** the user edits or deletes a pack after including it in a journey
- **THEN** existing journey and blueprint item copies remain unchanged

### Requirement: Context-specific pack variants

The system SHALL let a pack contain common base items and named variants with context labels such as season, purpose, or activity. The system SHALL expose variant metadata so an LM or user can choose a variant deliberately.

#### Scenario: Summer and winter vacation variants

- **WHEN** the vacation pack contains common items plus `summer` and `winter` variants
- **THEN** a pack read identifies the common items and both variant item sets separately

#### Scenario: Choose a seasonal variant

- **WHEN** the user includes the vacation pack with the `winter` variant
- **THEN** the target receives the common items and winter variant items, and does not receive the summer variant items

#### Scenario: Variant choice is explicit

- **WHEN** a journey has a season but no variant is selected
- **THEN** the system exposes available variants and does not silently choose one or claim a recommendation was made

### Requirement: Safe pack composition

The system SHALL report duplicate or conflicting item names encountered while composing a pack instead of silently overwriting an existing manually edited item. The user or LM SHALL be able to continue with an explicit choice.

#### Scenario: Pack overlaps an edited item

- **WHEN** a pack contains `toothbrush` and the target already has a user-edited `toothbrush`
- **THEN** the composition result identifies the overlap and preserves the existing edited item
