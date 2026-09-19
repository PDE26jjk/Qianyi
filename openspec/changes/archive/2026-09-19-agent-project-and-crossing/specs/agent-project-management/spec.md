## Purpose

Let a script or an agent start from a blank file: make a project, make it the one
the other calls work on, and address projects by a name that the editor's own
panel and the script surface agree on.

## ADDED Requirements

### Requirement: A project can be created and is immediately usable

Creating a project SHALL make the node tree, give the project and its default
fabric an identity, name it, and select it. Everything else SHALL work on it
straight away: a panel created in the same session SHALL need no further setup.

#### Scenario: From a blank file to a panel

- **WHEN** a project is created in a scene that has none and a panel is created in it
- **THEN** the panel exists with its mesh, and no call reports a missing project

#### Scenario: A scene with no project

- **WHEN** a panel call is made before any project exists
- **THEN** it is refused with a reason, and the answer names the call that makes a project

### Requirement: A project carries the name it is addressed by

A project is addressed by the add-on's own name property, which is also what the
editor's project list draws. Creating and renaming SHALL set that name, so a
project made by a script is addressable and shows up in the list under it.
Listing SHALL report that name, and MAY report the node tree's own datablock key
as a diagnostic, because the two can differ without meaning anything.

#### Scenario: A created project is addressable by its name

- **WHEN** a project is created under a name and a later call names that project
- **THEN** the call finds it

#### Scenario: The list shows the same name

- **WHEN** a project created by the surface is listed by the editor's own panel
- **THEN** the row carries the name the surface addresses it by

#### Scenario: Renaming moves the address

- **WHEN** a project is renamed
- **THEN** the new name resolves and the old one does not

### Requirement: A project can be made the active one

Making a project active SHALL be one call taking its name, and every call that
does not name a project SHALL work on the active one. The active project SHALL be
readable, and `state()` SHALL report it.

#### Scenario: Switching between projects

- **WHEN** two projects exist and the second is made active
- **THEN** a call that names no project works on the second, and the snapshot reports the second as active

#### Scenario: The index is not the interface

- **WHEN** the scene holds node trees that are not projects
- **THEN** activating by name still selects the right project

### Requirement: Projects can be listed and removed

Listing SHALL report, for every project, the name to address it by, whether it is
active, and how many panels, sewings, fabrics and generators it holds. Removing
SHALL take a project away and report what went with it.

#### Scenario: The listing

- **WHEN** the projects are listed
- **THEN** each entry carries its name, whether it is active, and its counts

#### Scenario: Removing a project

- **WHEN** a project is removed
- **THEN** it is gone from the listing and the answer reports the panels and sewings that went with it
