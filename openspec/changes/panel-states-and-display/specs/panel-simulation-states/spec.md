## Purpose

Lets a pattern maker state what each panel is for in the simulation - solved,
excluded, held in place or stiff - so a garment can contain reference panels,
frozen drapes and stiffened parts without leaving the add-on.

## ADDED Requirements

### Requirement: A panel has exactly one simulation state

Every pattern SHALL carry a simulation state with the values `simulate`,
`excluded`, `frozen` and `stiffened`, defaulting to `simulate`. The state SHALL
be stored with the pattern, SHALL survive saving and reopening the file, and
SHALL be visible wherever the panel is listed (the pattern list of the 2D
editor and the 3D sidebar of the selected panel).

#### Scenario: Default state

- **WHEN** a panel is created by the pen, by a generator or by a copy of
  another panel
- **THEN** its state is `simulate` unless the source of the copy had another
  state, in which case the copy inherits it

#### Scenario: One state at a time

- **WHEN** a panel's state is set to `frozen` while it was `stiffened`
- **THEN** the panel reports `frozen` and no longer reports `stiffened`

### Requirement: An excluded panel does not reach the engine

A panel whose state is `excluded` SHALL NOT be solved and SHALL NOT act as a
collider. It SHALL be absent from the mesh list the simulation bridge builds,
and a simulation SHALL refuse to start when every participating panel is
excluded, reporting that there is nothing to solve.

#### Scenario: Keep a reference panel in the scene

- **WHEN** a project contains two panels, one `simulate` and one `excluded`,
  and a simulation starts
- **THEN** the engine receives one cloth mesh, the excluded panel's mesh is
  unchanged when the simulation advances, and the excluded panel does not
  collide with the simulated one

#### Scenario: Nothing left to solve

- **WHEN** a simulation starts and every panel in the scene is `excluded`
- **THEN** the start is refused with a report naming the reason, and the engine
  is not called

### Requirement: A frozen panel holds its shape and still collides

A panel whose state is `frozen` SHALL be handed to the engine as cloth whose
vertices are all pinned, so it stays where it is while the rest of the garment
drapes against it. Unfreezing SHALL remove the generated pin weights and
return the panel to its previous state.

#### Scenario: Drape against a frozen panel

- **WHEN** one panel is `frozen` and another is `simulate`, the two overlap,
  and the simulation advances
- **THEN** the frozen panel's simulated vertices do not move, the simulated
  panel stays outside the frozen panel as it does against a collider object,
  and both are present in the engine payload

#### Scenario: Unfreeze restores the panel

- **WHEN** a frozen panel is set back to `simulate`
- **THEN** the pin weights the freeze added are gone, the panel moves under
  gravity again, and the vertex groups the user set by hand are unchanged

### Requirement: A stiffened panel uses a per-panel stiffness multiplier

A panel whose state is `stiffened` SHALL be sent to the engine with its stretch
and bending values scaled by a per-panel multiplier, while the fabric asset it
refers to stays unchanged for every other panel. The multiplier SHALL be
editable per panel with a documented range and a default that is stiff but not
rigid.

#### Scenario: Only the stiffened panel changes

- **WHEN** two panels share one fabric and one of them is set to `stiffened`
  with a multiplier of 4
- **THEN** the payload of the stiffened panel carries stretch and bending
  scaled by 4, the other panel's payload carries the fabric values unchanged,
  and the shared fabric asset on disk is not modified

#### Scenario: Multiplier is per panel

- **WHEN** two panels are both `stiffened` with different multipliers
- **THEN** each panel's payload carries its own scale

### Requirement: State changes are undoable and simulation-safe

Setting a panel's state SHALL be one undoable step. Changing the state of a
panel while a simulation is running SHALL stop the simulation and report that
the change takes effect on the next start, so a run can never mix two payloads.

#### Scenario: Undo restores the state

- **WHEN** a panel's state is changed and the user undoes once
- **THEN** the panel reports its previous state and a following simulation uses
  it

#### Scenario: Changing state during a run

- **WHEN** the state of a participating panel changes while a simulation is
  running
- **THEN** the simulation stops, the change is kept, and the report says the
  new state applies from the next start

### Requirement: State is scriptable and captured

The script surface SHALL expose reading and writing a panel's state and its
stiffness multiplier, and the scene capture SHALL record the state of every
panel so a captured scene reproduces the same payload.

#### Scenario: Script sets the state

- **WHEN** a script sets a panel to `frozen` and then reads the panel back
- **THEN** the read reports `frozen`, and a capture taken afterwards records
  that state for the panel
