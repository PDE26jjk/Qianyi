"""Unit tests for the panel library.

The library must work without Blender, so this file imports it straight from
disk instead of going through the add-on package (whose __init__ imports bpy):

    python Qianyi/panellib/tests/run_tests.py

Only numpy is required.
"""

from __future__ import annotations

import importlib.util
import math
import sys
import unittest
from pathlib import Path

import numpy as np

LIB_DIR = Path(__file__).resolve().parents[1]


def _load_panellib():
    """Import the library as a top-level package named ``panellib``."""
    spec = importlib.util.spec_from_file_location(
        "panellib", LIB_DIR / "__init__.py",
        submodule_search_locations=[str(LIB_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["panellib"] = module
    spec.loader.exec_module(module)
    return module


panellib = _load_panellib()

from panellib import component, registry  # noqa: E402
from panellib.curves import Arc, Bezier, FrontendEdge, Line, Polyline, signed_area  # noqa: E402
from panellib.noise import noise_run  # noqa: E402
from panellib import preview  # noqa: E402
from panellib.land import land_panel, landed_boundary  # noqa: E402
from panellib.spec import (  # noqa: E402
    EdgeSpec,
    PanelSpec,
    PanelSpecError,
    auto_label,
    finalize_panel,
    reference_shift,
)


class CurveTests(unittest.TestCase):
    def test_line_reduces_to_a_straight_edge(self):
        edges = Line().to_frontend((0.0, 0.0), (10.0, 0.0))
        self.assertEqual(edges, [FrontendEdge("straight", ((0.0, 0.0), (10.0, 0.0)))])

    def test_quadratic_bezier_is_raised_to_cubic_exactly(self):
        p0, p1, q = (0.0, 0.0), (10.0, 0.0), (5.0, 4.0)
        curve = Bezier(controls=(q,))
        edges = curve.to_frontend(p0, p1)
        self.assertEqual(len(edges), 1)
        kind, points = edges[0].kind, edges[0].points
        self.assertEqual(kind, "bezier")
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            s = 1.0 - t
            expected = (s * s * p0[0] + 2 * s * t * q[0] + t * t * p1[0],
                        s * s * p0[1] + 2 * s * t * q[1] + t * t * p1[1])
            got = _bezier_point(points, t)
            self.assertLess(math.dist(expected, got), 1e-9)

    def test_arc_stays_close_to_the_true_circle(self):
        p0, p1 = (0.0, 0.0), (100.0, 0.0)
        curve = Arc(bulge=0.4)
        center, radius, _, _ = curve.geometry(p0, p1)
        for t in np.linspace(0.0, 1.0, 25):
            point = np.asarray(curve.point(p0, p1, float(t)))
            self.assertLess(abs(np.linalg.norm(point - center) - radius), 1e-9)
        # A positive bulge bends to the left of p0 -> p1.
        self.assertGreater(curve.point(p0, p1, 0.5)[1], 0.0)
        # The straight-line approximation of the arc is what the editor sees.
        max_deviation = 0.0
        for edge in curve.to_frontend(p0, p1):
            for t in np.linspace(0.0, 1.0, 9):
                point = np.asarray(_bezier_point(edge.points, float(t)))
                max_deviation = max(max_deviation,
                                    abs(np.linalg.norm(point - center) - radius))
        self.assertLess(max_deviation, 0.05)

    def test_arc_with_zero_bulge_is_straight(self):
        edges = Arc(bulge=0.0).to_frontend((0.0, 0.0), (10.0, 0.0))
        self.assertEqual(edges[0].kind, "straight")

    def test_polyline_becomes_consecutive_straight_edges(self):
        points = ((0.0, 0.0), (5.0, 1.0), (10.0, 0.0))
        edges = Polyline(points=points).to_frontend((0.0, 0.0), (10.0, 0.0))
        self.assertEqual([edge.kind for edge in edges], ["straight", "straight"])
        self.assertEqual(edges[0].points[1], (5.0, 1.0))

    def test_polyline_must_match_its_vertices(self):
        curve = Polyline(points=((0.0, 0.0), (10.0, 5.0)))
        with self.assertRaises(ValueError):
            curve.to_frontend((0.0, 0.0), (10.0, 0.0))


class NoiseTests(unittest.TestCase):
    def test_same_seed_gives_the_same_run(self):
        first = noise_run((0.0, 0.0), (100.0, 0.0), 5.0, 20.0, 32, 7)
        second = noise_run((0.0, 0.0), (100.0, 0.0), 5.0, 20.0, 32, 7)
        np.testing.assert_allclose(np.asarray(first.points), np.asarray(second.points))

    def test_different_seed_gives_a_different_run(self):
        first = noise_run((0.0, 0.0), (100.0, 0.0), 5.0, 20.0, 32, 7)
        second = noise_run((0.0, 0.0), (100.0, 0.0), 5.0, 20.0, 32, 8)
        self.assertFalse(np.allclose(np.asarray(first.points), np.asarray(second.points)))

    def test_run_starts_and_ends_on_its_vertices(self):
        run = noise_run((0.0, 0.0), (100.0, 20.0), 5.0, 20.0, 32, 3)
        self.assertLess(math.dist(run.points[0], (0.0, 0.0)), 1e-9)
        self.assertLess(math.dist(run.points[-1], (100.0, 20.0)), 1e-9)
        # Points are the requested count, and the run can be handed to a panel.
        self.assertEqual(len(run.points), 32)
        run.to_frontend((0.0, 0.0), (100.0, 20.0))


class PanelSpecTests(unittest.TestCase):
    def _square(self, name="square", labels=("hem", "", "", "")):
        vertices = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        edges = [EdgeSpec(i, (i + 1) % 4, Line(), name=labels[i]) for i in range(4)]
        return PanelSpec(name=name, vertices=vertices, edges=edges)

    def test_unnamed_edges_get_positional_labels(self):
        panel = finalize_panel(self._square())
        self.assertEqual([edge.name for edge in panel.edges],
                         ["hem", auto_label(1), auto_label(2), auto_label(3)])

    def test_duplicate_labels_are_rejected(self):
        with self.assertRaises(PanelSpecError):
            finalize_panel(self._square(labels=("hem", "hem", "", "")))

    def test_reserved_positional_label_is_rejected(self):
        with self.assertRaises(PanelSpecError):
            finalize_panel(self._square(labels=("edge1", "", "", "")))

    def test_open_loop_is_rejected(self):
        panel = self._square()
        panel.edges[2] = EdgeSpec(2, 0, Line())
        with self.assertRaises(PanelSpecError):
            finalize_panel(panel)

    def test_clockwise_panel_is_rejected(self):
        panel = self._square()
        panel.vertices.reverse()
        with self.assertRaises(PanelSpecError):
            finalize_panel(panel)

    def test_counter_clockwise_area_is_positive(self):
        self.assertGreater(signed_area([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]), 0.0)

    def test_finalize_does_not_mutate_its_input(self):
        panel = self._square()
        finalize_panel(panel)
        self.assertEqual(panel.edges[1].name, "")


class ComponentTests(unittest.TestCase):
    def setUp(self):
        registry.load_builtin()

    def test_registry_lists_the_builtin_components(self):
        self.assertIn("square", registry.component_ids())
        self.assertIn("waistband", registry.component_ids())
        info = registry.info("square")
        self.assertTrue(info.label)
        self.assertIn("width", info.params)

    def test_same_params_give_the_same_result(self):
        first = component.build_component("square", {"width": 300.0, "height": 400.0})
        second = component.build_component("square", {"width": 300.0, "height": 400.0})
        self.assertEqual([p.name for p in first.panels], [p.name for p in second.panels])
        for a, b in zip(first.panels, second.panels):
            np.testing.assert_allclose(np.asarray(a.vertices), np.asarray(b.vertices))
            self.assertEqual([e.name for e in a.edges], [e.name for e in b.edges])

    def test_missing_params_fall_back_to_defaults(self):
        spec = component.build_component("square", {"width": 100.0})
        self.assertEqual(spec.params["height"], 400.0)

    def test_shape_change_keeps_the_reference_point(self):
        base = component.build_component("square", {"width": 300.0, "height": 400.0})
        changed = component.build_component("square", {"width": 300.0, "height": 450.0})
        shift = reference_shift(base.panels[0], changed.panels[0])
        self.assertLess(shift, 1e-9)

    def test_waistband_is_two_bands_with_a_waist_edge(self):
        spec = component.build_component("waistband", {"waist_length": 800.0})
        self.assertEqual([p.name for p in spec.panels], ["band_front", "band_back"])
        for panel in spec.panels:
            self.assertEqual([edge.name for edge in panel.edges],
                             ["side_left", "bottom", "side_right", "waist"])


class LandingTests(unittest.TestCase):
    def setUp(self):
        registry.load_builtin()

    def test_landed_panel_becomes_editor_edges(self):
        spec = component.build_component("waistband", {"waist_length": 800.0,
                                                       "waist_curve": 20.0})
        landed = land_panel(spec.panels[0])
        self.assertEqual(len(landed.vertices), 4)
        self.assertEqual([edge.kind for edge in landed.edges],
                         ["straight", "straight", "straight", "bezier"])
        self.assertEqual([edge.name for edge in landed.edges],
                         ["side_left", "bottom", "side_right", "waist"])

    def test_boundary_is_one_closed_loop(self):
        spec = component.build_component("square", {"width": 200.0, "height": 300.0})
        points = landed_boundary(land_panel(spec.panels[0]))
        self.assertEqual(points.shape[1], 2)
        self.assertGreater(points.shape[0], 8)
        self.assertLess(np.linalg.norm(points[0] - np.array((0.0, 0.0))), 1e-3)

    def test_preview_renders_a_thumbnail(self):
        spec = component.build_component("waistband")
        image = preview.render_preview([land_panel(panel) for panel in spec.panels],
                                       size=32)
        self.assertEqual(image.shape, (32, 32, 4))
        self.assertGreater(float(image.std()), 0.0)      # something was drawn
        self.assertEqual(preview.to_pixels(image).shape, (32 * 32 * 4,))


def _bezier_point(points, t):
    p0, c1, c2, p1 = points
    s = 1.0 - t
    return (s ** 3 * p0[0] + 3 * s * s * t * c1[0] + 3 * s * t * t * c2[0] + t ** 3 * p1[0],
            s ** 3 * p0[1] + 3 * s * s * t * c1[1] + 3 * s * t * t * c2[1] + t ** 3 * p1[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
