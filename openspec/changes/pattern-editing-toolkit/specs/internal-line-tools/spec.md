## Purpose

Lets a pattern maker move between the two things a drawn line can be inside a
panel - a cut and a boundary - and lay out repeated internal lines by distance,
which is how darts, fold lines and cut lines are actually made.

## ADDED Requirements

### Requirement: A panel can be cut along an internal line

The editor SHALL cut a panel along a selected internal line that crosses its
outline twice, replacing the panel with two panels whose shared boundary is the
cut. Both resulting panels SHALL keep the source's fabric, granularity, grain
direction, collision layer, simulation state and generator link; the command
SHALL be one undo step.

#### Scenario: Cut a panel in two

- **WHEN** a closed internal line that crosses the outline at two points is cut
- **THEN** two panels replace the original, their outlines share the cut
  geometry exactly, and the total area equals the original area

#### Scenario: Sewings survive the cut

- **WHEN** a panel that carries sewings is cut
- **THEN** every sewing whose edge is unchanged still points at that edge, a
  sewing whose edge was split follows the piece that replaced it, and a sewing
  that can no longer be resolved is dropped with a report naming it

#### Scenario: Cut rejected

- **WHEN** the internal line does not cross the outline, crosses it once, or
  crosses it more than twice
- **THEN** the cut is refused with the reason and the panel is unchanged

### Requirement: A run of outline edges can become an internal line

The editor SHALL convert a run of consecutive outline edges into an internal
line, re-routing the outline along the straight chord between the run's end
points. It SHALL refuse when the run is the whole outline or when the chord
crosses the remaining outline.

#### Scenario: Inset a corner as an internal line

- **WHEN** two consecutive edges of a panel are converted into an internal line
- **THEN** the outline is the chord between the run's ends, the run's geometry
  is an internal line inside the panel, and the panel area is smaller by the
  triangle between the chord and the run

### Requirement: Internal lines can be repeated at a distance

The editor SHALL create a requested number of additional internal lines offset
from a source internal line (or from a run of outline edges) by a signed
distance, in one undo step. Each generated line SHALL be clipped to the panel,
and the part outside the outline SHALL be marked as outside rather than
silently kept.

#### Scenario: Five fold lines at 20 mm

- **WHEN** five internal lines are requested at 20 mm from a source line across
  a panel that is wide enough
- **THEN** five internal lines are created at 20, 40, 60, 80 and 100 mm, each
  spanning the panel, and the report names any line that was clipped

#### Scenario: Offset leaves the panel

- **WHEN** an offset line lies completely outside the outline
- **THEN** no internal line is created for it and the report names the offset
  that was dropped

### Requirement: An internal line can be a sewing side

A sewing side SHALL be able to reference an internal line as well as an outline
edge run, so a dart or a fold line can be sewn shut, and the seam SHALL render
and stitch exactly as a seam between outline edges does.

#### Scenario: Sew a dart shut

- **WHEN** a seam is created between an internal line and a run of outline edges
- **THEN** the seam is created, its stitches pair the internal line's vertices
  with the outline run, and the simulated result pulls the two together
