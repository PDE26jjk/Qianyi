## Purpose

Keeps the pattern editor's mode-based structure while removing what made it feel
bureaucratic: a tool now activates the mode it works in, a selection survives a
mode change, and a geometry command is written so Blender's own adjust-last-
operation panel can change its parameters after the fact.

## ADDED Requirements

### Requirement: Picking a tool activates the mode that tool works in

Activating an editing tool SHALL put the pattern editor into the mode and sub
mode that tool needs, from the toolbar and from the operator alike, so that a
tool is never silently unavailable because the header happens to show another
mode. The two settings SHALL be written in one place, and a tool whose mode is
already active SHALL change nothing.

#### Scenario: A tool picked in the wrong mode

- **WHEN** the header shows the sewing mode and the add-vertex tool is activated
- **THEN** the editor switches to the edge mode with the add-vertex sub mode,
  and the next click on an edge splits it as the tool promises

#### Scenario: Already in the right mode

- **WHEN** a tool is activated while the editor is already in its mode
- **THEN** nothing about the mode changes

#### Scenario: No silent no-op

- **WHEN** any editing tool is activated while a project is being edited
- **THEN** its operator is available (its `poll` does not depend on the mode),
  so a click either does the work or reports why it cannot

### Requirement: A selection survives a mode change

Changing the mode SHALL NOT discard another mode's selection, and the elements
selected in another mode SHALL be drawn dimmed while the current mode is active,
so a pattern maker can make a selection, do something else, and still see and
reuse what was selected. Switching back SHALL show that selection as the
current one again.

#### Scenario: Edges selected, then the sewing mode

- **WHEN** two edges are selected in the edge mode and the editor switches to
  the sewing mode
- **THEN** the two edges are still selected and are drawn dimmed, and switching
  back to the edge mode shows them as selected again

#### Scenario: Patterns selected, then the edge mode

- **WHEN** a pattern is selected in the pattern mode and the editor switches to
  the edge mode
- **THEN** the pattern is still selected and still drawn with its selection
  outline

### Requirement: A geometry command acts on the selection

A command that changes geometry SHALL act on the elements selected when it
runs, not on whatever the pointer happens to be over; hovering SHALL only decide
what a click selects. A command with nothing usable selected SHALL say so
instead of guessing a target.

#### Scenario: Acting on a selection

- **WHEN** a command that needs one edge is run with one edge selected
- **THEN** it acts on that edge

#### Scenario: Nothing selected

- **WHEN** such a command is run with an empty selection
- **THEN** it reports that it needs a selection and changes nothing

#### Scenario: More selected than the command can use

- **WHEN** several edges are selected and the command needs one
- **THEN** it says how many it found and changes nothing, rather than picking
  one of them by itself

### Requirement: A geometry command can be re-run from Blender's redo panel

A selection-driven geometry command SHALL be a registered, undoable operator
whose parameters are RNA properties, and it SHALL be able to compute its result
from the state that existed before it ran. Changing one of those parameters in
Blender's adjust-last-operation panel SHALL therefore apply the command again
with the new value, from the original state, rather than applying it a second
time.

#### Scenario: Changing a parameter after the fact

- **WHEN** an edge has been divided by a target length and the length is then
  changed in the adjust-last-operation panel
- **THEN** the edge is divided again with the new length, the previous division
  is not left behind, and there is one undo step for the result

#### Scenario: Re-running does not depend on the previous run

- **WHEN** the same command is re-run with the parameters it already used
- **THEN** the result is the same as the first run, and no element is added
  twice

#### Scenario: Caches are rebuilt

- **WHEN** a command is re-run after Blender rolled its undo step back
- **THEN** object identities are refreshed and the derived mesh data is rebuilt
  before the command computes, so the re-run does not read a stale cache

### Requirement: Derived work is recomputed, never accumulated

Work a command derives from the state it changes - remapping the sewings that
referenced a changed edge, re-pointing a copy's sewings, dropping what can no
longer be resolved - SHALL be computed from the state before the operation, so
that a re-run produces the same result and the same report. It MUST NOT be
computed by modifying the result of the previous run.

#### Scenario: A seam on a divided edge

- **WHEN** an edge that a seam uses is divided, and the change is then re-run
  with a different segment count
- **THEN** the seam points at the piece that replaced its edge in both runs,
  and the seam list is what the new run computed, not the first run's list
  remapped again

#### Scenario: A seam that cannot be remapped

- **WHEN** a seam's edge disappears in a topology change
- **THEN** the seam is dropped and reported, and a re-run of the same command
  reports the same drop rather than dropping a second seam

### Requirement: The gesture-driven tools are documented exceptions

The tools whose parameters are the gesture itself - the pattern pen, the
internal-line pen, the sewing tool, box select and the 3D pick - SHALL NOT be
required to offer adjustable parameters, and the shipped documentation SHALL
name them and say why.

#### Scenario: A gesture tool after it runs

- **WHEN** a seam is created by clicking two edges
- **THEN** the tool finishes without an adjustable parameter pattern, which the
  documentation explains
