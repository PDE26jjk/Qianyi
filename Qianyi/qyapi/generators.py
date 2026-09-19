"""Parametric panels: a component plus a parameter block, owned by the project."""

from __future__ import annotations

import numpy as np

from . import _address as address
from . import patterns
from .errors import QyapiError
from .. import generators as generator_model


def list(project=None):  # noqa: A001 - the surface's name for this call
    """Every generator of the project, with its parameters and panels."""
    project = address.project_or_refuse(project)
    entries = [_entry(project, generator)
               for generator in project.generators]  # loop: one dict per generator
    return address.jsonify({"project": project.name, "generators": entries})


def get(name, project=None):
    """One generator, with its parameter table and the panels it owns."""
    project = address.project_or_refuse(project)
    generator = _generator_or_refuse(project, name)
    entry = _entry(project, generator)
    entry["panels"] = [patterns._summary(pattern, None)
                       for pattern in generator_model.panels_of(project, generator)]
    return address.jsonify(entry)


def create(component_id, params=None, name=None, project=None):
    """Add a generator for a component and build its panels."""
    from . import components

    project = address.project_or_refuse(project)
    from ..panellib import registry

    components._ensure_registered()
    info = components._info_or_refuse(component_id)
    values = components._known_params(info, params)
    try:
        generator = generator_model.create_generator(project, component_id, values)
    except Exception as error:
        raise QyapiError(f"generator for {component_id!r} could not be built: {error}",
                         ("its parameters may not describe a panel",)) from error
    if name is not None:
        generator.name = str(name)
    address.write_done(f"add generator {generator.name} ({component_id})")
    entry = _entry(project, generator)
    entry["panels"] = [patterns._summary(pattern, None)
                       for pattern in generator_model.panels_of(project, generator)]
    return address.jsonify(entry)


def set_params(name, params, project=None):
    """Set several parameters and rebuild once, reporting what the rebuild did."""
    project = address.project_or_refuse(project)
    generator = _generator_or_refuse(project, name)
    values = dict(params or {})
    if not values:
        raise QyapiError("no parameters were given")
    known = {param.key for param in generator.params}
    unknown = sorted(set(values) - known)
    if unknown:
        raise QyapiError(f"generator {generator.name!r} has no parameter "
                         f"{', '.join(unknown)}",
                         (f"parameters: {', '.join(sorted(known))}",))
    panels = generator_model.panels_of(project, generator)
    before = _simulation_state(panels)
    generator.suppress_rebuild = True
    try:
        generator.set_values(values)
    finally:
        generator.suppress_rebuild = False
    report = generator_model.apply_generator(project, generator)
    if report.get("error"):
        raise QyapiError(f"the rebuild failed: {report['error']}",
                         ("the panels were left as they were",))
    report = _named_report(project, generator, report)
    address.write_done(f"set parameters of {generator.name}")
    panels = generator_model.panels_of(project, generator)
    entry = _entry(project, generator)
    entry["report"] = report
    entry["panels"] = [patterns._summary(pattern, None)
                       for pattern in generator_model.panels_of(project, generator)]
    entry["simulation_before"] = before
    entry["simulation_carried"] = before == "simulated" and _simulation_state(panels) == "simulated"
    return address.jsonify(entry)


def rebuild(name, project=None):
    """Rebuild a generator with the parameters it already has."""
    project = address.project_or_refuse(project)
    generator = _generator_or_refuse(project, name)
    panels = generator_model.panels_of(project, generator)
    before = _simulation_state(panels)
    report = generator_model.apply_generator(project, generator)
    if report.get("error"):
        raise QyapiError(f"the rebuild failed: {report['error']}")
    report = _named_report(project, generator, report)
    address.write_done(f"rebuild {generator.name}")
    panels = generator_model.panels_of(project, generator)
    entry = _entry(project, generator)
    entry["report"] = report
    entry["panels"] = [patterns._summary(pattern, None)
                       for pattern in generator_model.panels_of(project, generator)]
    entry["simulation_before"] = before
    entry["simulation_carried"] = before == "simulated" and _simulation_state(panels) == "simulated"
    return address.jsonify(entry)


def detach(name, project=None):
    """Turn a generator's panels into ordinary panels and drop the generator."""
    project = address.project_or_refuse(project)
    generator = _generator_or_refuse(project, name)
    generator_name = generator.name
    panels = [pattern.name for pattern in
              generator_model.panels_of(project, generator)]
    generator_model.detach_generator(project, generator)
    address.write_done(f"detach {generator_name}")
    return address.jsonify({"generator": generator_name, "detached": panels,
                            "generators_left": len(project.generators)})


def remove(name, project=None):
    """Remove a generator together with the panels it owns."""
    project = address.project_or_refuse(project)
    generator = _generator_or_refuse(project, name)
    generator_name = generator.name
    panels = [pattern.name for pattern in
              generator_model.panels_of(project, generator)]
    sewings_before = len(project.sewings)
    generator_model.delete_group(project, generator)
    address.write_done(f"remove {generator_name}")
    return address.jsonify({"generator": generator_name, "removed": panels,
                            "dropped_sewings": sewings_before - len(project.sewings),
                            "generators_left": len(project.generators)})


# --- internals -------------------------------------------------------------

def _generator_or_refuse(project, name):
    for generator in project.generators:  # loop: one name comparison per generator
        if generator.name == name:
            return generator
    names = ", ".join(generator.name for generator in project.generators)
    raise QyapiError(f"no generator named {name!r}",
                     (f"generators: {names or '(none)'}",
                      "qyapi.generators.list() has the same names"))


def _entry(project, generator):
    panels = generator_model.panels_of(project, generator)
    by_uuid = {pattern.global_uuid: pattern.name for pattern in panels}
    return {
        "name": generator.name,
        "component": generator.component_id,
        "version": int(generator.version),
        "parameters": {param.key: param.value() for param in generator.params},
        "parameter_table": [{
            "key": param.key, "label": param.label, "unit": param.unit,
            "kind": param.kind, "min": float(param.min_value),
            "max": float(param.max_value), "value": param.value(),
        } for param in generator.params],
        "slots": [{"slot": output.slot, "panel": by_uuid.get(output.pattern_uuid)}
                  for output in generator.outputs],
    }


def _simulation_state(panels):
    """Whether any of these panels carries simulated positions.

    Compared with a micron of slack, not bit for bit: a panel that never ran
    still has the two keys written through different paths, so an exact
    comparison calls a fresh panel simulated.
    """
    for pattern in panels:  # loop: one shape-key comparison per panel
        obj = pattern.mesh_object
        if obj is None:
            continue
        props = obj.qmyi_simulation_props
        simulated = props.get_simulation_vertices()
        rest = props.get_shape_key_vertices(props.base_key_name)
        if simulated is None or rest is None:
            continue
        if not np.allclose(simulated, rest, rtol=0.0, atol=1e-6):
            return "simulated"
    return "untouched"


def _named_report(project, generator, report):
    """Add the panel names behind the rebuild's counts.

    The rebuild writes what the parameters describe and lets the mesh stage keep
    the previous mesh when an outline crosses or is degenerate; that is its own
    policy and it is not gated by the per-call crossing flag. Naming the panels
    is what a caller needs to fix them.
    """
    invalid, degenerate = [], []
    for pattern in generator_model.panels_of(project, generator):  # loop: one panel each
        if str(pattern.validity_state).lower() == "invalid":
            invalid.append(pattern.name)
        elif generator_model._too_close_vertices(pattern) is not None:
            degenerate.append(pattern.name)
    report["invalid_panel_names"] = invalid
    report["degenerate_panel_names"] = degenerate
    report["stale_meshes"] = sorted(set(invalid) | set(degenerate))
    return report
