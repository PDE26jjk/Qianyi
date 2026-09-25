## Purpose

Lets a pattern maker state what each pattern is for in the simulation - solved,
excluded, held in place or stiff - so a garment can contain reference patterns,
frozen drapes and stiffened parts without leaving the add-on.

## ADDED Requirements

### Requirement: A pattern has exactly one simulation state

Every pattern SHALL carry a simulation state with the values `simulate`,
`excluded`, `frozen` and `stiffened`, defaulting to `simulate`. The state SHALL
be stored with the pattern, SHALL survive saving and reopening the file, and
SHALL be visible wherever the pattern is listed (the pattern list of the 2D
editor and the 3D sidebar of the selected pattern).

#### Scenario: Default state

- **WHEN** a pattern is created by the pen, by a generator or by a copy of
  another pattern
- **THEN** its state is `simulate` unless the source of the copy had another
  state, in which case the copy inherits it

#### Scenario: One state at a time

- **WHEN** a pattern's state is set to `frozen` while it was `stiffened`
- **THEN** the pattern reports `frozen` and no longer reports `stiffened`

### Requirement: An excluded pattern does not reach the engine

A pattern whose state is `excluded` SHALL NOT be solved and SHALL NOT act as a
collider. It SHALL be absent from the mesh list the simulation bridge builds,
and a simulation SHALL refuse to start when every participating pattern is
excluded, reporting that there is nothing to solve.

#### Scenario: Keep a reference pattern in the scene

- **WHEN** a project contains two patterns, one `simulate` and one `excluded`,
  and a simulation starts
- **THEN** the engine receives one cloth mesh, the excluded pattern's mesh is
  unchanged when the simulation advances, and the excluded pattern does not
  collide with the simulated one

#### Scenario: Nothing left to solve

- **WHEN** a simulation starts and every pattern in the scene is `excluded`
- **THEN** the start is refused with a report naming the reason, and the engine
  is not called

### Requirement: A frozen pattern holds its shape and still collides

A pattern whose state is `frozen` SHALL be handed to the engine as cloth whose
vertices are all pinned, so it stays where it is while the rest of the garment
drapes against it. Unfreezing SHALL remove the generated pin weights and
return the pattern to its previous state.

#### Scenario: Drape against a frozen pattern

- **WHEN** one pattern is `frozen` and another is `simulate`, the two overlap,
  and the simulation advances
- **THEN** the frozen pattern's simulated vertices do not move, the simulated
  pattern stays outside the frozen pattern as it does against a collider object,
  and both are present in the engine payload

#### Scenario: Unfreeze restores the pattern

- **WHEN** a frozen pattern is set back to `simulate`
- **THEN** the pin weights the freeze added are gone, the pattern moves under
  gravity again, and the vertex groups the user set by hand are unchanged

### Requirement: A stiffened pattern uses a per-pattern stiffness multiplier

A pattern whose state is `stiffened` SHALL be sent to the engine with its stretch
and bending values scaled by a per-pattern multiplier, while the fabric asset it
refers to stays unchanged for every other pattern. The multiplier SHALL be
editable per pattern with a documented range and a default that is stiff but not
rigid.

#### Scenario: Only the stiffened pattern changes

- **WHEN** two patterns share one fabric and one of them is set to `stiffened`
  with a multiplier of 4
- **THEN** the payload of the stiffened pattern carries stretch and bending
  scaled by 4, the other pattern's payload carries the fabric values unchanged,
  and the shared fabric asset on disk is not modified

#### Scenario: Multiplier is per pattern

- **WHEN** two patterns are both `stiffened` with different multipliers
- **THEN** each pattern's payload carries its own scale

### Requirement: State changes are undoable and simulation-safe

Setting a pattern's state SHALL be one undoable step. Changing the state of a
pattern while a simulation is running SHALL stop the simulation and report that
the change takes effect on the next start, so a run can never mix two payloads.

#### Scenario: Undo restores the state

- **WHEN** a pattern's state is changed and the user undoes once
- **THEN** the pattern reports its previous state and a following simulation uses
  it

#### Scenario: Changing state during a run

- **WHEN** the state of a participating pattern changes while a simulation is
  running
- **THEN** the simulation stops, the change is kept, and the report says the
  new state applies from the next start

### Requirement: State is scriptable and captured

The script surface SHALL expose reading and writing a pattern's state and its
stiffness multiplier, and the scene capture SHALL record the state of every
pattern so a captured scene reproduces the same payload.

#### Scenario: Script sets the state

- **WHEN** a script sets a pattern to `frozen` and then reads the pattern back
- **THEN** the read reports `frozen`, and a capture taken afterwards records
  that state for the pattern
