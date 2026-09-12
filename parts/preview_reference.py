"""Render the reference mech from four angles, the way the concept sheet does.

    blender --background --python parts/preview_reference.py -- <output-dir>

Same framing as the sheet it came from: front, three-quarter, back and side, on
a plain backdrop, so the two can be compared side by side rather than from
memory.
"""

import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import preview  # noqa: E402
import reference_mech  # noqa: E402


def main():
    out = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else os.path.join(HERE, "..", "previews")
    built = reference_mech.build()
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]

    preview.studio(strength=1.25)
    # 0 is the front of a model built facing -Y, so the four are front,
    # three-quarter, back and side -- the sheet's own order.
    for label, angle in (("front", 0), ("threequarter", 40), ("back", 180), ("side", 90)):
        preview.camera_for(meshes, angle, elevation=0.05, lens=50.0, margin=1.12)
        preview.render(os.path.join(out, f"reference_{label}.png"), 760, 1040)

    print("AURUM_REFERENCE", built["stats"], built["nodes"])


if __name__ == "__main__":
    main()
