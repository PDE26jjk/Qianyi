## Purpose

Adds the two primitives every pattern maker starts from, a rectangle and a
circle, as parametric library components, so a panel can be placed from the
library and adjusted by numbers instead of drawn by hand.

## ADDED Requirements

### Requirement: A rectangle generator exists in the panel library

The panel library SHALL offer a rectangle component with width, height, corner
radius and rotation parameters, in millimetres and degrees, each with a range
and a default. The generated panel SHALL be one closed counter-clockwise
outline whose edges carry stable labels.

#### Scenario: Place a rectangle

- **WHEN** the rectangle component is added with a width of 300 mm, a height of
  200 mm and no corner radius
- **THEN** one panel with four straight edges and the requested area appears,
  and its edge labels survive a rebuild with different parameters

#### Scenario: Corner radius

- **WHEN** the corner radius parameter is set to a value the sides allow
- **THEN** each corner becomes an arc of that radius and the outline stays a
  single closed loop

### Requirement: A circle and an annulus generator exist

The panel library SHALL offer a circle component with a radius (or diameter)
and a segment count, and an annulus component that additionally takes an inner
radius. The circle SHALL be one closed outline; the annulus SHALL be one closed
outline with a hole.

#### Scenario: Place a circle

- **WHEN** the circle component is placed with a radius of 150 mm and 48 segments
- **THEN** the panel is a closed loop of 48 arcs whose vertices lie within the
  sampling tolerance of the requested radius

#### Scenario: Place an annulus

- **WHEN** the annulus component is placed with an outer radius of 150 mm and an
  inner radius of 60 mm
- **THEN** the panel has one outline and one hole outline, and the mesh stage
  produces no triangles inside the hole

### Requirement: Placed primitives stay parametric

A component placed from the library SHALL remain a generator: changing a
parameter SHALL rebuild it in place, keeping its edge labels, its sewings and
its simulation state, and the user SHALL be able to detach it into an ordinary
editable panel. The rebuild report SHALL name any panel it could not rebuild.

#### Scenario: Rebuild keeps the sewings

- **WHEN** a rectangle already sewn to another panel has its width changed
- **THEN** the seam still connects the same labelled edges, the report says the
  panel was rebuilt in place, and any seam that could not be remapped is named

#### Scenario: Detach

- **WHEN** a placed circle is detached
- **THEN** its panel becomes an ordinary panel with the same outline and
  sewings, and editing it is no longer refused as a generated panel

#### Scenario: Invalid parameters

- **WHEN** a parameter outside its declared range is requested
- **THEN** it is clamped to the nearest bound and the written value is reported
