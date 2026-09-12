"""The reference mech: a faithful build of the supplied concept sheet.

Four views were given — front, three-quarter, back, side — and this reproduces
the design they show: white armour over olive-drab secondary plate over dark
mechanical joints, with orange accents at the chest, shins and backpack, a small
helmeted head with a dark visor set low between large rounded pauldrons, a
backpack carrying an antenna mast, articulated hands, and heavy angular feet.

Written as its own module rather than as another entry in `mechs.py` because it
is not a variation on those machines. The proportions are different, the colour
blocking is different, and it has parts they do not — hands with fingers, a
backpack, an antenna. Bending the spec-driven builder far enough to express this
would have made both harder to read.

The rig is the same rig. `torso`, `head`, `leg_l`, `knee_r`, `foot_l`, `arm_l`,
`gun_l`, `blade_l` and the rest are the joints `mechs.py` exports, because the
game drives those names and a new model that renamed them would animate nothing.
"""

import math

import bpy
import mathutils

import mech_kit as kit
import weapons

HEIGHT = 6.0

# Fractions of the height, read off the concept sheet.
#
# The first pass at these was badly wrong in one direction: every width was
# about half what it should be, and the result was a stick figure wearing the
# right colours. What the sheet actually shows is a broad machine -- the chest
# alone is a quarter of the height across, and the shoulders are wider than the
# hips by a third. Heights were close enough; widths were not.
ANKLE = 0.077 * HEIGHT
KNEE = 0.303 * HEIGHT
HIP = 0.520 * HEIGHT
WAIST = 0.592 * HEIGHT
CHEST_LOW = 0.610 * HEIGHT
CHEST_HIGH = 0.837 * HEIGHT
SHOULDER = 0.797 * HEIGHT
NECK = 0.850 * HEIGHT
STANCE = 0.067 * HEIGHT

# Across, rather than up.
CHEST_HALF = 0.134 * HEIGHT
CHEST_DEPTH = 0.103 * HEIGHT
SHOULDER_X = 0.143 * HEIGHT
PAULDRON_OUT = 0.190 * HEIGHT
HIP_HALF = 0.110 * HEIGHT
THIGH_W = 0.104 * HEIGHT
SHIN_W = 0.086 * HEIGHT
FOOT_W = 0.092 * HEIGHT
FOOT_L = 0.130 * HEIGHT
UPPER_ARM = 0.048 * HEIGHT
FOREARM = 0.058 * HEIGHT


def palette():
    """The sheet's own colours.

    Sampled from the concept rather than invented: an off-white that is warm
    rather than neutral (a pure white reads as plastic at this scale), an olive
    drab that is genuinely dark, near-black joints, and a single saturated
    orange used sparingly enough that it still means something.
    """
    return {
        "white": kit.material("REF_white", (0.780, 0.775, 0.745), metallic=0.25, roughness=0.48),
        "olive": kit.material("REF_olive", (0.245, 0.275, 0.195), metallic=0.35, roughness=0.58),
        "dark": kit.material("REF_dark", (0.085, 0.090, 0.098), metallic=0.65, roughness=0.42),
        "orange": kit.material("REF_orange", (0.880, 0.420, 0.075), metallic=0.15, roughness=0.42),
        "steel": kit.material("REF_steel", (0.480, 0.500, 0.530), metallic=1.0, roughness=0.28),
        "visor": kit.material("REF_visor", (0.030, 0.038, 0.048), metallic=0.4, roughness=0.10,
                              emission=(0.45, 0.72, 0.85), emission_strength=1.4),
    }


# ── the head ─────────────────────────────────────────────────────────────────


def head(mats):
    parts = []
    parts.append(kit.tube("neck", 0.17, 0.18, (0.0, 0.01, NECK - 0.06), mats["dark"],
                          axis="Z", segments=14))

    # Helmet: a wide, shallow box with a crest. The sheet's head is small and
    # reads mostly as silhouette -- a brow, a visor band and a jaw.
    parts.append(kit.slab("skull", (0.62, 0.68, 0.38), (0.0, 0.02, NECK + 0.20),
                          mats["white"], bevel=0.07))
    parts.append(kit.slab("brow", (0.66, 0.20, 0.11), (0.0, -0.27, NECK + 0.29),
                          mats["white"], bevel=0.03))
    parts.append(kit.slab("visor", (0.52, 0.10, 0.13), (0.0, -0.315, NECK + 0.17),
                          mats["visor"], bevel=0.02))
    parts.append(kit.slab("jaw", (0.46, 0.28, 0.13), (0.0, -0.20, NECK + 0.055),
                          mats["dark"], bevel=0.03))
    parts.append(kit.slab("chin", (0.26, 0.07, 0.07), (0.0, -0.345, NECK + 0.06),
                          mats["orange"], bevel=0.015))
    # Ear blocks and a small crest, which is what stops the helmet being a box.
    for side in (1, -1):
        parts.append(kit.slab("ear", (0.085, 0.30, 0.21), (0.315 * side, 0.02, NECK + 0.20),
                              mats["dark"], bevel=0.03))
    parts.append(kit.slab("crest", (0.20, 0.54, 0.07), (0.0, 0.06, NECK + 0.40),
                          mats["olive"], bevel=0.03))
    return parts


# ── the torso ────────────────────────────────────────────────────────────────


def torso(mats):
    parts = []
    half = CHEST_HALF      # half the chest width, the broadest mass on the machine
    depth = CHEST_DEPTH

    # Pelvis and waist. The sheet's waist is narrow and dark, which is what
    # makes the chest above it read as heavy.
    # The pelvis, the waist and the abdomen are one continuous column here.
    # The first pass left three separate blocks with air between them, which
    # read as a machine with its middle missing: the chest ended at 3.66 and the
    # pelvis started at 3.20, and nothing bridged the space.
    parts.append(kit.slab("pelvis", (HIP_HALF * 1.55, 0.56, 0.44), (0.0, 0.0, HIP + 0.04),
                          mats["dark"], bevel=0.06))
    for side in (1, -1):
        parts.append(kit.slab("pelvis_plate", (0.20, 0.50, 0.42),
                              (HIP_HALF * 0.92 * side, -0.02, HIP + 0.05),
                              mats["white"], bevel=0.05,
                              rotation=(0.0, math.radians(-12 * side), 0.0)))
        parts.append(kit.slab("pelvis_rear", (0.26, 0.15, 0.30),
                              (HIP_HALF * 0.62 * side, 0.28, HIP + 0.02),
                              mats["olive"], bevel=0.035))
    parts.append(kit.tube("waist", 0.30, 0.20, (0.0, 0.0, WAIST - 0.03), mats["steel"],
                          axis="Z", segments=18))
    parts.append(kit.slab("abdomen", (0.70, 0.50, 0.42), (0.0, -0.01, WAIST + 0.10),
                          mats["olive"], bevel=0.05))
    parts.append(kit.slab("abdomen_front", (0.52, 0.14, 0.34),
                          (0.0, -CHEST_DEPTH * 0.46, WAIST + 0.10),
                          mats["white"], bevel=0.04))

    # Chest. One broad white plate with a dark spine behind it and an orange
    # rule across the front -- the single most recognisable thing on the sheet.
    span = CHEST_HIGH - CHEST_LOW
    centre = (CHEST_LOW + CHEST_HIGH) / 2.0
    parts.append(kit.slab("chest", (half * 2, depth, span), (0.0, -0.02, centre),
                          mats["white"], bevel=0.075))
    # The chest is a wedge, not a slab: wider at the shoulders than at the
    # waist. Two flanks do that better than a taper on the main box, because a
    # taper would round the corners the sheet shows as hard.
    for side in (1, -1):
        parts.append(kit.slab("chest_wing", (half * 0.42, depth * 0.92, span * 0.62),
                              (half * 0.86 * side, -0.01, centre + span * 0.12),
                              mats["white"], bevel=0.06,
                              rotation=(0.0, math.radians(-7 * side), 0.0)))
    parts.append(kit.slab("chest_spine", (0.52, 0.24, span * 0.90), (0.0, depth * 0.52, centre),
                          mats["dark"], bevel=0.04))
    parts.append(kit.slab("chest_collar", (half * 1.5, depth * 0.85, 0.13),
                          (0.0, -0.03, CHEST_HIGH + 0.03), mats["olive"], bevel=0.05))

    # The orange rule, and the dark channel it sits in.
    parts.append(kit.slab("chest_channel", (half * 1.72, 0.10, 0.115),
                          (0.0, -depth * 0.50, centre + span * 0.10), mats["dark"], bevel=0.02))
    parts.append(kit.slab("chest_stripe", (half * 1.60, 0.07, 0.055),
                          (0.0, -depth * 0.54, centre + span * 0.10), mats["orange"], bevel=0.012))

    # The angular centre plate below the rule: the sheet's chest is not a plain
    # box, it narrows toward the waist with a raised central form.
    parts.append(kit.tube("chest_core", 0.145, 0.10, (0.0, -depth * 0.50, centre - span * 0.16),
                          mats["dark"], axis="Y", segments=16, bevel=0.02))
    parts.append(kit.slab("chest_lower", (half * 1.30, 0.13, span * 0.30),
                          (0.0, -depth * 0.46, centre - span * 0.26), mats["olive"], bevel=0.035))

    # Faceting. The sheet's chest is a set of angled planes rather than one
    # face, and that is most of what separates a designed machine from a box
    # with a stripe on it: a raised centre plate, and a bevel running down to
    # the waist.
    parts.append(kit.slab("chest_centre", (half * 0.84, 0.09, span * 0.50),
                          (0.0, -depth * 0.545, centre - span * 0.12),
                          mats["white"], bevel=0.035))
    parts.append(kit.slab("chest_bevel", (half * 0.78, 0.09, span * 0.20),
                          (0.0, -depth * 0.52, centre - span * 0.42),
                          mats["olive"], bevel=0.03,
                          rotation=(math.radians(22), 0.0, 0.0)))

    # Shoulder blocks the pauldrons hang from.
    for side in (1, -1):
        parts.append(kit.slab("chest_flank", (0.16, depth * 0.86, span * 0.78),
                              (half * 0.94 * side, -0.01, centre - span * 0.02),
                              mats["olive"], bevel=0.04))
    return parts


def backpack(mats):
    """The pack and its mast.

    It sits high and wide between the shoulders, which is a large part of why
    the machine reads as a machine rather than a person in armour.
    """
    parts = []
    z = CHEST_HIGH - 0.10
    parts.append(kit.slab("pack", (0.76, 0.42, 0.72), (0.0, 0.44, z), mats["olive"], bevel=0.06))
    parts.append(kit.slab("pack_lid", (0.80, 0.46, 0.09), (0.0, 0.44, z + 0.39),
                          mats["white"], bevel=0.03))
    for side in (1, -1):
        parts.append(kit.slab("pack_vent", (0.10, 0.30, 0.44), (0.40 * side, 0.44, z),
                              mats["dark"], bevel=0.02))
        for index in range(3):
            parts.append(kit.slab("pack_fin", (0.045, 0.26, 0.05),
                                  (0.44 * side, 0.44, z + 0.15 - index * 0.15),
                                  mats["orange"], bevel=0.008))
    # Mast. Thin, tall, and off-centre, exactly as the sheet has it.
    parts.append(kit.tube("mast_base", 0.055, 0.12, (0.22, 0.50, z + 0.45),
                          mats["dark"], axis="Z", segments=10))
    parts.append(kit.tube("mast", 0.016, 1.05, (0.22, 0.50, z + 1.00), mats["steel"],
                          axis="Z", segments=8, bevel=0.0))
    return parts


# ── arms ─────────────────────────────────────────────────────────────────────


def arm(mats, side):
    x = SHOULDER_X * side
    parts = []

    # Pauldron: the second-largest mass on the machine. Rounded on the sheet --
    # a stack of chamfered slabs rather than a single block, which is what gives
    # it a curve without smoothing the whole thing into a blob.
    parts.append(kit.tube("shoulder", 0.23, 0.30, (x, 0.0, SHOULDER), mats["steel"],
                          axis="X", segments=18))
    # A cap, rounded by one deep bevel rather than by stacked layers.
    #
    # Two attempts at stacking came first and both were worse. Slabs marching
    # outward along the arm are a staircase; slabs sharing an axis but varying
    # in thickness show their edges as ridges, so the cap reads as a stack of
    # tubes. What the sheet actually draws is a single form with a generous
    # chamfer, and a bevel with enough segments produces exactly that while
    # keeping the hard outer edge -- which smoothing the mesh would lose.
    reach = PAULDRON_OUT - SHOULDER_X
    hub = x + reach * 0.50 * side
    tilt = math.radians(-11 * side)
    parts.append(kit.slab("pauldron", (0.44, 1.00, 0.52), (hub, -0.02, SHOULDER + 0.02),
                          mats["white"], bevel=0.13, segments=5, rotation=(0.0, tilt, 0.0)))
    parts.append(kit.slab("pauldron_under", (0.38, 0.84, 0.16), (hub, -0.02, SHOULDER - 0.28),
                          mats["olive"], bevel=0.06, rotation=(0.0, tilt, 0.0)))

    # Upper arm: dark, narrow, mostly hidden behind the pauldron.
    parts.append(kit.slab("upper_arm", (UPPER_ARM, UPPER_ARM * 1.1, 0.56), (x + 0.07 * side, 0.0, SHOULDER - 0.44),
                          mats["dark"], bevel=0.035))
    parts.append(kit.tube("elbow", 0.135, 0.30, (x + 0.07 * side, 0.0, SHOULDER - 0.78),
                          mats["steel"], axis="X", segments=14))

    # Forearm: white plated over an olive core, wider than the upper arm.
    parts.append(kit.slab("forearm", (FOREARM, FOREARM * 1.15, 0.62), (x + 0.07 * side, -0.01, SHOULDER - 1.14),
                          mats["dark"], bevel=0.035))
    parts.append(kit.slab("forearm_plate", (FOREARM * 1.15, 0.24, 0.54), (x + 0.07 * side, -0.16, SHOULDER - 1.12),
                          mats["white"], bevel=0.04))
    parts.append(kit.slab("forearm_edge", (FOREARM * 1.05, 0.26, 0.07), (x + 0.07 * side, -0.02, SHOULDER - 1.46),
                          mats["olive"], bevel=0.015))

    # Hand. Fingers matter: the sheet's hands are articulated, and a mitt reads
    # as unfinished at any distance.
    hand_z = SHOULDER - 1.62
    parts.append(kit.slab("hand", (0.28, 0.22, 0.24), (x + 0.07 * side, -0.01, hand_z),
                          mats["dark"], bevel=0.035))
    for index in range(4):
        offset = (index - 1.5) * 0.062
        parts.append(kit.slab("finger", (0.048, 0.19, 0.075),
                              (x + 0.07 * side + offset, -0.07, hand_z - 0.155),
                              mats["dark"], bevel=0.018))
        parts.append(kit.slab("finger_tip", (0.044, 0.13, 0.062),
                              (x + 0.07 * side + offset, -0.14, hand_z - 0.225),
                              mats["dark"], bevel=0.015))
    parts.append(kit.slab("thumb", (0.055, 0.14, 0.055),
                          (x + 0.07 * side + 0.13 * side, -0.08, hand_z - 0.075),
                          mats["dark"], bevel=0.018))
    return parts


# ── legs ─────────────────────────────────────────────────────────────────────


def leg(mats, side):
    x = STANCE * side
    parts = []

    # Foot: broad, angular, with a split toe. The sheet's feet are the widest
    # part of the lower machine and sit flat.
    parts.append(kit.slab("foot", (FOOT_W, FOOT_L, 0.20), (x, -0.05, 0.10), mats["dark"], bevel=0.045))
    parts.append(kit.slab("foot_top", (FOOT_W * 0.86, FOOT_L * 0.72, 0.17), (x, -0.03, 0.26), mats["olive"], bevel=0.04))
    parts.append(kit.slab("toe", (FOOT_W * 0.90, 0.26, 0.15), (x, -0.42, 0.085), mats["olive"], bevel=0.035))
    parts.append(kit.slab("toe_cap", (FOOT_W * 0.76, 0.12, 0.11), (x, -0.53, 0.07), mats["white"], bevel=0.025))
    parts.append(kit.slab("heel", (FOOT_W * 0.76, 0.20, 0.19), (x, 0.32, 0.11), mats["dark"], bevel=0.035))
    for index in (-1, 1):
        parts.append(kit.slab("foot_vent", (0.06, 0.20, 0.11),
                              (x + index * 0.17, -0.18, 0.21), mats["orange"], bevel=0.012))

    parts.append(kit.tube("ankle", 0.135, 0.30, (x, 0.02, ANKLE + 0.06), mats["steel"],
                          axis="X", segments=14))

    # Shin: white plate down the front, olive flanking it, tapering to the
    # ankle. Orange rules at the bottom, as on the sheet.
    shin_low = ANKLE + 0.08
    shin_high = KNEE - 0.10
    shin_mid = (shin_low + shin_high) / 2.0
    shin_h = shin_high - shin_low
    parts.append(kit.slab("shin_core", (SHIN_W * 0.80, SHIN_W * 0.95, shin_h), (x, 0.0, shin_mid),
                          mats["dark"], bevel=0.04))
    parts.append(kit.slab("shin_plate", (SHIN_W, SHIN_W * 0.62, shin_h * 0.96), (x, -SHIN_W * 0.48, shin_mid),
                          mats["white"], bevel=0.045))
    for side_sign in (1, -1):
        parts.append(kit.slab("shin_flank", (SHIN_W * 0.24, SHIN_W * 0.82, shin_h * 0.80),
                              (x + SHIN_W * 0.50 * side_sign, 0.0, shin_mid), mats["olive"], bevel=0.03))
    for index in range(2):
        parts.append(kit.slab("shin_rule", (SHIN_W * 0.80, 0.07, 0.045),
                              (x, -SHIN_W * 0.78, shin_low + 0.12 + index * 0.11),
                              mats["orange"], bevel=0.008))
    parts.append(kit.slab("calf", (SHIN_W * 0.66, SHIN_W * 0.42, shin_h * 0.70), (x, SHIN_W * 0.52, shin_mid + 0.02),
                          mats["olive"], bevel=0.03))

    # Knee: a big dark drum with a white cap over it.
    parts.append(kit.tube("knee", 0.185, 0.38, (x, 0.0, KNEE), mats["steel"],
                          axis="X", segments=18))
    parts.append(kit.slab("knee_cap", (SHIN_W * 0.94, 0.26, 0.26), (x, -SHIN_W * 0.52, KNEE + 0.015),
                          mats["white"], bevel=0.035))

    # Thigh: thickest at the hip, white outer over olive inner.
    thigh_low = KNEE + 0.10
    thigh_high = HIP - 0.08
    thigh_mid = (thigh_low + thigh_high) / 2.0
    thigh_h = thigh_high - thigh_low
    parts.append(kit.slab("thigh_core", (THIGH_W * 0.86, THIGH_W * 0.96, thigh_h), (x, -0.01, thigh_mid),
                          mats["olive"], bevel=0.045))
    parts.append(kit.slab("thigh_plate", (THIGH_W, THIGH_W * 0.62, thigh_h * 0.92),
                          (x, -THIGH_W * 0.54, thigh_mid + 0.02), mats["white"], bevel=0.05))
    parts.append(kit.slab("thigh_outer", (THIGH_W * 0.28, THIGH_W * 0.82, thigh_h * 0.80),
                          (x + THIGH_W * 0.56 * side, -0.01, thigh_mid), mats["white"], bevel=0.035))
    parts.append(kit.slab("thigh_rear", (THIGH_W * 0.72, THIGH_W * 0.28, thigh_h * 0.72),
                          (x, THIGH_W * 0.56, thigh_mid - 0.02), mats["dark"], bevel=0.03))

    parts.append(kit.tube("hip", 0.195, 0.36, (x, 0.0, HIP), mats["steel"], axis="X", segments=18))
    parts.append(kit.slab("hip_cap", (0.17, 0.36, 0.34), (x + THIGH_W * 0.62 * side, 0.0, HIP),
                          mats["olive"], bevel=0.035))
    return parts


# ── assembly ─────────────────────────────────────────────────────────────────

# Where the weapons hang. The hands, because that is where a machine holds a
# gun, and the launcher on the left shoulder where the sheet leaves a hardpoint
# and where the arm does not swing through it.
HAND_R = (-(SHOULDER_X + 0.07), 0.0, SHOULDER - 1.62)
HAND_L = (SHOULDER_X + 0.07, 0.0, SHOULDER - 1.62)
POD_AT = (SHOULDER_X * 1.26, 0.24, SHOULDER + 0.30)

PIVOTS = {
    "torso": ((0.0, 0.0, HIP), None),
    "head": ((0.0, 0.0, NECK), "torso"),
    "leg_l": ((STANCE, 0.0, HIP), None),
    "leg_r": ((-STANCE, 0.0, HIP), None),
    "knee_l": ((STANCE, 0.0, KNEE), "leg_l"),
    "knee_r": ((-STANCE, 0.0, KNEE), "leg_r"),
    "foot_l": ((STANCE, 0.0, ANKLE), "knee_l"),
    "foot_r": ((-STANCE, 0.0, ANKLE), "knee_r"),
    "arm_l": ((SHOULDER_X, 0.0, SHOULDER), "torso"),
    "arm_r": ((-SHOULDER_X, 0.0, SHOULDER), "torso"),
    "gun_l": (HAND_L, "arm_l"),
    "gun_r": (HAND_R, "arm_r"),
    "blade_l": (HAND_L, "arm_l"),
    "blade_r": (HAND_R, "arm_r"),
}


def build():
    """Build the machine and return what was made."""
    kit.reset()
    mats = palette()

    grouped = {}

    def collect(node, builder):
        before = set(bpy.data.objects)
        builder()
        for obj in bpy.data.objects:
            if obj in before or obj.type != "MESH":
                continue
            grouped.setdefault(node, []).append(obj)

    for side, tag in ((1, "l"), (-1, "r")):
        collect(f"leg_{tag}", lambda s=side: leg(mats, s))
        collect(f"arm_{tag}", lambda s=side: arm(mats, s))
    collect("torso", lambda: torso(mats))
    collect("torso", lambda: backpack(mats))
    collect("head", lambda: head(mats))

    # The weapons, on the joints the game drives them from.
    #
    # The sheet is a bare machine and has no weapons, but the game fires a
    # cannon, a launcher and a blade, and it drives them through joints named
    # gun_l, gun_r, blade_l and blade_r -- recoil slides the gun joints and the
    # blade joints swing through the cut. A mech exported without them animates
    # nothing when it fires, and the failure is a warning in a log rather than
    # anything a player would report as a bug.
    #
    # `weapons.py` builds each piece with its mounting point at its own origin
    # and its muzzle down -Y, so mounting one is a translation to the joint and
    # nothing else. Both sides get a joint, because the game looks for both;
    # only two of them carry anything, which is what the sheet's machine would
    # do if it were armed.
    weapon_mats = weapons.palette()

    def mount(node, builder, at):
        def build_and_place():
            offset = mathutils.Vector(at)
            for obj in builder(weapon_mats):
                obj.location = obj.location + offset
        collect(node, build_and_place)

    mount("gun_r", weapons.autocannon, HAND_R)
    mount("blade_l", weapons.arc_blade, HAND_L)
    mount("torso", weapons.missile_pod, POD_AT)

    # The hierarchy, built parents first so a joint can be offset from a parent
    # that already exists. The world positions are kept separately from the
    # objects' own locations, because once a joint is parented its location
    # becomes an offset -- and reading it back to place a part is how a mech ends
    # up standing a metre and a half in the air.
    world = {name: mathutils.Vector(position) for name, (position, _) in PIVOTS.items()}
    nodes = {}
    for name, (position, _parent) in PIVOTS.items():
        empty = bpy.data.objects.new(f"ASH_{name}", None)
        empty.empty_display_size = HEIGHT * 0.03
        bpy.context.scene.collection.objects.link(empty)
        empty.location = position
        nodes[name] = empty
    for name, (_position, parent) in PIVOTS.items():
        if parent is None:
            continue
        nodes[name].parent = nodes[parent]
        nodes[name].location = world[name] - world[parent]

    merged = []
    for node_name, objects in grouped.items():
        by_material = {}
        for obj in objects:
            if not obj.data.materials:
                continue
            by_material.setdefault(obj.data.materials[0].name, []).append(obj)
        for key, group in by_material.items():
            joined = kit.join(group, f"ASH_{node_name}_{key.rsplit('_', 1)[-1]}")
            joined.parent = nodes[node_name]
            joined.location = joined.location - world[node_name]
            kit.shade_auto_smooth(joined, 30.0)
            merged.append(joined)

    return {
        "parts": [o.name for o in merged],
        "nodes": sorted(grouped),
        "stats": kit.stats(*merged),
    }
