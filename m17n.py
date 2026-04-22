# This file references mmd_tools.

import bpy
from utilities.console import console
PACKAGE_NAME = __package__
# Tuple of tuples:
# ((msgctxt, msgid), (sources, gen_comments), (lang, translation, (is_fuzzy, comments)), ...)
translations_tuple = (
    (
        ("*", "enable free simulation"),
        (("bpy.types.Scene.qmyi.simulation_data.enable_free_simulation",), ()),
        ("zh_HANS", "自由模拟", (False, ())),
    ),
    # TODO make a script to generate it.
)

translations_dict = {}
for msg in translations_tuple:
    key = msg[0]
    for lang, trans, (is_fuzzy, comments) in msg[2:]:
        if trans and not is_fuzzy:
            translations_dict.setdefault(lang, {})[key] = trans


def register():
    # console.info("m17n register", __package__)
    bpy.app.translations.register(PACKAGE_NAME, translations_dict)

def unregister():
    # console.info("m17n unregister")
    bpy.app.translations.unregister(PACKAGE_NAME)
