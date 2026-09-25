# agent-simulation-control Specification

## Purpose
Let a script or an agent prepare, step, run, inspect and reset a simulation
through one call per intent, and always be able to tell a completed run from a
refused or failed one.

## Requirements

### Requirement: One call per intent

The simulation surface SHALL offer preparing, stepping, starting, stopping,
reading back and resetting as separate entry points. A caller MUST NOT have to
know the internal order in which scene data has to be refreshed, validated and
handed to the engine before a simulation can run.

#### Scenario: From a loaded file to a stepped result

- **WHEN** a caller prepares and then steps a session that was just loaded from a file
- **THEN** the run happens without the caller touching any scene toggle or operator

### Requirement: Preparation is explicit, repeatable and validated

Preparing SHALL refresh object identities, test every participating outline for
self-intersection, apply the requested solver name and parameter block, export
the engine payload and bind the engine, and SHALL report a summary of what it
bound. Preparing twice with the same arguments SHALL leave the same bound state.
A preparation that refuses MUST NOT touch the engine.

#### Scenario: An intersecting outline is refused

- **WHEN** preparation finds a pattern whose outline intersects itself
- **THEN** it reports the offending patterns and the engine is not touched

#### Scenario: Preparation reports what it bound

- **WHEN** preparation succeeds
- **THEN** the summary names the solver in effect and the object, vertex and stitch counts that were handed to the engine

### Requirement: Stepping is synchronous and counted in engine substeps

Stepping SHALL advance the engine by exactly the requested number of substeps on
the calling thread, apply the resulting positions to the scene meshes, and return
metrics. It MUST NOT depend on the scene frame timeline, on a timer, or on a
background thread, and the number of substeps MUST be a function of the arguments
alone.

#### Scenario: The same request advances the same number of substeps

- **WHEN** the same number of substeps is requested twice on the same prepared state
- **THEN** the reported substep count and frame count advance by that number both times, whatever the machine load

#### Scenario: Results are applied before the call returns

- **WHEN** a step call returns
- **THEN** the pattern meshes already show the positions of that substep

### Requirement: The live run and stepping exclude each other

Starting SHALL keep the existing timer-driven run for a session a human is
watching, and stopping SHALL end it. Stepping MUST refuse while a live run is
active, and starting MUST refuse while a stepping session is active. A refusal
SHALL name the active mode.

#### Scenario: Stepping during a live run

- **WHEN** a step is requested while a live run is active
- **THEN** the request is refused with the active mode named, and the live run continues

#### Scenario: Starting during a stepping session

- **WHEN** a live run is requested while a stepping session is active
- **THEN** the request is refused with the active mode named

### Requirement: State is readable in one call

The surface SHALL report the current mode, whether a prepared state exists,
whether the engine is bound, how many substeps have been simulated, and the
solver name and parameters in effect. The reported state MUST agree with the
scene: it MUST NOT claim simulated frames that no run produced.

#### Scenario: Before preparation

- **WHEN** the state is requested before anything was prepared
- **THEN** it reports that no prepared state exists and that no run is active

#### Scenario: During a live run

- **WHEN** the state is requested while a live run is active
- **THEN** it reports the live mode rather than the stepping mode

### Requirement: Results are readable as plain data

Reading back SHALL return the simulated vertex positions per pattern as plain
lists, in the pattern's local space and in world space, together with a count of
positions that are not finite. Reading MUST NOT move any vertex.

#### Scenario: Reading after a step

- **WHEN** positions are read after a step
- **THEN** the returned positions match the pattern meshes and the vertex count per pattern matches the mesh

#### Scenario: A non-finite position

- **WHEN** the simulation produced a position that is not finite
- **THEN** the count reports it instead of the call failing

### Requirement: Solver parameters are an explicit input

The solver name and its parameter block SHALL either be passed to preparation or
be read from the scene's solver panel, and the surface SHALL report which of the
two supplied the values in effect. Parameters passed to preparation MUST be the
ones the engine runs with.

#### Scenario: Parameters passed by the caller win

- **WHEN** a caller passes a parameter block to preparation while the scene panel holds different values
- **THEN** the engine runs with the caller's values and the summary says the caller supplied them

### Requirement: Engine statistics are passed through, never invented

Metrics SHALL include the substep count, the frame count and the wall time of the
call. Statistics the engine reports SHALL appear unchanged. A statistic the
engine does not report MUST be absent rather than reported as zero.

#### Scenario: Wall time is measured

- **WHEN** a step call returns
- **THEN** its metrics carry the wall time and the substep count of that call

#### Scenario: The engine reports no statistics

- **WHEN** the engine exposes no solver statistics
- **THEN** the metrics carry no solver-statistic entries

### Requirement: Engine failures during stepping are reported

A failure raised by the engine during a step SHALL reach the caller as that
error. It MUST NOT be discarded, and the session MUST NOT claim that it is still
stepping afterwards. The surface SHALL NOT promise per-substep progress that the
engine does not report.

#### Scenario: A failure during a step

- **WHEN** the engine raises an error during a step
- **THEN** the caller receives that error and the mode is no longer stepping

### Requirement: Resetting returns the scene to its rest state

Resetting SHALL discard the simulated result so that a following run starts from
the rest pose, and SHALL leave the patterns, the sewings and the solver parameters
unchanged.

#### Scenario: Reset then run

- **WHEN** a session is reset after a run and then stepped again
- **THEN** the first substep starts from the rest pose

### Requirement: Simulated positions are not an undoable edit

Applying simulated positions SHALL NOT create an undo step, so a long scripted
run does not fill the user's undo history.

#### Scenario: A scripted run leaves the undo stack alone

- **WHEN** a scripted run steps many substeps
- **THEN** the user's undo history is unchanged
