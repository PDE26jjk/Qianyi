## MODIFIED Requirements

### Requirement: The surface is reachable under one stable name

The add-on SHALL expose its script surface as the `qyapi` sub-module of its own
package, which a client can reach in any session where the add-on is registered,
whether a viewport exists or the session runs with `-b`. A client SHALL find the
package among the registered add-ons rather than naming it, because the package
name carries the repository the add-on was installed from. The add-on MUST NOT
publish a module name of its own into the module table, neither for the surface
nor for one of its sub-modules. Importing and calling the surface MUST NOT
require an operator, a modal handler, a menu, a selection, or an active editor.

#### Scenario: Imported in a background session

- **WHEN** the add-on is registered in a session started with `-b` and a client imports the surface from the add-on package
- **THEN** the import succeeds and every discovery call works with no viewport present

#### Scenario: Imported in a live session

- **WHEN** the add-on is loaded in a normal session with a viewport
- **THEN** the same import resolves to the same surface

#### Scenario: Registering publishes no module name of its own

- **WHEN** the add-on has been registered
- **THEN** the surface is present in the module table only under the add-on's own package path, and no bare sub-module name of it exists
