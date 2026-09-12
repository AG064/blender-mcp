"""The weapons: the autocannon, the missile pod and the arc blade.

Three machines' worth of hardware that has to read as belonging to the mech it
is bolted to. So they use the reference sheet's palette -- white armour over
olive drab over dark mechanism, with orange at the working parts -- and they
keep its language of chamfered plates over exposed joints.

Built at the mech's own scale in metres, with the mounting point at the origin of
each: a weapon that has to be positioned by eye every time it is attached is a
weapon that ends up crooked. The muzzle or the emitter points down -Y, which is
the mech's forward, so a weapon dropped onto an arm joint points where the arm
points.
"""

import math

import bpy

import mech_kit as kit


def palette():
    """The reference mech's own materials, so a weapon matches its machine."""
    return {
        "white": kit.material("REF_white", (0.780, 0.775, 0.745), metallic=0.25, roughness=0.48),
        "olive": kit.material("REF_olive", (0.245, 0.275, 0.195), metallic=0.35, roughness=0.58),
        "dark": kit.material("REF_dark", (0.085, 0.090, 0.098), metallic=0.65, roughness=0.42),
        "orange": kit.material("REF_orange", (0.880, 0.420, 0.075), metallic=0.15, roughness=0.42),
        "steel": kit.material("REF_steel", (0.480, 0.500, 0.530), metallic=1.0, roughness=0.28),
        "hot": kit.material("REF_hot", (1.0, 0.55, 0.18), metallic=0.0, roughness=0.35,
                            emission=(1.0, 0.55, 0.18), emission_strength=3.0),
        "arc": kit.material("REF_arc", (0.55, 0.85, 1.0), metallic=0.0, roughness=0.10,
                            emission=(0.55, 0.82, 1.0), emission_strength=4.0),
    }


def autocannon(mats):
    """VK-40. A heavy kinetic gun: boxy receiver, long barrel, muzzle brake.

    The proportions are a rifle's rather than a cannon's: a long barrel in front
    of a compact receiver reads as something that throws a round a long way,
    where a short fat tube reads as a mortar.
    """
    parts = []
    # Receiver, with a hardpoint above it where it meets the arm.
    parts.append(kit.slab("ac_receiver", (0.30, 0.92, 0.34), (0.0, -0.20, 0.0),
                          mats["white"], bevel=0.045))
    parts.append(kit.slab("ac_mount", (0.24, 0.34, 0.14), (0.0, 0.06, 0.22),
                          mats["olive"], bevel=0.03))
    parts.append(kit.slab("ac_spine", (0.20, 0.80, 0.10), (0.0, -0.22, 0.19),
                          mats["olive"], bevel=0.025))
    parts.append(kit.slab("ac_ejection", (0.13, 0.26, 0.16), (0.19, -0.05, 0.04),
                          mats["dark"], bevel=0.025))

    # Barrel and its shroud. The shroud is what stops the barrel looking like a
    # stick pushed into a box.
    parts.append(kit.tube("ac_barrel", 0.072, 0.86, (0.0, -1.08, 0.0), mats["steel"],
                          axis="Y", segments=18, bevel=0.014))
    parts.append(kit.tube("ac_shroud", 0.115, 0.50, (0.0, -0.90, 0.0), mats["dark"],
                          axis="Y", segments=18))
    for index in range(4):
        parts.append(kit.tube("ac_rib", 0.125, 0.035, (0.0, -0.72 - index * 0.13, 0.0),
                              mats["white"], axis="Y", segments=18, bevel=0.008))
    parts.append(kit.tube("ac_brake", 0.105, 0.20, (0.0, -1.60, 0.0), mats["dark"],
                          axis="Y", segments=18, bevel=0.02))
    parts.append(kit.slab("ac_brake_port", (0.26, 0.10, 0.10), (0.0, -1.60, 0.0),
                          mats["dark"], bevel=0.02))

    # Ammunition: a drum on the left, with a feed chute up into the receiver.
    parts.append(kit.tube("ac_drum", 0.170, 0.28, (-0.26, -0.06, -0.08), mats["olive"],
                          axis="X", segments=20))
    parts.append(kit.tube("ac_drum_cap", 0.140, 0.06, (-0.41, -0.06, -0.08), mats["orange"],
                          axis="X", segments=20, bevel=0.012))
    parts.append(kit.slab("ac_feed", (0.10, 0.30, 0.13), (-0.20, -0.16, 0.06),
                          mats["dark"], bevel=0.02))

    # Sight rail and a muzzle reference mark, which is what makes the barrel
    # look aimed rather than attached.
    parts.append(kit.slab("ac_rail", (0.09, 0.46, 0.05), (0.0, -0.34, 0.30),
                          mats["dark"], bevel=0.015))
    parts.append(kit.slab("ac_sight", (0.07, 0.09, 0.08), (0.0, -0.52, 0.36),
                          mats["dark"], bevel=0.015))
    return parts


def missile_pod(mats):
    """HR-6. Six tubes in a box, on a hinged hardpoint.

    Angled up and back on its mount, because a launcher that fires over the
    shoulder has to be, and because the angle is what tells the eye it is a
    launcher rather than a crate.
    """
    parts = []
    parts.append(kit.slab("mp_hinge", (0.26, 0.22, 0.22), (0.0, 0.16, 0.0),
                          mats["dark"], bevel=0.035))
    parts.append(kit.tube("mp_pivot", 0.075, 0.34, (0.0, 0.16, 0.0), mats["steel"],
                          axis="X", segments=14))

    tilt = math.radians(-16)
    parts.append(kit.slab("mp_body", (0.44, 0.72, 0.46), (0.0, -0.16, 0.06),
                          mats["white"], bevel=0.05, rotation=(tilt, 0.0, 0.0)))
    parts.append(kit.slab("mp_lid", (0.48, 0.76, 0.08), (0.0, -0.16, 0.30),
                          mats["olive"], bevel=0.03, rotation=(tilt, 0.0, 0.0)))

    # The tube face. Recessed mouths rather than flat circles: a hole you can
    # see into is what says there is something in it.
    for column in (-1, 1):
        for row in (-1, 0, 1):
            x = column * 0.115
            z = row * 0.145
            parts.append(kit.tube("mp_tube", 0.082, 0.10, (x, -0.50, 0.06 + z),
                                  mats["dark"], axis="Y", segments=14))
            parts.append(kit.tube("mp_rim", 0.094, 0.035, (x, -0.54, 0.06 + z),
                                  mats["white"], axis="Y", segments=14, bevel=0.008))
            parts.append(kit.tube("mp_round", 0.062, 0.02, (x, -0.47, 0.06 + z),
                                  mats["orange"], axis="Y", segments=12, bevel=0.006))
    parts.append(kit.slab("mp_warning", (0.40, 0.05, 0.07), (0.0, -0.38, 0.31),
                          mats["orange"], bevel=0.012, rotation=(tilt, 0.0, 0.0)))
    return parts


def arc_blade(mats):
    """KS-9. A forearm housing with two emitter prongs and a blade between them.

    The blade is the brightest thing on the machine and it is deliberately thin:
    an arc is a line, and a thick one reads as a slab of glowing plastic.
    """
    parts = []
    parts.append(kit.slab("ab_housing", (0.26, 0.66, 0.30), (0.0, -0.16, 0.0),
                          mats["white"], bevel=0.04))
    parts.append(kit.slab("ab_mount", (0.22, 0.30, 0.13), (0.0, 0.08, 0.18),
                          mats["olive"], bevel=0.028))
    parts.append(kit.slab("ab_capacitor", (0.30, 0.22, 0.24), (0.0, -0.02, 0.16),
                          mats["olive"], bevel=0.035))
    parts.append(kit.tube("ab_core", 0.045, 0.34, (0.0, -0.05, 0.16), mats["hot"],
                          axis="Y", segments=12, bevel=0.0))

    # Prongs, splayed so the arc has somewhere to strike between them.
    for side in (1, -1):
        parts.append(kit.slab("ab_prong", (0.055, 0.62, 0.075),
                              (0.085 * side, -0.80, 0.10), mats["steel"], bevel=0.018,
                              rotation=(0.0, math.radians(5 * side), 0.0)))
        parts.append(kit.slab("ab_prong_tip", (0.048, 0.16, 0.062),
                              (0.115 * side, -1.14, 0.10), mats["dark"], bevel=0.014,
                              rotation=(0.0, math.radians(9 * side), 0.0)))
    parts.append(kit.slab("ab_blade", (0.022, 0.92, 0.11), (0.0, -0.92, 0.10),
                          mats["arc"], bevel=0.008))
    parts.append(kit.slab("ab_edge", (0.012, 0.74, 0.045), (0.0, -0.86, 0.10),
                          mats["arc"], bevel=0.004))
    return parts


BUILDERS = {
    "autocannon": autocannon,
    "missile_pod": missile_pod,
    "arc_blade": arc_blade,
}


def build(name):
    kit.reset()
    mats = palette()
    parts = BUILDERS[name](mats)
    joined = kit.join(parts, name)
    kit.shade_auto_smooth(joined, 30.0)
    return {"parts": [joined.name], "stats": kit.stats(joined)}
