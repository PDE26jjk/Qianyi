## Purpose

Give a script or an agent client a stable, discoverable way to drive the add-on
by name from any Blender session, including one with no viewport, and to get one
undo step per intent.

## ADDED Requirements

### Requirement: The surface is reachable under one stable name

The add-on SHALL publish its script surface as a module named `qyapi` that a
client can import in any session where the add-on is registered, whether a
viewport exists or the session runs with `-b`. Importing and calling it MUST NOT
require an operator, a modal handler, a menu, a selection, or an active editor.

#### Scenario: Imported in a background session

- **WHEN** the add-on is registered in a session started with `-b` and a client imports `qyapi`
- **THEN** the import succeeds and every discovery call works with no viewport present

#### Scenario: Imported in a live session

- **WHEN** the add-on is loaded in a normal session with a viewport
- **THEN** the same import resolves to the same surface

### Requirement: The surface is discoverable without the repository

The surface SHALL offer a call that returns a compact text index of every public
entry point, with a one-line purpose and the unit of every numeric argument, and
a call that returns a JSON-safe snapshot of the scene. Both MUST work with no
scene content and MUST NOT change the scene. The text index SHALL also be
readable by topic, so that the data model described below can be read the same
way as the entry-point list.

#### Scenario: A client that can only run Python finds the surface

- **WHEN** a client reads the module documentation and then the text index
- **THEN** it learns every entry point, its arguments and their units without reading any repository file

#### Scenario: Snapshot of an empty scene

- **WHEN** the snapshot is requested in a scene that holds no project
- **THEN** the result reports the absence of a project instead of raising

### Requirement: Objects are addressed by name and results are plain data

Every entry point SHALL identify projects and patterns by name. A call MUST NOT
require an identifier that is only valid inside the current process, and no
returned value MAY contain a Blender object, a Blender collection, or a numpy
array.

#### Scenario: Addressing by name

- **WHEN** a caller names a pattern that exists
- **THEN** the call acts on that pattern

#### Scenario: A name that no longer exists

- **WHEN** a caller names a pattern that was deleted or renamed
- **THEN** the call reports the missing name and changes nothing

### Requirement: A call works after undo, redo or a file reload

The in-memory identity map the add-on resolves objects through is cleared by
undo, redo and file loading. Every entry point SHALL therefore resolve names from
the scene data at the start of the call, so a call made after any of those events
behaves the same as one made before.

#### Scenario: Called after an undo

- **WHEN** a caller undoes an edit and then makes an entry-point call naming an object that still exists
- **THEN** the call resolves that object and succeeds

### Requirement: One write call is one undo step

A write entry point SHALL leave exactly one undo step, labelled with the caller's
intent, and a read entry point MUST NOT add an undo step. A transaction SHALL
collapse the writes it contains into a single undo step, including nested
transactions. In a session that cannot undo, a write SHALL still succeed and a
transaction MUST NOT fail.

#### Scenario: A batch inside one transaction is reverted at once

- **WHEN** several writes run inside one transaction and the user presses undo once
- **THEN** every change made inside the transaction is reverted together

#### Scenario: Reading leaves the undo stack alone

- **WHEN** only read entry points have been called
- **THEN** the undo stack is unchanged

#### Scenario: A session with no window

- **WHEN** a write runs inside a transaction in a session that has no window
- **THEN** the change is applied and no error is raised about undo being unavailable

### Requirement: Failures are explicit and never a silent success

An entry point that cannot carry out its work SHALL report the reason, naming the
object involved and a next action. It MUST NOT return a success result, and MUST
NOT open a menu, a popup or any other dialog. When a call changes part of its
input before failing, it SHALL report which objects it already changed.

#### Scenario: A refused operation

- **WHEN** a write entry point could not do its work
- **THEN** the caller receives the reason and no success result

#### Scenario: Output in a session with no window

- **WHEN** a session with no window runs an entry point that would otherwise report to the user
- **THEN** the report is delivered to the caller instead of a dialog being opened

### Requirement: The documentation ships with the code

The surface SHALL document itself in the module, so a client that can only run
Python can find it, and the same content SHALL be shipped as a reference file in
the repository. Both MUST state the entry points, the units, the coordinate
spaces, the addressing scheme, the undo granularity and the calls the surface
deliberately does not offer.

#### Scenario: Documentation and index agree

- **WHEN** the text index and the shipped reference file are compared
- **THEN** every entry point appears in both with the same purpose and units

### Requirement: The data model is documented

The documentation SHALL describe the add-on's objects and their structure, and
how each one is reached from a session: the project that owns patterns, sewings
and fabrics; a pattern with its vertices, edges, spline points, internal lines,
fabric, granularity, collision layer and mesh object; a sewing as two sides,
each one an edge plus a normalized position on that edge; a fabric; and the mesh
objects that take part in a simulation. For every object it MUST name the
supported way to read it and the supported way to change it.

The documentation SHALL also state that reading and writing Blender data
directly is permitted but discouraged, and MUST name what has to be re-resolved
after such a write and which failures follow from skipping it.

#### Scenario: An agent needs something the surface does not offer

- **WHEN** a client finds no entry point for a change it has to make
- **THEN** the documentation tells it which data to reach for, what to re-resolve after the write, and what can break

#### Scenario: The data model is reachable without the repository

- **WHEN** a client reads the data-model topic from the text index
- **THEN** it gets the same description as the shipped reference file

#### Scenario: A discouraged path is not a silent path

- **WHEN** a client changes patterns or sewings through Blender data instead of the surface
- **THEN** the documentation has already told it that the add-on's identity map and derived data must be refreshed, and which failure the missing refresh causes
