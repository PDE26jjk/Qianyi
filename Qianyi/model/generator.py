"""Panel generators: parametric panel sources stored in a project."""

from __future__ import annotations

import json
import time

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from .. import global_data
from ..utilities.console import console
from .model_data import ModelData, define_temp_prop


def _param_changed(param, context) -> None:
    """A parameter value changed: rebuild the generator that owns it."""
    generator = owner_of_param(param)
    project = param.id_data
    if generator is None or project is None:
        return
    if generator.applying or generator.suppress_rebuild:
        return
    from ..generators import apply_generator
    from ..utilities.console import console

    # A property update callback must never raise: Blender calls it from inside
    # RNA and an exception here takes the UI down with it. apply_generator
    # reports through the console and returns a report instead.
    if _should_defer(generator):
        _defer_rebuild(generator)
        return
    _rebuild_now(generator)


REBUILD_DELAY = 0.2          # seconds after the last parameter change
HEAVY_EDGE_COUNT = 300       # a rebuild that costs this much is worth waiting for


def _rebuild_now(generator) -> None:
    from ..generators import apply_generator

    try:
        apply_generator(generator.id_data, generator)
    except Exception as error:
        console.error(f"generator '{generator.name}': {error}")


def _should_defer(generator) -> bool:
    """Defer the rebuild of a heavy generator, so dragging stays responsive.

    A scripted session has no event loop to run the timer, so background use
    (and every test) keeps rebuilding immediately.
    """
    if bpy.app.background:
        return False
    edges = 0
    for output in generator.outputs:
        pattern = global_data.get_obj_by_uuid(output.pattern_uuid, check_uuid=False)
        if pattern is not None:
            edges += len(pattern.edges)
    return edges > HEAVY_EDGE_COUNT


_pending: dict[int, float] = {}


def _defer_rebuild(generator) -> None:
    _pending[generator.global_uuid] = time.monotonic() + REBUILD_DELAY
    if not bpy.app.timers.is_registered(_rebuild_due):
        bpy.app.timers.register(_rebuild_due, first_interval=REBUILD_DELAY)


def _rebuild_due():
    """Timer callback: rebuild the generators whose pause has elapsed."""
    now = time.monotonic()
    due = [uuid for uuid, deadline in _pending.items() if deadline <= now]
    for uuid in due:
        _pending.pop(uuid, None)
        generator = global_data.get_obj_by_uuid(uuid, check_uuid=False)
        if generator is not None:
            _rebuild_now(generator)
    return 0.05 if _pending else None


class GeneratorParam(PropertyGroup):
    """One parameter of a generator, described by the component's schema."""

    key: StringProperty(name="Key")
    label: StringProperty(name="Label")
    description: StringProperty(name="Description")
    kind: StringProperty(name="Kind", default="float")   # float | int | bool | text
    unit: StringProperty(name="Unit")
    # The schema range is enforced when a rebuild reads the values (see
    # Qianyi.panellib.component.clamp_to_schema): Blender can only give an RNA
    # property a fixed range at registration time, and this parameter list is
    # built at runtime, so the range cannot live on the property itself. These
    # two fields carry it for the rebuild and for the UI.
    min_value: FloatProperty(name="Minimum", default=0.0)
    max_value: FloatProperty(name="Maximum", default=1.0)

    value_float: FloatProperty(name="Value", update=_param_changed)
    value_int: IntProperty(name="Value", update=_param_changed)
    value_bool: BoolProperty(name="Value", update=_param_changed)
    value_text: StringProperty(name="Value", update=_param_changed)

    def value(self):
        if self.kind == "bool":
            return bool(self.value_bool)
        if self.kind == "int":
            return int(self.value_int)
        if self.kind == "text":
            return str(self.value_text)
        return float(self.value_float)

    def set_value(self, value) -> None:
        if self.kind == "bool":
            self.value_bool = bool(value)
        elif self.kind == "int":
            self.value_int = int(value)
        elif self.kind == "text":
            self.value_text = str(value)
        else:
            self.value_float = float(value)

    def apply_schema(self, spec: dict) -> None:
        self.kind = str(spec.get("type", "float"))
        self.label = str(spec.get("label", self.key))
        self.description = str(spec.get("description", ""))
        self.unit = str(spec.get("unit", ""))
        if "min" in spec:
            self.min_value = float(spec["min"])
        if "max" in spec:
            self.max_value = float(spec["max"])


class GeneratorOutput(PropertyGroup):
    """One panel a generator produced, addressed by its slot name."""

    slot: StringProperty(name="Slot")
    pattern_uuid: IntProperty(name="Panel", default=-1)


class PatternGenerator(PropertyGroup, ModelData):
    """A component plus a parameter block, owning the panels it produces."""

    component_id: StringProperty(name="Component", default="")
    version: IntProperty(name="Component Version", default=1)
    params: CollectionProperty(type=GeneratorParam, name="Parameters")
    outputs: CollectionProperty(type=GeneratorOutput, name="Panels")

    def values(self) -> dict:
        return {param.key: param.value() for param in self.params}

    def set_values(self, values: dict) -> None:
        known = {param.key: param for param in self.params}
        for key, value in (values or {}).items():
            if key in known:
                known[key].set_value(value)

    def apply_schema(self, schema: dict) -> None:
        """Rebuild the parameter list from a component schema, keeping values."""
        self.suppress_rebuild = True
        try:
            self._apply_schema(schema)
        finally:
            self.suppress_rebuild = False

    def _apply_schema(self, schema: dict) -> None:
        previous = self.values()
        self.params.clear()
        for key, spec in schema.get("params", {}).items():
            param = self.params.add()
            param.key = key
            param.label = str(spec.get("label", key))
            param.apply_schema(spec)
            param.set_value(previous.get(key, spec.get("default")))

    def output_for(self, slot: str):
        for output in self.outputs:
            if output.slot == slot:
                return output
        return None

    def set_output(self, slot: str, pattern_uuid: int):
        output = self.output_for(slot)
        if output is None:
            output = self.outputs.add()
            output.slot = slot
        output.pattern_uuid = pattern_uuid
        return output


def owner_of_param(param) -> PatternGenerator | None:
    """The generator a parameter belongs to, or None."""
    project = param.id_data
    generators = getattr(project, "generators", None)
    if generators is None:
        return None
    target = param.as_pointer()
    for generator in generators:
        for item in generator.params:
            if item.as_pointer() == target:
                return generator
    return None


def generator_of_pattern(project, pattern) -> PatternGenerator | None:
    """The generator that owns a panel, or None for a hand-drawn panel."""
    if project is None or pattern is None:
        return None
    owner_uuid = getattr(pattern, "generator_uuid", -1)
    if owner_uuid != -1:
        for generator in project.generators:
            if generator.global_uuid == owner_uuid:
                return generator
    if pattern.global_uuid == -1:
        return None
    for generator in project.generators:
        for output in generator.outputs:
            if output.pattern_uuid == pattern.global_uuid:
                return generator
    return None


def refresh_generators(project) -> None:
    """Register generators in the in-memory uuid map."""
    for generator in project.generators:
        generator.get_temp_data()
        global_data.uuid2obj[generator.global_uuid] = generator


LOCKED_EDIT_MESSAGE = ("'{name}' is a generated panel: change its parameters in the "
                       "GC Library panel, or detach it first")


def generation_lock(project, pattern) -> str | None:
    """Why a geometry edit of this panel is refused, or None when it is free.

    Sewing, simulation, fabric settings and 2D placement are not affected: only
    the edits a rebuild would overwrite are locked. The whole instance chain is
    examined: the interactive tools keep copies in sync, so editing a free copy
    of a generated panel would reach the generated panel through the chain.
    """
    for member in instance_chain(pattern):
        generator = generator_of_pattern(project, member)
        if generator is not None:
            return LOCKED_EDIT_MESSAGE.format(name=generator.name or generator.component_id)
    return None


def instance_chain(pattern) -> list:
    """A panel plus every copy in its instance list.

    ``instance_next_uuid`` is a circular list, so any member sees all the
    others. A broken or half-built chain simply yields the panel alone.
    """
    if pattern is None:
        return []
    members = [pattern]
    try:
        members.extend(instance for instance in pattern.other_instances()
                       if instance is not None)
    except Exception:
        pass
    return members


def refuse_generated_edit(operator, project, pattern) -> bool:
    """Report and return True when an interactive edit must be refused."""
    reason = generation_lock(project, pattern)
    if reason is None:
        return False
    if operator is not None and hasattr(operator, "report"):
        operator.report({"ERROR"}, reason)
    console.error(reason)
    return True


define_temp_prop(PatternGenerator, "applying", False)
define_temp_prop(PatternGenerator, "suppress_rebuild", False)

register, unregister = register_classes_factory(
    (GeneratorParam, GeneratorOutput, PatternGenerator)
)
