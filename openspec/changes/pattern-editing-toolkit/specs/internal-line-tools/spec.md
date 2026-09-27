## Purpose

Lets a pattern maker move between the two things a drawn line can be inside a
pattern - a cut and a boundary - and lay out repeated internal lines by distance,
which is how darts, fold lines and cut lines are actually made.

## ADDED Requirements

### Requirement: A pattern can be cut along an internal line

The editor SHALL cut a pattern along a selected internal line that crosses its
outline exactly twice, replacing the pattern with two patterns whose shared boundary
is the cut. Both resulting patterns SHALL keep the source's fabric, granularity,
grain direction, collision layer, simulation state and generator link, and both
SHALL join the source's instance chain so a linked pattern stays linked. The
command SHALL be one undo step. The cut SHALL be creatable as a sewing along the
new boundary through an option that is off by default, and when it is on the
report SHALL name the seam it created.

#### Scenario: Cut a pattern in two

- **WHEN** an internal line that crosses the outline at two points is cut
- **THEN** two patterns replace the original, their outlines share the cut
  geometry exactly, and the total area equals the original area

#### Scenario: Cut rejected

- **WHEN** the internal line does not cross the outline, crosses it once, or
  crosses it more than twice
- **THEN** the cut is refused with the reason and the pattern is unchanged

#### Scenario: A closed line inside the pattern is a hole

- **WHEN** the selected internal line is closed and lies inside the outline
- **THEN** the cut is refused with the reason, because a hole is the existing
  meaning of that line and the cut does not change it

#### Scenario: Sewings survive the cut

- **WHEN** a pattern that carries sewings is cut
- **THEN** every sewing whose edge is unchanged still points at that edge, a
  sewing whose edge was split follows the piece that replaced it, and a sewing
  that can no longer be resolved is dropped with a report naming it

#### Scenario: Linked halves

- **WHEN** a pattern that has copies is cut
- **THEN** both halves join the same instance chain as the source, so the
  chain's members stay in step

#### Scenario: Cutting without a seam

- **WHEN** the cut is applied with the seam option off
- **THEN** the two patterns share the cut boundary as plain outline edges and the
  seam list is unchanged

### Requirement: A chain is copied at a distance, and is not itself changed

The editor SHALL write internal lines offset from the selected chain - a run of
consecutive outline edges, or an internal line - along that chain's own normal,
in one undo step. How far apart the lines are SHALL be either a distance, with a
line at it, twice it and so on for the number asked for, or the chain's own length
divided into equal parts, with a line at every division point inside it. The chain
itself SHALL be left exactly as it was, and the outline SHALL NOT be re-routed. A
line that lies outside the outline altogether SHALL NOT be written, and the report
SHALL name it.

#### Scenario: Five fold lines at 20 mm

- **WHEN** five internal lines are requested at 20 mm from a source across a
  pattern that is wide enough
- **THEN** five internal lines are created at 20, 40, 60, 80 and 100 mm, and the
  source is the shape it was

#### Scenario: A pleated edge

- **WHEN** one edge of a panel is the source and its length is divided into
  equal parts
- **THEN** a line is written at every division point inside it, one part apart,
  and the outline of the panel is unchanged

#### Scenario: Negative distance offsets the other way

- **WHEN** the same repeat is requested with a negative distance
- **THEN** the lines are created on the other side of the source line

#### Scenario: An offset line leaves the pattern

- **WHEN** an offset line lies completely outside the outline
- **THEN** no internal line is created for it and the report names the offset
  that was dropped

### Requirement: The ends of an internal line can be put on the outline

The editor SHALL put both ends of the selected internal line on the outline, in
one undo step, in one of two modes: `TRIM` cuts back the parts that lie outside
the pattern and lands the ends where the line crosses the outline, and `EXTEND`
moves an end that lies inside out to the nearest point of the outline. An end
that lies outside SHALL be cut back in either mode. The pieces of the line
between the two ends SHALL keep their own identity, so a seam on one of them
still names it. A line that lies outside the pattern altogether, and a trim that
would leave nothing of the line, SHALL be refused with the line as it was.

#### Scenario: A line that stops short spans the pattern

- **WHEN** `EXTEND` is applied to an internal line whose ends lie inside the
  pattern
- **THEN** both ends are moved onto the nearest point of the outline and the line
  spans the pattern

#### Scenario: A line that pokes out is cut back

- **WHEN** `TRIM` is applied to an internal line whose ends lie outside the
  pattern
- **THEN** the ends land on the outline, the pieces that lay outside it go, and
  the pieces between them are the pieces they were

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
