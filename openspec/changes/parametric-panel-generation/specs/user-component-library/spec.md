## Purpose

Let a user put their own panel components on disk, load them into the library,
and iterate on one while Blender stays open.

## ADDED Requirements

### Requirement: Component folders come from the preferences

The add-on preferences SHALL hold the folders that user components are read
from, and SHALL allow more than one folder.

#### Scenario: No folder configured

- **WHEN** no component folder is configured
- **THEN** the library still shows the built-in components and reports no error

### Requirement: Reload re-reads every component file

A reload SHALL re-execute every component file in the configured folders, so a
file that was edited is picked up without restarting Blender. Reloading MUST
ignore cached bytecode: a file whose length did not change must still be read
from disk.

#### Scenario: Editing a component and reloading

- **WHEN** the user edits a value in a component file and triggers the reload
- **THEN** the library shows the edited component, and the next rebuild uses the edited code

#### Scenario: A failing file does not hide the others

- **WHEN** one component file raises on import
- **THEN** that file is reported with its error and every other component, built-in or user, stays usable

### Requirement: Components are labelled by origin

The library SHALL mark whether a component comes from the add-on or from a user
folder, and SHALL report the files that failed to load.

#### Scenario: Origin shown in the grid

- **WHEN** a user component appears in the library
- **THEN** its cell shows that it comes from a user folder, and failing files are listed with their error
