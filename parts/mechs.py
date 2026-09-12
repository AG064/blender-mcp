"""Every mech in the game, from one builder.

Four machines that have to read as four different things at a glance, and the
thing that makes them different is proportion rather than decoration: a
skirmisher is light because it is narrow and long-legged, an artillery unit is
heavy because it is wide and low, and the Patriarch is a different class of
object because it is two of the player's mechs stacked.

So the builder takes a specification and the specifications are the design. The
alternative — four separate builders — is four times the code and four chances
for the machines to drift into looking like each other.

Conventions are in `mech_kit`: metres, Z up, feet at the origin, facing -Y.
"""

import math

import bpy
import mathutils

import mech_kit as kit


class Spec:
    """The proportions and fittings of one machine."""

    def __init__(self, name, palette, height, **kw):
        self.name = name
        self.materials = palette
        self.height = height
        # Fractions of the height, so a machine can be scaled as a whole and
        # still stand correctly.
        self.hip = kw.get("hip", 0.50) * height
        self.knee = kw.get("knee", 0.32) * height
        self.ankle = kw.get("ankle", 0.07) * height
        self.stance = kw.get("stance", 0.135) * height
        self.chest_low = kw.get("chest_low", 0.60) * height
        self.chest_high = kw.get("chest_high", 0.86) * height
        self.shoulder = kw.get("shoulder", 0.82) * height
        self.shoulder_out = kw.get("shoulder_out", 0.19) * height
        self.head = kw.get("head", 0.89) * height
        self.chest = kw.get("chest", (0.30, 0.22, 0.26))
        self.pauldron = kw.get("pauldron", (0.10, 0.19, 0.15))
        self.bulk = kw.get("bulk", 1.0)
        self.arm = kw.get("arm", "gun")            # gun | blade | both | none
        self.back = kw.get("back", "thrusters")    # thrusters | mortar | cannon | none
        self.visor = kw.get("visor", True)
        self.skirts = kw.get("skirts", True)
        self.greebles = kw.get("greebles", 1.0)


def palette(prefix, shell, trim, glass, **kw):
    return {
        "shell": kit.material(f"{prefix}_shell", shell, metallic=0.85, roughness=0.38),
        "plate": kit.material(f"{prefix}_plate", tuple(c * 0.62 for c in shell),
                              metallic=0.9, roughness=0.28),
        "trim": kit.material(f"{prefix}_trim", trim, metallic=0.7, roughness=0.35),
        "dark": kit.material(f"{prefix}_dark", (0.09, 0.10, 0.12), metallic=0.6, roughness=0.62),
        "glass": kit.material(f"{prefix}_glass", glass, metallic=0.0, roughness=0.12,
                              emission=glass, emission_strength=kw.get("glow", 3.0)),
        "steel": kit.material(f"{prefix}_steel", (0.66, 0.69, 0.74), metallic=1.0, roughness=0.20),
        "hot": kit.material(f"{prefix}_hot", (1.0, 0.45, 0.12), metallic=0.0, roughness=0.4,
                            emission=(1.0, 0.45, 0.12), emission_strength=2.5),
    }


ASHFRAME = dict(
    palette=((0.46, 0.49, 0.54), (0.84, 0.52, 0.16), (0.30, 0.72, 0.86)),
    height=6.0, hip=0.53, knee=0.34, stance=0.135,
    chest=(0.285, 0.235, 0.265), pauldron=(0.105, 0.175, 0.135),
    arm="both", back="thrusters",
)

SKIRMISHER = dict(
    palette=((0.40, 0.45, 0.51), (0.24, 0.66, 0.80), (0.40, 0.85, 0.95)),
    height=4.6, hip=0.56, knee=0.36, stance=0.125,
    chest=(0.24, 0.20, 0.26), pauldron=(0.075, 0.125, 0.10),
    bulk=0.86, arm="gun", back="thrusters", greebles=0.7,
)

ARTILLERY = dict(
    palette=((0.50, 0.44, 0.34), (0.80, 0.45, 0.15), (0.90, 0.60, 0.20)),
    height=5.4, hip=0.44, knee=0.26, stance=0.185,
    chest=(0.36, 0.30, 0.24), pauldron=(0.09, 0.15, 0.13),
    bulk=1.25, arm="none", back="mortar", skirts=False, greebles=1.2,
)

PATRIARCH = dict(
    palette=((0.20, 0.20, 0.24), (0.78, 0.14, 0.16), (1.0, 0.30, 0.25)),
    height=11.5, hip=0.50, knee=0.31, stance=0.145,
    chest=(0.30, 0.26, 0.30), pauldron=(0.115, 0.21, 0.19),
    bulk=1.5, arm="gun", back="cannon", glow=4.0, greebles=1.6,
)


# Which articulated node each named part hangs from. The builders do not have to
# know: they name what they make, and this decides where it goes. Keeping the
# mapping here rather than threading a node argument through forty call sites is
# the difference between a rig and a rewrite.
_NODE_RULES = (
    ("foot", "foot"), ("toe", "foot"), ("heel", "foot"),
    ("ankle", "knee"), ("shin", "knee"),
    ("knee", "leg"), ("thigh", "leg"), ("hip", "leg"),
    ("blade", "blade"), ("forearm", "blade"),
    ("gun", "gun"), ("barrel", "gun"), ("muzzle", "gun"),
    ("pauldron", "arm"), ("shoulder", "arm"), ("upper_arm", "arm"), ("elbow", "arm"),
    ("neck", "head"), ("skull", "head"), ("visor", "head"),
    ("crest", "head"), ("antenna", "head"),
)


def _node_for(part_name, tag):
    for prefix, node in _NODE_RULES:
        if part_name.startswith(prefix):
            return f"{node}_{tag}" if tag else node
    return "torso"


def _pivots(spec):
    """Where each joint sits, and what it hangs from."""
    return {
        "torso": ((0.0, 0.0, spec.hip), None),
        "head": ((0.0, 0.0, spec.head), "torso"),
        "leg_l": ((spec.stance, 0.0, spec.hip), None),
        "leg_r": ((-spec.stance, 0.0, spec.hip), None),
        "knee_l": ((spec.stance, 0.0, spec.knee), "leg_l"),
        "knee_r": ((-spec.stance, 0.0, spec.knee), "leg_r"),
        "foot_l": ((spec.stance, 0.0, spec.ankle), "knee_l"),
        "foot_r": ((-spec.stance, 0.0, spec.ankle), "knee_r"),
        "arm_l": ((spec.shoulder_out, 0.0, spec.shoulder), "torso"),
        "arm_r": ((-spec.shoulder_out, 0.0, spec.shoulder), "torso"),
        "gun_l": ((spec.shoulder_out + spec.height * 0.030, 0.0,
                   spec.shoulder - spec.height * 0.14 * 1.70), "arm_l"),
        "gun_r": ((-spec.shoulder_out - spec.height * 0.030, 0.0,
                   spec.shoulder - spec.height * 0.14 * 1.70), "arm_r"),
        "blade_l": ((spec.shoulder_out + spec.height * 0.030, 0.0,
                     spec.shoulder - spec.height * 0.14 * 1.70), "arm_l"),
        "blade_r": ((-spec.shoulder_out - spec.height * 0.030, 0.0,
                     spec.shoulder - spec.height * 0.14 * 1.70), "arm_r"),
    }


def build_spec(spec):
    """Build one machine from its specification, as a rig rather than a lump.

    The caller is responsible for having emptied the file first, and for
    creating the palette *after* that. Doing it here would be tidier and wrong:
    the reset deletes every unused material, so a palette built before it is
    deleted along with everything else, and the failure surfaces later as a
    dangling reference from a datablock that no longer exists.

    Parts are grouped two ways: by the articulated node they swing from, so the
    machine can walk and turn, and by material within that, so it draws in a
    handful of calls rather than seventy. A single joined mesh would animate as
    one rigid object and a part per material would lose the hierarchy, and a
    mech needs both.
    """
    mats = spec.materials
    grouped = {}

    def collect(tag, *builders):
        for builder in builders:
            before = set(bpy.data.objects)
            builder()
            for obj in bpy.data.objects:
                if obj in before or obj.type != "MESH":
                    continue
                grouped.setdefault(_node_for(obj.name, tag), []).append(obj)

    for side, tag in ((1, "l"), (-1, "r")):
        collect(tag,
                lambda s=side: _leg(spec, mats, s),
                lambda s=side: _arm(spec, mats, s),
                lambda s=side: _limb_detail(spec, mats, s),
                lambda s=side: _arm_detail(spec, mats, s))
    collect("", lambda: _torso(spec, mats))
    collect("", lambda: _torso_detail(spec, mats))
    collect("", lambda: _back(spec, mats))
    if spec.visor:
        collect("", lambda: _head(spec, mats))

    pivots = _pivots(spec)
    nodes = {}
    # The world position of each joint, kept separately from the object's own
    # `location`. Once a joint is parented its `location` becomes an offset from
    # its parent, and reading it back to place a part would place that part
    # relative to the wrong frame -- which is exactly what happened the first
    # time, and it showed up as a mech standing a metre and a half in the air.
    world = {}
    for name, (position, _parent) in pivots.items():
        empty = bpy.data.objects.new(f"{spec.name}_{name}", None)
        empty.empty_display_size = spec.height * 0.04
        bpy.context.scene.collection.objects.link(empty)
        empty.location = position
        nodes[name] = empty
        world[name] = mathutils.Vector(position)

    # Parents after children exist, so a joint can be moved without moving the
    # parts that hang off it.
    for name, (_position, parent) in pivots.items():
        if parent is None:
            continue
        nodes[name].parent = nodes[parent]
        nodes[name].location = world[name] - world[parent]

    merged = []
    for node_name, objects in grouped.items():
        if node_name not in nodes:
            continue
        by_material = {}
        for obj in objects:
            if not obj.data.materials:
                continue
            by_material.setdefault(obj.data.materials[0].name, []).append(obj)
        for key, group in by_material.items():
            joined = kit.join(group, f"{spec.name}_{node_name}_{key.rsplit('_', 1)[-1]}")
            # Re-parent with the world position kept, by moving the origin into
            # the joint's frame. Doing it by arithmetic rather than by a parent
            # inverse is what makes the exported glTF carry the right local
            # transforms: glTF has no concept of a parent inverse.
            joined.parent = nodes[node_name]
            # Relative to the joint it hangs from, which is what the exporter
            # writes as the node's local transform. The joints themselves were
            # already given their offsets from their own parents above, so the
            # chain adds up without anything being subtracted twice.
            joined.location = joined.location - world[node_name]
            kit.shade_auto_smooth(joined, 32.0)
            merged.append(joined)

    return {
        "parts": [o.name for o in merged],
        "nodes": [n for n in pivots if any(o.parent is nodes[n] for o in merged)],
        "stats": kit.stats(*merged),
    }





def _bulk(spec, value):
    return value * spec.bulk


# ── legs ─────────────────────────────────────────────────────────────────────


def _leg(spec, mats, side):
    x = spec.stance * side
    b = spec.bulk
    leg_w = _bulk(spec, spec.height * 0.085)
    parts = []

    # Foot: broad, and longer at the toe than the heel because a machine that
    # walks carries its weight forward.
    foot_l = _bulk(spec, spec.height * 0.20)
    parts.append(kit.slab("foot", (leg_w * 1.5, foot_l, spec.height * 0.042),
                          (x, -foot_l * 0.12, spec.height * 0.024), mats["dark"], bevel=0.05))
    parts.append(kit.slab("toe", (leg_w * 1.25, foot_l * 0.34, spec.height * 0.032),
                          (x, -foot_l * 0.62, spec.height * 0.020), mats["plate"], bevel=0.04))
    parts.append(kit.slab("heel", (leg_w * 1.05, foot_l * 0.28, spec.height * 0.05),
                          (x, foot_l * 0.40, spec.height * 0.028), mats["plate"], bevel=0.04))

    parts.append(kit.tube("ankle", leg_w * 0.34, leg_w * 1.1, (x, 0.0, spec.ankle),
                          mats["steel"], axis="X", segments=14))

    # Shin: narrow at the ankle and flaring to the knee. The flare is what makes
    # a leg look like it is carrying something.
    shin_low = spec.knee - spec.ankle
    parts.append(kit.slab("shin_low", (leg_w * 0.80, leg_w * 0.95, shin_low * 0.55),
                          (x, -leg_w * 0.06, spec.ankle + shin_low * 0.28), mats["shell"], bevel=0.05))
    parts.append(kit.slab("shin_high", (leg_w * 1.02, leg_w * 1.15, shin_low * 0.52),
                          (x, -leg_w * 0.02, spec.ankle + shin_low * 0.78), mats["shell"], bevel=0.05))
    parts.append(kit.slab("shin_plate", (leg_w * 0.62, leg_w * 0.18, shin_low * 0.8),
                          (x, -leg_w * 0.62, spec.ankle + shin_low * 0.5), mats["plate"], bevel=0.03))

    parts.append(kit.tube("knee", leg_w * 0.38, leg_w * 1.2, (x, 0.0, spec.knee),
                          mats["steel"], axis="X", segments=16))
    parts.append(kit.slab("knee_guard", (leg_w * 1.05, leg_w * 0.62, spec.height * 0.075),
                          (x, -leg_w * 0.62, spec.knee + spec.height * 0.012),
                          mats["trim"], bevel=0.06))

    # Thigh: the widest part of the leg, because that is where the load is.
    thigh_l = spec.hip - spec.knee
    parts.append(kit.slab("thigh", (leg_w * 1.20, leg_w * 1.35, thigh_l * 0.95),
                          (x, -leg_w * 0.04, spec.knee + thigh_l * 0.5), mats["shell"], bevel=0.06))
    parts.append(kit.slab("thigh_outer", (leg_w * 0.30, leg_w * 1.0, thigh_l * 0.72),
                          (x + leg_w * 0.68 * side, 0.0, spec.knee + thigh_l * 0.52),
                          mats["plate"], bevel=0.04))
    parts.append(kit.slab("thigh_inner", (leg_w * 0.24, leg_w * 0.9, thigh_l * 0.58),
                          (x - leg_w * 0.64 * side, 0.0, spec.knee + thigh_l * 0.46),
                          mats["dark"], bevel=0.03))

    parts.append(kit.tube("hip", leg_w * 0.44, leg_w * 1.0, (x, 0.0, spec.hip),
                          mats["steel"], axis="X", segments=18))
    parts.append(kit.slab("hip_cap", (leg_w * 0.34, leg_w * 0.95, leg_w * 0.95),
                          (x + leg_w * 0.66 * side, 0.0, spec.hip), mats["trim"], bevel=0.05))

    for index in range(int(2 * spec.greebles) + 1):
        z = spec.ankle + shin_low * (0.3 + index * 0.22)
        parts.append(kit.slab("shin_vent", (leg_w * 0.5, leg_w * 0.10, spec.height * 0.008),
                              (x, -leg_w * 0.68, z), mats["trim"], bevel=0.0))
    return parts


# ── arms ─────────────────────────────────────────────────────────────────────


def _arm(spec, mats, side):
    if spec.arm == "none":
        return []
    x = spec.shoulder_out * side
    s = spec.height
    parts = []

    parts.append(kit.tube("shoulder", _bulk(spec, s * 0.048), _bulk(spec, s * 0.075),
                          (x, 0.0, spec.shoulder), mats["steel"], axis="X", segments=18))
    parts.append(kit.slab("shoulder_mount", (_bulk(spec, s * 0.055), _bulk(spec, s * 0.11),
                                             _bulk(spec, s * 0.11)),
                          (x - spec.shoulder_out * 0.42 * side, 0.0, spec.shoulder),
                          mats["dark"], bevel=0.04))

    # Pauldron. Angled outward so the silhouette is a chevron rather than a
    # rectangle sitting on a rectangle, which is most of what makes a machine
    # look designed rather than assembled.
    pw, pd, ph = (v * s for v in spec.pauldron)
    tilt = math.radians(kw_tilt(side))
    pauldron = kit.slab("pauldron", (pw, pd, ph),
                        (x + pw * 0.55 * side, -pd * 0.02, spec.shoulder + ph * 0.22),
                        mats["shell"], bevel=0.09, rotation=(0.0, tilt, 0.0))
    parts.append(pauldron)
    parts.append(kit.slab("pauldron_edge", (pw * 1.08, pd * 1.04, ph * 0.16),
                          (x + pw * 0.55 * side, -pd * 0.02, spec.shoulder + ph * 0.70),
                          mats["trim"], bevel=0.03, rotation=(0.0, tilt, 0.0)))

    upper = s * 0.14
    parts.append(kit.slab("upper_arm", (_bulk(spec, s * 0.075), _bulk(spec, s * 0.085), upper),
                          (x + s * 0.030 * side, 0.0, spec.shoulder - upper * 0.85),
                          mats["plate"], bevel=0.05))
    elbow_y = spec.shoulder - upper * 1.70
    parts.append(kit.tube("elbow", _bulk(spec, s * 0.034), _bulk(spec, s * 0.075),
                          (x + s * 0.030 * side, 0.0, elbow_y), mats["steel"],
                          axis="X", segments=14))

    ax = x + s * 0.030 * side
    if spec.arm in ("gun", "both"):
        parts += _cannon(spec, mats, ax, elbow_y, primary=(spec.arm == "gun" and side > 0))
    if spec.arm in ("blade", "both"):
        parts += _blade(spec, mats, ax, elbow_y, side)
    return parts


def kw_tilt(side):
    return -14 * side


def _cannon(spec, mats, ax, elbow_y, primary):
    s = spec.height
    parts = []
    housing = s * 0.095
    parts.append(kit.slab("gun_housing", (_bulk(spec, housing * 1.15), _bulk(spec, s * 0.22),
                                          _bulk(spec, housing)),
                          (ax, -s * 0.055, elbow_y - s * 0.062), mats["shell"], bevel=0.05))
    parts.append(kit.slab("gun_feed", (_bulk(spec, housing * 0.66), _bulk(spec, s * 0.075),
                                       _bulk(spec, housing * 0.8)),
                          (ax, s * 0.055, elbow_y - s * 0.045), mats["dark"], bevel=0.03))

    barrel_r = _bulk(spec, s * 0.019)
    barrel_l = s * 0.27
    parts.append(kit.tube("barrel", barrel_r, barrel_l,
                          (ax, -s * 0.14 - barrel_l * 0.42, elbow_y - s * 0.062),
                          mats["steel"], axis="Y", segments=16, bevel=0.02))
    parts.append(kit.tube("barrel_shroud", barrel_r * 1.5, barrel_l * 0.4,
                          (ax, -s * 0.14 - barrel_l * 0.15, elbow_y - s * 0.062),
                          mats["dark"], axis="Y", segments=16))
    parts.append(kit.tube("muzzle", barrel_r * 1.35, barrel_l * 0.14,
                          (ax, -s * 0.14 - barrel_l * 0.95, elbow_y - s * 0.062),
                          mats["trim"], axis="Y", segments=16, bevel=0.02))
    return parts


def _blade(spec, mats, ax, elbow_y, side):
    s = spec.height
    out = -s * 0.04 * side
    parts = []
    parts.append(kit.slab("forearm", (_bulk(spec, s * 0.082), _bulk(spec, s * 0.105),
                                      _bulk(spec, s * 0.14)),
                          (ax, out, elbow_y - s * 0.070), mats["plate"], bevel=0.05))
    parts.append(kit.slab("blade_mount", (_bulk(spec, s * 0.070), _bulk(spec, s * 0.12),
                                          _bulk(spec, s * 0.055)),
                          (ax, out - s * 0.06, elbow_y - s * 0.145), mats["dark"], bevel=0.03))
    blade_l = s * 0.30
    parts.append(kit.slab("blade", (_bulk(spec, s * 0.017), blade_l, _bulk(spec, s * 0.05)),
                          (ax, out - s * 0.10 - blade_l * 0.42, elbow_y - s * 0.145),
                          mats["glass"], bevel=0.03))
    parts.append(kit.slab("blade_spine", (_bulk(spec, s * 0.026), blade_l * 0.62,
                                          _bulk(spec, s * 0.026)),
                          (ax, out - s * 0.10 - blade_l * 0.30, elbow_y - s * 0.115),
                          mats["steel"], bevel=0.02))
    return parts


# ── torso ────────────────────────────────────────────────────────────────────


def _torso(spec, mats):
    s = spec.height
    b = spec.bulk
    cw, cd, ch = (v * s for v in spec.chest)
    parts = []

    pelvis_w = _bulk(spec, s * 0.30)
    parts.append(kit.slab("pelvis", (pelvis_w, _bulk(spec, s * 0.19), s * 0.085),
                          (0.0, 0.0, spec.hip + s * 0.030), mats["plate"], bevel=0.07))
    parts.append(kit.slab("pelvis_front", (pelvis_w * 0.7, _bulk(spec, s * 0.05), s * 0.070),
                          (0.0, -cd * 0.42, spec.hip + s * 0.024), mats["shell"], bevel=0.05))

    if spec.skirts:
        # Hip skirts: small plates over the hip joints. They break the line
        # between the legs and the body, which is where a mech most easily looks
        # like two unrelated halves.
        for side in (1, -1):
            parts.append(kit.slab("skirt", (_bulk(spec, s * 0.045), _bulk(spec, s * 0.16),
                                            s * 0.115),
                                  (spec.stance * 1.35 * side, -_bulk(spec, s * 0.03),
                                   spec.hip + s * 0.030),
                                  mats["shell"], bevel=0.05,
                                  rotation=(0.0, math.radians(-16 * side), 0.0)))

    waist = spec.chest_low - spec.hip - s * 0.055
    parts.append(kit.tube("waist_ring", _bulk(spec, s * 0.085), waist * 0.55,
                          (0.0, 0.0, spec.hip + s * 0.055 + waist * 0.4),
                          mats["steel"], axis="Z", segments=20))
    parts.append(kit.slab("waist_block", (_bulk(spec, s * 0.16), _bulk(spec, s * 0.14), waist * 0.6),
                          (0.0, 0.0, spec.hip + s * 0.055 + waist * 0.45),
                          mats["dark"], bevel=0.04))

    chest_h = spec.chest_high - spec.chest_low
    chest_c = (spec.chest_low + spec.chest_high) / 2.0
    parts.append(kit.slab("chest", (cw, cd, chest_h), (0.0, -cd * 0.06, chest_c),
                          mats["shell"], bevel=0.09))
    parts.append(kit.slab("spine", (cw * 0.45, cd * 0.36, chest_h * 0.92),
                          (0.0, cd * 0.52, chest_c), mats["dark"], bevel=0.05))
    parts.append(kit.slab("chest_top", (cw * 0.78, cd * 0.84, s * 0.040),
                          (0.0, -cd * 0.04, spec.chest_high + s * 0.010),
                          mats["plate"], bevel=0.05))

    # The front of the chest: a window band, a plate under it, and a rail
    # between. Three horizontal elements is what stops a large flat face reading
    # as an unfinished surface.
    parts.append(kit.slab("breastplate", (cw * 0.86, cd * 0.10, chest_h * 0.46),
                          (0.0, -cd * 0.56, chest_c - chest_h * 0.24),
                          mats["shell"], bevel=0.04))
    parts.append(kit.slab("chest_rail", (cw * 0.90, cd * 0.07, s * 0.014),
                          (0.0, -cd * 0.60, chest_c - chest_h * 0.02),
                          mats["trim"], bevel=0.02))
    if spec.visor:
        parts.append(kit.slab("cockpit", (cw * 0.50, cd * 0.07, chest_h * 0.17),
                              (0.0, -cd * 0.58, chest_c + chest_h * 0.13),
                              mats["glass"], bevel=0.02))

    # Flank vents. Raised rather than cut: a raised louvre catches light from
    # every angle, and cutting one into a hollow chest would open it up.
    for side in (1, -1):
        for index in range(int(3 * spec.greebles) + 1):
            z = chest_c + chest_h * (0.30 - index * 0.16)
            parts.append(kit.slab("flank_vent", (s * 0.012, cd * 0.16, s * 0.007),
                                  (cw * 0.51 * side, -cd * 0.10, z),
                                  mats["trim"], bevel=0.0))
    return parts


def _back(spec, mats):
    s = spec.height
    cw, cd, ch = (v * s for v in spec.chest)
    chest_c = (spec.chest_low + spec.chest_high) / 2.0
    parts = []

    if spec.back == "none":
        return parts

    parts.append(kit.slab("backpack", (cw * 0.70, cd * 0.40, ch * 0.66),
                          (0.0, cd * 0.78, chest_c + ch * 0.04), mats["shell"], bevel=0.06))

    if spec.back == "thrusters":
        for side in (1, -1):
            parts.append(kit.tube("thruster", _bulk(spec, s * 0.042), _bulk(spec, s * 0.12),
                                  (cw * 0.30 * side, cd * 1.05, chest_c - ch * 0.14),
                                  mats["dark"], axis="Y", segments=16))
            parts.append(kit.tube("thruster_lip", _bulk(spec, s * 0.048), _bulk(spec, s * 0.022),
                                  (cw * 0.30 * side, cd * 1.28, chest_c - ch * 0.14),
                                  mats["hot"], axis="Y", segments=16, bevel=0.01))
    elif spec.back == "mortar":
        # A siege unit's mortar: a short, very wide tube, angled up. It reads as
        # artillery from any direction, which is the whole job.
        parts.append(kit.tube("mortar", s * 0.085, s * 0.34,
                              (0.0, cd * 0.95, chest_c + ch * 0.42),
                              mats["dark"], axis="Y", segments=20,
                              ))
        parts.append(kit.tube("mortar_lip", s * 0.098, s * 0.05,
                              (0.0, cd * 0.95 - s * 0.17, chest_c + ch * 0.42),
                              mats["trim"], axis="Y", segments=20, bevel=0.02))
        for side in (1, -1):
            parts.append(kit.slab("mortar_brace", (s * 0.022, cd * 0.30, ch * 0.5),
                                  (s * 0.075 * side, cd * 0.85, chest_c + ch * 0.30),
                                  mats["plate"], bevel=0.02))
    elif spec.back == "cannon":
        for side in (1, -1):
            parts.append(kit.tube("shoulder_cannon", s * 0.045, s * 0.34,
                                  (cw * 0.44 * side, cd * 0.30, spec.shoulder + s * 0.055),
                                  mats["dark"], axis="Y", segments=18))
            parts.append(kit.slab("cannon_shell", (cw * 0.20, cd * 0.44, ch * 0.30),
                                  (cw * 0.44 * side, cd * 0.42, spec.shoulder + s * 0.048),
                                  mats["plate"], bevel=0.04))
    return parts


def _head(spec, mats):
    s = spec.height
    cw, cd, _ = (v * s for v in spec.chest)
    parts = []
    parts.append(kit.tube("neck", _bulk(spec, s * 0.030), s * 0.045,
                          (0.0, cd * 0.02, spec.head - s * 0.024), mats["dark"],
                          axis="Z", segments=14))
    parts.append(kit.slab("skull", (cw * 0.42, cd * 0.56, s * 0.078),
                          (0.0, cd * 0.03, spec.head + s * 0.030), mats["shell"], bevel=0.07))
    parts.append(kit.slab("visor", (cw * 0.34, cd * 0.09, s * 0.028),
                          (0.0, -cd * 0.26, spec.head + s * 0.036), mats["glass"], bevel=0.02))
    parts.append(kit.slab("crest", (cw * 0.13, cd * 0.42, s * 0.020),
                          (0.0, cd * 0.04, spec.head + s * 0.078), mats["trim"], bevel=0.02))
    parts.append(kit.tube("antenna", s * 0.004, s * 0.070,
                          (cw * 0.13, cd * 0.15, spec.head + s * 0.100), mats["steel"],
                          axis="Z", segments=8, bevel=0.0))
    return parts


# ── the four machines ────────────────────────────────────────────────────────


def player():
    kit.reset()
    shell, trim, glass = ASHFRAME["palette"]
    spec = Spec("ASH", palette("ASH", shell, trim, glass), ASHFRAME["height"],
                hip=ASHFRAME["hip"], knee=ASHFRAME["knee"], stance=ASHFRAME["stance"],
                chest=ASHFRAME["chest"], pauldron=ASHFRAME["pauldron"],
                arm=ASHFRAME["arm"], back=ASHFRAME["back"])
    return build_spec(spec)


def skirmisher():
    kit.reset()
    shell, trim, glass = SKIRMISHER["palette"]
    spec = Spec("SKM", palette("SKM", shell, trim, glass), SKIRMISHER["height"],
                hip=SKIRMISHER["hip"], knee=SKIRMISHER["knee"], stance=SKIRMISHER["stance"],
                chest=SKIRMISHER["chest"], pauldron=SKIRMISHER["pauldron"],
                bulk=SKIRMISHER["bulk"], arm=SKIRMISHER["arm"], back=SKIRMISHER["back"],
                greebles=SKIRMISHER["greebles"])
    return build_spec(spec)


def artillery():
    kit.reset()
    shell, trim, glass = ARTILLERY["palette"]
    spec = Spec("ART", palette("ART", shell, trim, glass), ARTILLERY["height"],
                hip=ARTILLERY["hip"], knee=ARTILLERY["knee"], stance=ARTILLERY["stance"],
                chest=ARTILLERY["chest"], pauldron=ARTILLERY["pauldron"],
                bulk=ARTILLERY["bulk"], arm=ARTILLERY["arm"], back=ARTILLERY["back"],
                skirts=ARTILLERY["skirts"], greebles=ARTILLERY["greebles"])
    return build_spec(spec)


def patriarch():
    kit.reset()
    shell, trim, glass = PATRIARCH["palette"]
    spec = Spec("PAT", palette("PAT", shell, trim, glass, glow=PATRIARCH["glow"]),
                PATRIARCH["height"],
                hip=PATRIARCH["hip"], knee=PATRIARCH["knee"], stance=PATRIARCH["stance"],
                chest=PATRIARCH["chest"], pauldron=PATRIARCH["pauldron"],
                bulk=PATRIARCH["bulk"], arm=PATRIARCH["arm"], back=PATRIARCH["back"],
                greebles=PATRIARCH["greebles"])
    return build_spec(spec)

# ── detail ───────────────────────────────────────────────────────────────────
#
# The parts below add nothing a collision cares about and everything the eye
# does. A machine with clean silhouettes and no small features reads as a
# placeholder at any distance, because there is nothing for the eye to measure
# it against; a dozen deliberate extrusions give it scale and give the light
# somewhere to catch.
#
# All of it is proportional to `spec.greebles`, so a light skirmisher is
# sparsely fitted and the Patriarch is covered in machinery, which is most of
# what separates them once they are the same colour in a dark yard.


def _actuator(spec, mats, name, start, end, radius, material):
    """A piston between two points.

    Placed by its midpoint and rotated to point along the span, which is how a
    real actuator reads: a bright rod crossing a dark gap, under load.
    """
    start = mathutils.Vector(start)
    end = mathutils.Vector(end)
    span = end - start
    length = span.length
    if length < 1e-4:
        return None
    obj = kit.tube(name, radius, length, tuple((start + end) / 2.0), material,
                   axis="Z", segments=10, bevel=0.008)
    obj.rotation_euler = span.to_track_quat("Z", "Y").to_euler()
    return obj


def _limb_detail(spec, mats, side):
    """Pistons and cabling on one leg."""
    x = spec.stance * side
    s = spec.height
    b = spec.bulk
    count = spec.greebles
    parts = []

    # Knee actuator, up the back of the thigh: the thing that visibly holds the
    # leg straight when the machine is standing.
    parts.append(_actuator(spec, mats, "thigh_piston",
                           (x, b * s * 0.055, spec.hip - s * 0.030),
                           (x, b * s * 0.060, spec.knee + s * 0.045),
                           s * 0.011 * b, mats["steel"]))
    # Ankle actuator, the other way, because the ankle is pulled rather than
    # pushed when a foot lands.
    parts.append(_actuator(spec, mats, "shin_piston",
                           (x, b * s * 0.050, spec.knee - s * 0.020),
                           (x, b * s * 0.055, spec.ankle + s * 0.020),
                           s * 0.009 * b, mats["steel"]))

    # Cabling between the hip and the shin, sagging slightly.
    for strand in range(int(2 * count)):
        offset = (strand - 0.5) * s * 0.016
        parts.append(_actuator(spec, mats, "hip_cable",
                               (x + offset, -b * s * 0.045, spec.hip - s * 0.045),
                               (x + offset, -b * s * 0.050, spec.knee + s * 0.010),
                               s * 0.005, mats["dark"]))

    # Armour spurs along the shin, angled back.
    for index in range(int(3 * count) + 1):
        z = spec.ankle + (spec.knee - spec.ankle) * (0.20 + index * 0.24)
        parts.append(kit.slab("shin_fin", (s * 0.010, b * s * 0.055, s * 0.012),
                              (x + s * 0.052 * b * side, -b * s * 0.010, z),
                              mats["plate"], bevel=0.004,
                              rotation=(0.0, math.radians(-22 * side), 0.0)))

    # Toe and heel grips.
    for index in range(3):
        parts.append(kit.slab("foot_cleat", (s * 0.014, s * 0.045, s * 0.016),
                              (x + (index - 1) * s * 0.045 * b, -b * s * 0.145,
                               s * 0.020), mats["trim"], bevel=0.004))
    return [p for p in parts if p is not None]


def _arm_detail(spec, mats, side):
    """Louvres on the pauldron and greebles on the arm."""
    if spec.arm == "none":
        return []
    s = spec.height
    x = spec.shoulder_out * side
    pw, pd, ph = (v * s for v in spec.pauldron)
    parts = []

    # Louvres across the top of the pauldron. The largest flat plate on the
    # machine is the one that most needs breaking up.
    for index in range(int(4 * spec.greebles) + 2):
        y = (index - (spec.greebles * 2.0 + 0.5)) * pd * 0.17
        parts.append(kit.slab("pauldron_louvre", (pw * 1.06, pd * 0.07, ph * 0.10),
                              (x + pw * 0.55 * side, y, spec.shoulder + ph * 0.42),
                              mats["dark"], bevel=0.008,
                              rotation=(0.0, math.radians(-14 * side), 0.0)))

    # A sensor pod on the outer face, and a hardpoint rail under it.
    parts.append(kit.slab("pauldron_pod", (pw * 0.30, pd * 0.22, ph * 0.20),
                          (x + pw * 1.15 * side, -pd * 0.30, spec.shoulder + ph * 0.18),
                          mats["dark"], bevel=0.02))
    parts.append(kit.slab("pauldron_lens", (pw * 0.12, pd * 0.12, ph * 0.10),
                          (x + pw * 1.32 * side, -pd * 0.30, spec.shoulder + ph * 0.18),
                          mats["glass"], bevel=0.01))
    parts.append(kit.slab("arm_rail", (s * 0.012, s * 0.10, s * 0.010),
                          (x + s * 0.075 * side, 0.0, spec.shoulder - s * 0.10),
                          mats["trim"], bevel=0.003))
    return parts


def _torso_detail(spec, mats):
    """Vents, hatches, a sensor cluster and the reactor glow."""
    s = spec.height
    cw, cd, ch = (v * s for v in spec.chest)
    chest_c = (spec.chest_low + spec.chest_high) / 2.0
    count = spec.greebles
    parts = []

    # A sensor cluster above the cockpit: three lenses of different sizes, which
    # reads as a head even on a machine whose head is a box.
    parts.append(kit.slab("chest_sensor", (cw * 0.26, cd * 0.07, ch * 0.07),
                          (0.0, -cd * 0.57, chest_c + ch * 0.33), mats["dark"], bevel=0.012))
    for dx, size in ((-0.020, 0.020), (0.0, 0.028), (0.020, 0.016)):
        parts.append(kit.tube("chest_lens", s * size, cd * 0.045,
                              (dx * s, -cd * 0.61, chest_c + ch * 0.33),
                              mats["glass"], axis="Y", segments=12, bevel=0.003))

    # Louvres down each flank, angled so they read in profile.
    for side in (1, -1):
        for index in range(int(4 * count) + 2):
            z = chest_c - ch * 0.30 + index * ch * 0.13
            parts.append(kit.slab("chest_louvre", (cw * 0.05, cd * 0.24, ch * 0.055),
                                  (cw * 0.47 * side, cd * 0.02, z), mats["dark"],
                                  bevel=0.008,
                                  rotation=(0.0, math.radians(-28 * side), 0.0)))

    # Reactor glow. Small, and set low behind the breastplate rather than on it:
    # a machine's power plant reads through a vent, and a large disc in the
    # middle of the chest reads as a headlight.
    parts.append(kit.tube("reactor", cw * 0.055, cd * 0.08,
                          (0.0, -cd * 0.58, chest_c - ch * 0.42),
                          mats["hot"], axis="Y", segments=14, bevel=0.008))
    parts.append(kit.tube("reactor_ring", cw * 0.085, cd * 0.05,
                          (0.0, -cd * 0.56, chest_c - ch * 0.42),
                          mats["dark"], axis="Y", segments=14, bevel=0.008))
    for index in range(3):
        parts.append(kit.slab("reactor_vent", (cw * 0.20, cd * 0.04, ch * 0.012),
                              (0.0, -cd * 0.60, chest_c - ch * 0.42
                               + (index - 1) * ch * 0.035),
                              mats["dark"], bevel=0.003))

    # Access hatches on the shoulders and the pelvis.
    for side in (1, -1):
        parts.append(kit.slab("chest_hatch", (cw * 0.16, cd * 0.30, ch * 0.04),
                              (cw * 0.30 * side, cd * 0.30, chest_c + ch * 0.48),
                              mats["plate"], bevel=0.012))
    parts.append(kit.slab("pelvis_hatch", (s * 0.10, s * 0.02, s * 0.05),
                          (0.0, -s * 0.10, spec.hip + s * 0.030), mats["dark"], bevel=0.01))
    return parts