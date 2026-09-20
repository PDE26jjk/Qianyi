## Purpose

Lets a pattern maker move between the two things a drawn line can be inside a
panel - a cut and a boundary - and lay out repeated internal lines by distance,
which is how darts, fold lines and cut lines are actually made.

## ADDED Requirements

### Requirement: A panel can be cut along an internal line

The editor SHALL cut a panel along a selected internal line that crosses its
outline exactly twice, replacing the panel with two panels whose shared boundary
is the cut. Both resulting panels SHALL keep the source's fabric, granularity,
grain direction, collision layer, simulation state and generator link, and both
SHALL join the source's instance chain so a linked panel stays linked. The
command SHALL be one undo step. The cut SHALL be creatable as a sewing along the
new boundary through an option that is off by default, and when it is on the
report SHALL name the seam it created.

#### Scenario: Cut a panel in two

- **WHEN** an internal line that crosses the outline at two points is cut
- **THEN** two panels replace the original, their outlines share the cut
  geometry exactly, and the total area equals the original area

#### Scenario: Cut rejected

- **WHEN** the internal line does not cross the outline, crosses it once, or
  crosses it more than twice
- **THEN** the cut is refused with the reason and the panel is unchanged

#### Scenario: A closed line inside the panel is a hole

- **WHEN** the selected internal line is closed and lies inside the outline
- **THEN** the cut is refused with the reason, because a hole is the existing
  meaning of that line and the cut does not change it

#### Scenario: Sewings survive the cut

- **WHEN** a panel that carries sewings is cut
- **THEN** every sewing whose edge is unchanged still points at that edge, a
  sewing whose edge was split follows the piece that replaced it, and a sewing
  that can no longer be resolved is dropped with a report naming it

#### Scenario: Linked halves

- **WHEN** a panel that has copies is cut
- **THEN** both halves join the same instance chain as the source, so the
  chain's members stay in step

#### Scenario: Cutting without a seam

- **WHEN** the cut is applied with the seam option off
- **THEN** the two panels share the cut boundary as plain outline edges and the
  seam list is unchanged

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

### Requirement: Internal lines can be repeated at a signed distance

The editor SHALL create a requested number of additional internal lines offset
from a source line - an internal line or a run of outline edges - by a signed
distance along the local normal, in one undo step. Each generated line SHALL be
processed according to one of three end modes: `CLIP` trims it to the outline,
`EXTEND_TO_OUTLINE` projects both of its ends onto the outline, and `KEEP`
leaves it as the offset produced it. `EXTEND_TO_OUTLINE` SHALL target the
outline only and SHALL NOT be extended against other internal lines.

#### Scenario: Five fold lines at 20 mm

- **WHEN** five internal lines are requested at 20 mm from a source line across
  a panel that is wide enough
- **THEN** five internal lines are created at 20, 40, 60, 80 and 100 mm, each
  spanning the panel according to the selected end mode

#### Scenario: Negative distance offsets the other way

- **WHEN** the same repeat is requested with a negative distance
- **THEN** the lines are created on the other side of the source line

#### Scenario: Ends projected onto the outline

- **WHEN** `EXTEND_TO_OUTLINE` is selected and an offset line ends inside the
  panel
- **THEN** both of its ends are moved onto the nearest point of the outline and
  the line spans the panel

#### Scenario: An offset line leaves the panel

- **WHEN** an offset line lies completely outside the outline
- **THEN** no internal line is created for it and the report names the offset
  that was dropped

### Requirement: An offset line is never left self-crossing

Because an offset beyond the local radius of curvature or past a concave corner
produces a self-crossing polyline, the editor SHALL de-loop every generated
offset before it is used: it SHALL find the offset's self-intersections, remove
the loops they enclose, and keep the surviving skeleton. A generated line that
degenerates completely SHALL be dropped, and the report SHALL say which offset
was shortened or dropped. The rule SHALL apply in all three end modes, because a
self-crossing internal line makes the in/out classification of its sections and
the seam sampling undefined.

#### Scenario: Offset past a concave corner

- **WHEN** an offset is generated past a concave corner whose adjacent edges are
  shorter than the distance where the offset segments would meet
- **THEN** the crossing and the loop it encloses are removed and the surviving
  line is reported as shortened

#### Scenario: Offset beyond the local radius

- **WHEN** an offset distance exceeds the radius of a concave arc in the source
  line
- **THEN** the arc's contribution to the offset is removed and the report names
  the shortened line

#### Scenario: Fully degenerate offset

- **WHEN** de-looping leaves an offset with nothing in it
- **THEN** no internal line is created for that distance and the report names it

### Requirement: An internal line can be a sewing side

A sewing side SHALL be able to reference an internal line as well as an outline
edge run, so a dart or a fold line can be sewn shut, and the seam SHALL render
and stitch exactly as a seam between outline edges does.

#### Scenario: Sew a dart shut

- **WHEN** a seam is created between an internal line and a run of outline edges
- **THEN** the seam is created, its stitches pair the internal line's vertices
  with the outline run, and the simulated result pulls the two together
