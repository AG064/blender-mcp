"""Render the three weapons side by side, at their own scale.

    blender --background --python parts/preview_weapons.py -- <output-dir>

Each is laid out where its mounting point is, with a label-sized gap between
them, so the sheet shows their relative sizes -- which is most of what decides
whether a weapon looks like it belongs on the machine that carries it.
"""

import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import mech_kit  # noqa: E402
import preview  # noqa: E402
import weapons  # noqa: E402


def build_all():
    """Every weapon in the file at once, spaced along X so nothing overlaps."""
    mech_kit.reset()
    mats = weapons.palette()
    made = []
    # Far enough apart that a long barrel and a long blade do not touch.
    for index, (name, offset) in enumerate(
        (("autocannon", -1.5), ("missile_pod", 0.0), ("arc_blade", 1.5))
    ):
        for obj in weapons.BUILDERS[name](mats):
            obj.location.x += offset
            made.append(obj)
    return made


def main():
    out = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else os.path.join(HERE, "..", "previews")
    made = build_all()

    preview.studio(strength=1.2)
    preview.camera_for(made, 32, elevation=0.30, lens=55.0, margin=1.18)
    preview.render(os.path.join(out, "weapons_threequarter.png"), 1180, 720)
    preview.camera_for(made, 0, elevation=0.10, lens=55.0, margin=1.18)
    preview.render(os.path.join(out, "weapons_side.png"), 1180, 720)

    print("AURUM_WEAPONS", mech_kit.stats(*made))


if __name__ == "__main__":
    main()
