"""Building components: schema defaults, generation, and the stability check."""

from __future__ import annotations

from . import registry
from .spec import ComponentSpec, PanelSpec, finalize_panel


def build_component(component_id: str, params: dict | None = None) -> ComponentSpec:
    """Generate one component and finalise its panels.

    Parameters missing from ``params`` fall back to the component's schema
    defaults, so a generator can grow a parameter without invalidating the
    generators that already exist.
    """
    module = registry.get(component_id)
    merged = registry.default_params(component_id)
    if params:
        merged.update(params)
    merged = clamp_to_schema(component_id, merged)
    raw_panels = module.build(dict(merged))
    panels: list[PanelSpec] = [finalize_panel(panel) for panel in raw_panels]
    if not panels:
        raise ValueError(f"component '{component_id}' produced no panels")
    return ComponentSpec(component_id=component_id, params=dict(merged), panels=panels)


def clamp_to_schema(component_id: str, values: dict) -> dict:
    """Force numeric parameters into the range their schema declares.

    Blender can only give an RNA property a range at registration time, and a
    generator builds its parameter list at runtime, so the range is enforced
    here instead - for every caller, inside Blender or outside it. A value
    outside the range is pulled back to the nearest bound, which is what the
    slider would have allowed in the first place.
    """
    module = registry.get(component_id)
    specs = getattr(module, "SCHEMA", {}).get("params", {})
    clamped = dict(values)
    for key, spec in specs.items():
        if key not in clamped:
            continue
        value = clamped[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        low, high = spec.get("min"), spec.get("max")
        if low is not None:
            value = max(value, low)
        if high is not None:
            value = min(value, high)
        clamped[key] = value
    return clamped


def panel_by_name(spec: ComponentSpec, name: str) -> PanelSpec | None:
    for panel in spec.panels:
        if panel.name == name:
            return panel
    return None
