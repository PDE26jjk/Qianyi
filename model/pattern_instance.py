import numpy as np
import bpy


def collect_unique_instances(pattern_set):
    for p in pattern_set:
        p.impacted = True
    for p in pattern_set:
        p.calc_inv_matrix()
        p.calc_matrix()
        if not p.impacted:
            break
        other_instances = p.other_instances()
        for ins in other_instances:
            ins.impacted = False
        other_instances.append(p)
        p.instances = other_instances
    return {p for p in pattern_set if p.impacted}
