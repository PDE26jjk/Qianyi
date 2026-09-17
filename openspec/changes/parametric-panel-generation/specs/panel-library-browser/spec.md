## Purpose

Let a user see which panel components the add-on offers, narrow that list down,
inspect what a component needs, and add it to the project.

## ADDED Requirements

### Requirement: Components are browsed as a grid

The library panel SHALL list every available component as a grid cell that shows
a thumbnail of the component's geometry and its name, with several cells per
row.

#### Scenario: Library shows thumbnails and names

- **WHEN** the user opens the library panel with at least one component available
- **THEN** each component appears as a cell with a thumbnail of its panels and its name

#### Scenario: Thumbnail failure does not break the panel

- **WHEN** a thumbnail cannot be produced for a component
- **THEN** the cell still shows the component's name and the panel stays usable

### Requirement: The list can be narrowed

The library panel SHALL offer a free-text filter and a category filter, and SHALL
report when nothing matches instead of showing an empty grid.

#### Scenario: Filtering by text

- **WHEN** the user types part of a component's name, category or description
- **THEN** only the matching components remain in the grid

#### Scenario: Filtering by category

- **WHEN** the user picks a category
- **THEN** only the components of that category are shown, and choosing "all" shows every component

### Requirement: Selecting a component shows its details

Selecting a component SHALL show its name, category, description, its parameter
table (label, default, unit, range) and an action that adds it to the project.

#### Scenario: Details for the selected component

- **WHEN** the user selects a component in the grid
- **THEN** the detail area shows that component's description and parameters, and offers to add it

#### Scenario: Adding from the detail area

- **WHEN** the user triggers "add to project" for the selected component
- **THEN** a generator for that component is created in the project with its default parameters
