"""Solver selection and the solver parameter block, as scene data.

The engine reads its tuning from a flat name -> float map (`set_parameters`).
This module gives that map a UI: one enumeration for the solver, one typed
property per parameter (float, int, bool or enum, so the panel shows a slider,
a number field or a dropdown as appropriate), and a custom key/value list for
parameters that do not have a dedicated property yet - a new engine knob can be
used from the UI without touching this file.

`SolverParams.as_dict()` returns exactly the map the engine expects, and the
capture package records it verbatim, so a captured scene can be re-run with the
parameters it was tuned with.

Defaults are the engine's own defaults, not a tuned scene's values. Only
parameters the engine actually reads are listed (verified against the engine
sources): a knob that was removed from the engine must not come back as a UI
switch that does nothing.
"""

import json
import time

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

SOLVERS = ("PDNewton", "XPBD", "VBD", "Explicit")

FLOAT = "float"
INT = "int"
BOOL = "bool"
ENUM = "enum"


class ParameterSpec:
    """One engine parameter: name, UI text, kind, default, range and group."""

    __slots__ = ("name", "label", "kind", "default", "minimum", "maximum",
                 "group", "description", "items", "developer")

    def __init__(self, name, label, kind, default, minimum=0.0, maximum=0.0,
                 group="Solver", description="", items=None, developer=False):
        self.name = name
        self.label = label
        self.kind = kind
        self.default = default
        self.minimum = minimum
        self.maximum = maximum
        self.group = group
        self.description = description
        self.items = items
        self.developer = developer

    def make_property(self):
        if self.kind == FLOAT:
            return FloatProperty(name=self.label, description=self.description,
                                 default=self.default, min=self.minimum,
                                 max=self.maximum, precision=4)
        if self.kind == INT:
            return IntProperty(name=self.label, description=self.description,
                               default=int(self.default), min=int(self.minimum),
                               max=int(self.maximum))
        if self.kind == BOOL:
            return BoolProperty(name=self.label, description=self.description,
                                default=bool(self.default))
        if self.kind == ENUM:
            return EnumProperty(name=self.label, description=self.description,
                                items=self.items, default=str(self.default))
        raise ValueError(f"unknown parameter kind {self.kind}")


def _enum(*entries):
    """``(value, label)`` pairs as Blender enum items, keeping the numeric id."""
    return tuple((str(value), label, f"{label} ({value})") for value, label in entries)


FORCE_TYPES = _enum((0, "Spring"), (1, "IPC"))
BENDING_MODELS = _enum((0, "IBM quadratic"), (1, "DiscreteShells GN"), (2, "DiscreteShells AOGS"))
PLANAR_MODELS = _enum((0, "Spring-mass"), (1, "FEM_BW"))
LINEAR_SOLVERS = _enum((0, "PCG"), (1, "Block Jacobi"))


# Order is the panel order; the group name becomes a collapsible sub-panel.
PARAMETERS = (
    ParameterSpec("step_h", "Substep (s)", FLOAT, 0.0045, 1e-5, 0.05, "Time",
                  "Substep size the simulation manager feeds the engine"),
    ParameterSpec("smooth_times", "Smoothing passes", INT, 5, 0, 100, "Time",
                  "Frame-end Laplacian smoothing passes (anti blow-up)"),

    ParameterSpec("pd_iters", "Outer iterations", INT, 5, 1, 100, "Solver"),
    ParameterSpec("linear_iters", "Linear iterations", INT, 2, 1, 50, "Solver"),
    ParameterSpec("pd_hessian_every", "Assemble every N", INT, 1, 1, 10, "Solver",
                  "Chord / modified Newton: reuse the assembled Hessian for N-1 iterations"),
    ParameterSpec("linear_solver_type", "Linear solver", ENUM, 0, group="Solver",
                  description="Block Jacobi diverges on non-diagonally-dominant meshes",
                  items=LINEAR_SOLVERS),
    ParameterSpec("mask_stiff", "Mask stiffness", FLOAT, 2e3, 0.0, 1e6, "Solver"),
    ParameterSpec("max_vel", "Max velocity (m/s)", FLOAT, 10.0, 0.0, 1e4, "Solver"),
    ParameterSpec("gravity", "Gravity (m/s^2)", FLOAT, -9.8, -1e3, 1e3, "Solver"),
    ParameterSpec("average_mass_by_cloth", "Average mass", BOOL, False, group="Solver",
                  description="Share the total cloth mass over all cloth vertices"),

    ParameterSpec("velocity_damping", "Velocity damping (1/s)", FLOAT, 0.5, 0.0, 100.0, "Damping",
                  "End-of-step velocity floor"),
    ParameterSpec("creep_damping", "Creep damping (1/s)", FLOAT, 0.0, 0.0, 1000.0, "Damping",
                  "Extra decay below the creep speed; 0 disables it"),
    ParameterSpec("creep_speed", "Creep speed (m/s)", FLOAT, 0.03, 0.0, 10.0, "Damping"),

    ParameterSpec("base_spring_stiffness", "Membrane stiffness (N/m)", FLOAT, 4e3, 0.0, 1e7, "Membrane"),
    ParameterSpec("constitutive_model_planar", "Planar model", ENUM, 1, group="Membrane",
                  items=PLANAR_MODELS),
    ParameterSpec("bending_model", "Bending model", ENUM, 2, group="Membrane",
                  items=BENDING_MODELS),
    ParameterSpec("bending_k", "Bending stiffness", FLOAT, 1e-3, 0.0, 1e3, "Membrane"),
    ParameterSpec("strain_stiffen_start", "Stiffen above strain", FLOAT, 0.0, 0.0, 10.0, "Membrane",
                  "0 disables strain stiffening; 0.05 = 5% strain"),
    ParameterSpec("strain_stiffen_rate", "Stiffening rate", FLOAT, 2.0, 0.0, 100.0, "Membrane"),

    ParameterSpec("query_radius", "Contact query radius (m)", FLOAT, 1e-3, 0.0, 1.0, "Contact"),
    ParameterSpec("vf_force_k", "Vertex-face stiffness", FLOAT, 0.1, 0.0, 1e6, "Contact"),
    ParameterSpec("ee_force_k", "Edge-edge stiffness", FLOAT, 0.1, 0.0, 1e6, "Contact"),
    ParameterSpec("ef_force_k", "Edge-face stiffness", FLOAT, 50.5, 0.0, 1e6, "Contact"),
    ParameterSpec("vf_ground_k", "Ground stiffness", FLOAT, 4.0, 0.0, 1e6, "Contact"),
    ParameterSpec("vf_force_type", "Vertex-face force type", ENUM, 1, group="Contact",
                  items=FORCE_TYPES),
    ParameterSpec("ee_force_type", "Edge-edge force type", ENUM, 1, group="Contact",
                  items=FORCE_TYPES),
    ParameterSpec("ground", "Ground on", BOOL, True, group="Contact"),

    ParameterSpec("sewing_k", "Stitch stiffness", FLOAT, 4e4, 0.0, 1e9, "Sewing"),
    ParameterSpec("sewing_snap_dist", "Snap distance (m)", FLOAT, 3e-3, 0.0, 10.0, "Sewing"),
    ParameterSpec("sewing_snap_max_dist", "Snap ceiling (m)", FLOAT, 1.0, 0.0, 100.0, "Sewing",
                  "Ceiling of the ramped snap gate; box-layout stitches start far apart"),
    ParameterSpec("sewing_forced_connect_frame", "Activation frame", INT, 10, 0, 100000, "Sewing",
                  "Frame after which the stitch projection activates"),
    ParameterSpec("seam_merge_velocity", "Momentum-consistent merge", BOOL, True, group="Sewing"),

    ParameterSpec("debug_e_id", "Debug edge id", INT, -7, -1000000, 1000000, "Debug",
                  "Engine debug readout target", developer=True),
    ParameterSpec("debug_v_id", "Debug vertex id", INT, -6, -1000000, 1000000, "Debug",
                  "Engine debug readout target", developer=True),
)


def parameter_groups():
    """``[(group name, [spec, ...]), ...]`` in panel order."""
    groups = []
    for spec in PARAMETERS:
        for entry in groups:
            if entry[0] == spec.group:
                entry[1].append(spec)
                break
        else:
            groups.append((spec.group, [spec]))
    return groups


class CustomParameter(PropertyGroup):
    """One hand-written parameter: sent to the engine under ``key``."""

    key: StringProperty(name="Key", description="Engine parameter name")
    value: FloatProperty(name="Value", description="Value sent to the engine")


class SolverParams(PropertyGroup):
    """The solver name plus one typed property per engine parameter."""

    solver_name: EnumProperty(
        name="Solver",
        description="Solver the engine is set to before the next run",
        items=[(name, name, "", index) for index, name in enumerate(SOLVERS)],
        default=SOLVERS[0],
    )
    apply_on_start: BoolProperty(
        name="Apply on start",
        description="Send this block to the engine whenever a simulation starts",
        default=True,
    )
    developer_mode: BoolProperty(
        name="Developer mode",
        description="Also show the engine debug parameters and the custom parameter list",
        default=False,
    )
    custom: CollectionProperty(
        type=CustomParameter,
        name="Custom parameters",
        description="Parameters without a dedicated UI property, sent as-is",
    )
    custom_index: IntProperty(default=0)
    last_applied: StringProperty(
        name="Last applied",
        description="What the engine received the last time this block was applied",
        options={'SKIP_SAVE'},
    )

    def numeric_value(self, spec):
        """One parameter as the engine wants it: a float."""
        raw = getattr(self, spec.name)
        if spec.kind == BOOL:
            return 1.0 if raw else 0.0
        if spec.kind == ENUM:
            return float(int(raw))
        return float(raw)

    def as_dict(self):
        values = {spec.name: self.numeric_value(spec) for spec in PARAMETERS}
        for entry in self.custom:
            key = entry.key.strip()
            if key:
                values[key] = float(entry.value)
        return values

    def load_defaults(self):
        for spec in PARAMETERS:
            setattr(self, spec.name, spec.default)

    def load_values(self, values):
        """Apply a parameter map.

        Returns ``(known, custom)``: how many names went into the typed
        properties and how many were kept as custom entries (a name this UI
        does not know about is still usable).
        """
        known = {spec.name: spec for spec in PARAMETERS}
        known_count = 0
        custom_count = 0
        for name, value in (values or {}).items():
            spec = known.get(name)
            if spec is None:
                entry = self._custom_entry(name)
                entry.value = float(value)
                custom_count += 1
            elif spec.kind == BOOL:
                setattr(self, name, bool(value))
                known_count += 1
            elif spec.kind == ENUM:
                setattr(self, name, str(int(value)))
                known_count += 1
            else:
                setattr(self, name, value)
                known_count += 1
        return known_count, custom_count

    def _custom_entry(self, key):
        for entry in self.custom:
            if entry.key == key:
                return entry
        entry = self.custom.add()
        entry.key = key
        return entry

    def add_custom(self, key="", value=0.0):
        entry = self.custom.add()
        entry.key = key
        entry.value = value
        self.custom_index = len(self.custom) - 1
        return entry

    def remove_custom(self, index=None):
        if len(self.custom) == 0:
            return False
        index = self.custom_index if index is None else index
        if not (0 <= index < len(self.custom)):
            return False
        self.custom.remove(index)
        self.custom_index = max(0, min(index, len(self.custom) - 1))
        return True

    def import_file(self, path):
        with open(path, "r", encoding="utf-8") as handle:
            return self.load_values(json.load(handle))

    def apply_to_engine(self):
        """Hand the solver name and the parameter block to the engine module."""
        import Qianyi_DP as qydp

        values = self.as_dict()
        simulator = qydp.simulator
        simulator.set_solver(self.solver_name)
        simulator.set_parameters(values)
        self.last_applied = (
            f"{self.solver_name}, {len(values)} parameters at {time.strftime('%H:%M:%S')}")
        return simulator


class CaptureProps(PropertyGroup):
    """Where a capture package is written."""

    directory: StringProperty(
        name="Directory",
        description="Directory that receives scene.json and scene.npz",
        subtype='DIR_PATH',
    )
    per_scene_subfolder: BoolProperty(
        name="Subfolder per scene",
        description="Write into <directory>/<scene name> instead of <directory>",
        default=True,
    )
    last_capture: StringProperty(
        name="Last capture",
        description="Path of the last written package",
        options={'SKIP_SAVE'},
    )


for _spec in PARAMETERS:
    # Blender builds the RNA properties from the class annotations, so a
    # generated property has to appear in both places.
    _property = _spec.make_property()
    setattr(SolverParams, _spec.name, _property)
    SolverParams.__annotations__[_spec.name] = _property


classes = (
    CustomParameter,
    SolverParams,
    CaptureProps,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
