"""The ASHFRAME — the mech the player pilots.

Six metres, humanoid, industrial. Built the way a machine is: a spine that
carries the load, a chest that is the thickest mass because the cockpit and the
reactor are in it, shoulders that stand off on visible joints because arms which
reach past the body need the clearance, and legs wider at the hip than at the
ankle because that is where the weight is.

Everything is in metres with the feet at the origin and the machine facing -Y,
which becomes +Z in Godot. See `mech_kit` for why.
"""

import math

import bpy

import mech_kit as kit

# Proportions, in one place so a change of stance is a change of one number.
HIP_Y = 3.05          # centre of the hip joints
HIP_X = 0.82          # half the stance width
KNEE_Y = 1.95
ANKLE_Y = 0.44
CHEST_LOW = 3.88
CHEST_HIGH = 5.26
SHOULDER_Y = 5.02
SHOULDER_X = 1.16
HEAD_Y = 5.42
HEIGHT = 6.05


def palette():
    return {
        "shell": kit.material("ASH_shell", (0.46, 0.49, 0.54), metallic=0.85, roughness=0.38),
        "plate": kit.material("ASH_plate", (0.30, 0.33, 0.38), metallic=0.9, roughness=0.30),
        "trim": kit.material("ASH_trim", (0.84, 0.52, 0.16), metallic=0.7, roughness=0.35),
        "dark": kit.material("ASH_dark", (0.10, 0.11, 0.13), metallic=0.6, roughness=0.62),
        "glass": kit.material("ASH_glass", (0.30, 0.72, 0.86), metallic=0.0, roughness=0.12,
                              emission=(0.35, 0.85, 1.0), emission_strength=3.0),
        "steel": kit.material("ASH_steel", (0.62, 0.65, 0.70), metallic=1.0, roughness=0.22),
        "hot": kit.material("ASH_hot", (1.0, 0.45, 0.12), metallic=0.0, roughness=0.4,
                            emission=(1.0, 0.45, 0.12), emission_strength=2.5),
    }


def _panel_cuts(mats, y, inset):
    """Recessed panel lines across a face.

    Cut rather than drawn: a groove catches a shadow and a highlight at once,
    and it survives being seen from an angle, which a texture does not.
    """
    cutters = []
    for index, z in enumerate((4.18, 4.62, 5.02)):
        cutters.append(
            kit.slab(f"cut_panel_{index}", (2.2, inset, 0.045), (0.0, y, z), None, bevel=0.0)
        )
    return cutters


def _vent(mats, x, y, z, width, height, count=4):
    cutters = []
    for index in range(count):
        offset = (index - (count - 1) / 2.0) * (height * 1.6)
        cutters.append(
            kit.slab(f"cut_vent", (width, 0.5, height), (x, y, z + offset), None, bevel=0.0)
        )
    return cutters


def build_leg(mats, side):
    """One leg. `side` is +1 or -1 and only ever appears in an X coordinate."""
    x = HIP_X * side
    parts = []

    # Foot. Wider at the toe than the heel, because a machine that walks puts
    # its weight forward.
    parts.append(kit.slab("foot", (1.02, 1.30, 0.26), (x, -0.16, 0.15), mats["dark"], bevel=0.05))
    parts.append(kit.slab("toe", (0.86, 0.42, 0.20), (x, -0.78, 0.13), mats["plate"], bevel=0.04))
    parts.append(kit.slab("heel", (0.70, 0.36, 0.30), (x, 0.50, 0.17), mats["plate"], bevel=0.04))

    # Ankle: a visible joint, not a gap.
    parts.append(kit.tube("ankle", 0.21, 0.62, (x, 0.02, ANKLE_Y), mats["steel"], axis="X", segments=14))

    # Shin, tapering up. Two segments so the taper has a break in it.
    parts.append(kit.slab("shin_low", (0.60, 0.70, 0.62), (x, -0.04, 0.86), mats["shell"], bevel=0.05))
    parts.append(kit.slab("shin_high", (0.68, 0.78, 0.62), (x, -0.02, 1.50), mats["shell"], bevel=0.05))
    parts.append(kit.slab("shin_plate", (0.50, 0.14, 0.95), (x, -0.42, 1.20), mats["plate"], bevel=0.03))

    # Knee: guard in front, joint behind it.
    parts.append(kit.tube("knee", 0.26, 0.72, (x, 0.0, KNEE_Y), mats["steel"], axis="X", segments=16))
    parts.append(kit.slab("knee_guard", (0.72, 0.44, 0.52), (x, -0.40, KNEE_Y + 0.06), mats["trim"], bevel=0.06))

    # Thigh, thickest where the load is.
    parts.append(kit.slab("thigh", (0.80, 0.92, 1.05), (x, -0.02, 2.50), mats["shell"], bevel=0.06))
    parts.append(kit.slab("thigh_outer", (0.22, 0.70, 0.80), (x + 0.44 * side, 0.0, 2.52), mats["plate"], bevel=0.04))
    parts.append(kit.slab("thigh_inner", (0.18, 0.62, 0.62), (x - 0.42 * side, 0.0, 2.34), mats["dark"], bevel=0.03))

    # Hip: a big ball joint where the leg meets the pelvis.
    parts.append(kit.tube("hip", 0.30, 0.66, (x, 0.0, HIP_Y), mats["steel"], axis="X", segments=18))
    parts.append(kit.slab("hip_cap", (0.26, 0.62, 0.62), (x + 0.42 * side, 0.0, HIP_Y), mats["trim"], bevel=0.05))

    return parts


def build_leg_cuts(mats, side):
    x = HIP_X * side
    return _vent(mats, x, -0.45, 1.20, 0.34, 0.035, 4) + _vent(mats, x, -0.30, 2.50, 0.40, 0.04, 3)


def build_torso(mats):
    parts = []

    # Pelvis: a wide, shallow block. It is the thing the legs hang from.
    parts.append(kit.slab("pelvis", (1.86, 1.16, 0.52), (0.0, 0.0, 3.30), mats["plate"], bevel=0.07))
    parts.append(kit.slab("pelvis_front", (1.30, 0.30, 0.44), (0.0, -0.62, 3.26), mats["shell"], bevel=0.05))
    parts.append(kit.slab("pelvis_back", (1.10, 0.26, 0.40), (0.0, 0.62, 3.28), mats["dark"], bevel=0.04))

    # Waist: narrow, because it has to turn.
    parts.append(kit.tube("waist_ring", 0.52, 0.22, (0.0, 0.0, 3.66), mats["steel"], axis="Z", segments=20))
    parts.append(kit.slab("waist_block", (0.92, 0.78, 0.30), (0.0, 0.0, 3.72), mats["dark"], bevel=0.04))

    # Chest: the cockpit and the reactor, so the thickest mass on the machine
    # and set forward of the spine rather than centred on it.
    chest_height = CHEST_HIGH - CHEST_LOW
    chest_centre = (CHEST_LOW + CHEST_HIGH) / 2.0
    parts.append(kit.slab("chest", (1.98, 1.42, chest_height), (0.0, -0.08, chest_centre),
                          mats["shell"], bevel=0.09))
    parts.append(kit.slab("spine", (0.86, 0.52, chest_height * 0.92), (0.0, 0.72, chest_centre),
                          mats["dark"], bevel=0.05))
    parts.append(kit.slab("chest_top", (1.52, 1.20, 0.24), (0.0, -0.04, CHEST_HIGH + 0.06),
                          mats["plate"], bevel=0.05))

    # Cockpit: a window band across the front, with the plate below it.
    parts.append(kit.slab("cockpit", (0.94, 0.10, 0.30), (0.0, -0.80, 4.86), mats["glass"], bevel=0.02))
    parts.append(kit.slab("breastplate", (1.74, 0.14, 0.72), (0.0, -0.78, 4.26), mats["shell"], bevel=0.04))
    parts.append(kit.slab("chest_rail", (1.80, 0.10, 0.09), (0.0, -0.83, 4.62), mats["trim"], bevel=0.02))

    # Backpack and the two main thrusters.
    parts.append(kit.slab("backpack", (1.34, 0.58, 1.06), (0.0, 1.02, 4.56), mats["shell"], bevel=0.06))
    for side in (1, -1):
        parts.append(kit.tube("thruster", 0.24, 0.70, (0.48 * side, 1.36, 4.28), mats["dark"],
                              axis="Y", segments=16))
        parts.append(kit.tube("thruster_lip", 0.28, 0.12, (0.48 * side, 1.68, 4.28), mats["hot"],
                              axis="Y", segments=16, bevel=0.01))

    return parts


def build_torso_cuts(mats):
    return _panel_cuts(mats, -0.80, 0.16) + _vent(mats, 0.0, 1.32, 4.60, 0.70, 0.05, 3)


def build_arm(mats, side, gun):
    """One arm. The right carries the autocannon, the left the arc blade."""
    x = SHOULDER_X * side
    parts = []

    # Shoulder joint, standing off the chest on a visible pivot.
    parts.append(kit.tube("shoulder", 0.30, 0.44, (x, 0.0, SHOULDER_Y), mats["steel"],
                          axis="X", segments=18))
    parts.append(kit.slab("shoulder_mount", (0.34, 0.66, 0.66), (x - 0.34 * side, 0.0, SHOULDER_Y),
                          mats["dark"], bevel=0.04))

    # Pauldron: the biggest single plate on the machine, angled so the
    # silhouette is not a rectangle on a rectangle.
    pauldron = kit.slab("pauldron", (0.62, 1.18, 0.96), (x + 0.44 * side, -0.02, SHOULDER_Y + 0.16),
                        mats["shell"], bevel=0.10, rotation=(0.0, math.radians(-14 * side), 0.0))
    parts.append(pauldron)
    parts.append(kit.slab("pauldron_edge", (0.66, 1.22, 0.14), (x + 0.44 * side, -0.02, SHOULDER_Y + 0.60),
                          mats["trim"], bevel=0.03, rotation=(0.0, math.radians(-14 * side), 0.0)))

    # Upper arm.
    parts.append(kit.slab("upper_arm", (0.46, 0.52, 0.84), (x + 0.16 * side, 0.0, 4.42),
                          mats["plate"], bevel=0.05))
    parts.append(kit.tube("elbow", 0.20, 0.50, (x + 0.16 * side, 0.0, 3.96), mats["steel"],
                          axis="X", segments=14))

    if gun:
        # Forearm as a gun housing, then the barrel forward.
        parts.append(kit.slab("gun_housing", (0.56, 1.30, 0.62), (x + 0.16 * side, -0.34, 3.58),
                              mats["shell"], bevel=0.05))
        parts.append(kit.slab("gun_feed", (0.34, 0.44, 0.50), (x + 0.16 * side, 0.34, 3.66),
                              mats["dark"], bevel=0.03))
        parts.append(kit.tube("barrel", 0.115, 1.62, (x + 0.16 * side, -1.72, 3.58), mats["steel"],
                              axis="Y", segments=16, bevel=0.02))
        parts.append(kit.tube("barrel_shroud", 0.17, 0.66, (x + 0.16 * side, -1.28, 3.58),
                              mats["dark"], axis="Y", segments=16))
        parts.append(kit.tube("muzzle", 0.155, 0.22, (x + 0.16 * side, -2.58, 3.58), mats["trim"],
                              axis="Y", segments=16, bevel=0.02))
    else:
        # Forearm, then the blade emitter and the blade itself.
        parts.append(kit.slab("forearm", (0.50, 0.62, 0.86), (x + 0.16 * side, -0.10, 3.52),
                              mats["plate"], bevel=0.05))
        parts.append(kit.slab("blade_mount", (0.42, 0.72, 0.34), (x + 0.16 * side, -0.44, 3.18),
                              mats["dark"], bevel=0.03))
        parts.append(kit.slab("blade", (0.10, 1.84, 0.30), (x + 0.16 * side, -1.62, 3.18),
                              mats["glass"], bevel=0.03))
        parts.append(kit.slab("blade_spine", (0.16, 1.10, 0.16), (x + 0.16 * side, -1.30, 3.30),
                              mats["steel"], bevel=0.02))

    return parts


def build_head(mats):
    parts = []
    parts.append(kit.tube("neck", 0.19, 0.26, (0.0, 0.02, HEAD_Y - 0.14), mats["dark"],
                          axis="Z", segments=14))
    parts.append(kit.slab("skull", (0.74, 0.86, 0.48), (0.0, 0.04, HEAD_Y + 0.20),
                          mats["shell"], bevel=0.07))
    parts.append(kit.slab("visor", (0.60, 0.14, 0.17), (0.0, -0.40, HEAD_Y + 0.24),
                          mats["glass"], bevel=0.02))
    parts.append(kit.slab("crest", (0.22, 0.66, 0.12), (0.0, 0.06, HEAD_Y + 0.48),
                          mats["trim"], bevel=0.02))
    parts.append(kit.tube("antenna", 0.025, 0.44, (0.22, 0.24, HEAD_Y + 0.62), mats["steel"],
                          axis="Z", segments=8, bevel=0.0))
    return parts


def build():
    """Build the whole machine and return what was made."""
    kit.reset()
    mats = palette()

    parts = []
    for side in (1, -1):
        leg = build_leg(mats, side)
        # Cut the vents before joining, so each leg is a solid shell with
        # recesses rather than a shell with a hole in the wrong place.
        kit.cut(leg[2], build_leg_cuts(mats, side))
        parts += leg
        parts += build_arm(mats, side, gun=(side > 0))

    torso = build_torso(mats)
    kit.cut(torso[0], build_torso_cuts(mats))
    parts += torso
    parts += build_head(mats)

    # Join by material so the model is a handful of draw calls rather than
    # seventy, and shade it so the bevels read and the plates stay crisp.
    by_material = {}
    for obj in parts:
        if not obj.data.materials:
            continue
        key = obj.data.materials[0].name
        by_material.setdefault(key, []).append(obj)

    merged = [kit.join(group, f"ASH_{key}") for key, group in by_material.items()]
    for obj in merged:
        kit.shade_auto_smooth(obj, 32.0)

    return {
        "parts": [o.name for o in merged],
        "stats": kit.stats(*merged),
    }
