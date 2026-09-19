# agent-panel-generators Specification

## Purpose
Let a script or an agent build parametric panels from the component library,
change their parameters in one rebuild, and inspect the library well enough to
write and debug a component of its own.

## Requirements

### Requirement: The component library can be listed and described

Listing SHALL report every component with its id, label, category, description,
source and parameter schema - each parameter's key, label, unit, kind, range and
default. An unknown component id SHALL be refused with the ids that exist.

#### Scenario: The library is listed

- **WHEN** the library is listed
- **THEN** every built-in component appears with its parameter schema and its source

#### Scenario: An unknown component

- **WHEN** an unknown component id is described
- **THEN** it is refused and the reason lists the ids the library has

### Requirement: A component can be built without touching the scene

Building a component SHALL return the outlines it would produce - panel names,
closed boundary points in millimetres and edge labels - together with the result
of the outline check, and SHALL NOT change the scene in any way.

#### Scenario: A build changes nothing

- **WHEN** a component is built
- **THEN** the scene's panels, objects and undoes are exactly as they were

#### Scenario: A component that would produce a crossing outline

- **WHEN** a build's outline crosses itself
- **THEN** the result says so instead of returning outlines as if they were usable

### Requirement: User component folders can be reloaded

Reloading SHALL re-read the component folders configured in the preferences and
report the components that were loaded and the files that failed. A failing file
SHALL NOT remove the components that already loaded.

#### Scenario: A broken user component

- **WHEN** a user component file cannot be loaded
- **THEN** it is reported with its error and every other component stays usable

### Requirement: A generator is created from a component with parameters

Creating SHALL take a component id, an optional parameter map and an optional
name, build the component's panels into the project, and return the generator's
name together with the panels it produced. A parameter the component does not
declare SHALL be refused, and a value outside the schema's range SHALL be pulled
back to the nearest bound and the result SHALL report the value that was used.

#### Scenario: A generator is created

- **WHEN** a generator is created from a component with explicit parameters
- **THEN** it owns the component's panels, their meshes are built, and the result names the generator and the panels

#### Scenario: A parameter outside its range

- **WHEN** a parameter value is outside the range its schema declares
- **THEN** the nearest bound is used and the result reports the value that was used

### Requirement: Several parameters change in one rebuild

Setting parameters SHALL accept a map, apply it in one go and rebuild the
generator once, and SHALL return the report of that rebuild: how many panels were
rewritten in place, rebuilt, created and removed, how many sewings were
re-anchored and how many were dropped, and how many outlines ended up invalid.

#### Scenario: One call, one rebuild

- **WHEN** several parameters are set in one call
- **THEN** the generator is rebuilt once and the report describes that rebuild

#### Scenario: A parameter the component does not declare

- **WHEN** a parameter name the component does not declare is set
- **THEN** it is refused and the generator keeps its previous values

### Requirement: A rebuild keeps the previous simulation result where it can

The mesh stage interpolates the previous simulated positions onto the new mesh,
so a rebuild SHALL NOT throw a panel's simulation result away when the mesh
stage can carry it, and the rebuild report SHALL say whether positions were
carried over. Panels whose simulated positions are no longer the rest pose are
the case a caller may want to settle by running a few simulation frames.

#### Scenario: A parameter change after a run

- **WHEN** a generator's parameter changes after its panels have been simulated
- **THEN** the report says the simulated positions were carried over and the panels are not back on their rest pose

#### Scenario: A parameter change before any run

- **WHEN** a generator's parameter changes before anything was simulated
- **THEN** the report says there was nothing to carry over

### Requirement: A generator can be detached or removed with its group

Detaching SHALL turn the generator's panels into ordinary panels and remove the
generator; removing SHALL remove the generator together with the panels it owns
and report what went. Neither SHALL ask for confirmation.

#### Scenario: Detach keeps the panels

- **WHEN** a generator is detached
- **THEN** its panels stay, report that they no longer come from a generator, and the generator is gone

#### Scenario: Removing the group

- **WHEN** a generator is removed
- **THEN** its panels and the sewings that used them are gone and the result reports the counts

### Requirement: Generated panels stay editable through the surface

A generated panel SHALL be readable and its geometry SHALL be editable through
the surface - the interactive lock does not apply here - and the panel record
SHALL say that it comes from a generator, so a caller can expect a later rebuild
to rewrite what it changed.

#### Scenario: Editing a generated panel

- **WHEN** a generated panel's geometry is edited through the surface
- **THEN** the edit is applied and the panel reports that it comes from a generator

### Requirement: Fabric is assigned by name

Creating a panel or assigning a fabric SHALL take the fabric's name, and SHALL
use the project's default fabric when no name is given. An unknown fabric name
SHALL be refused with the names the project has.

#### Scenario: The default fabric

- **WHEN** a panel is created without a fabric name
- **THEN** it uses the project's default fabric

#### Scenario: An unknown fabric

- **WHEN** a fabric name is given that the project does not have
- **THEN** it is refused and the reason lists the fabric names the project has
