"""Building components: schema defaults, generation, and the stability check."""

from __future__ import annotations

from . import registry
from .spec import ComponentSpec, PatternSpec, SeamSpec, finalize_pattern


def build_component(component_id: str, params: dict | None = None) -> ComponentSpec:
    """Generate one component and finalise its patterns.

    Parameters missing from ``params`` fall back to the component's schema
    defaults, so a generator can grow a parameter without invalidating the
    generators that already exist.
    """
    module = registry.get(component_id)
    merged = registry.default_params(component_id)
    if params:
        merged.update(params)
    merged = clamp_to_schema(component_id, merged)
    raw_patterns = module.build(dict(merged))
    patterns: list[PatternSpec] = [finalize_pattern(pattern) for pattern in raw_patterns]
    if not patterns:
        raise ValueError(f"component '{component_id}' produced no patterns")
    return ComponentSpec(component_id=component_id, params=dict(merged), patterns=patterns,
                         seams=_component_seams(module, dict(merged), patterns))


def _component_seams(module, params: dict, patterns: list[PatternSpec]) -> list[SeamSpec]:
    """The component's declared internal seams, if it has any."""
    factory = getattr(module, "seams", None)
    if factory is None:
        return []
    result = []
    # Deliberate loop: one SeamSpec per declared Python tuple.
    for entry in factory(params, patterns):
        result.append(entry if isinstance(entry, SeamSpec) else SeamSpec(*entry))
    return result


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


def pattern_by_name(spec: ComponentSpec, name: str) -> PatternSpec | None:
    for pattern in spec.patterns:
        if pattern.name == name:
            return pattern
    return None
