"""Hero props for the yard.

The arena is built from the simulation's own list of boxes, and those boxes stay
what the collision uses. These are the handful of *landmarks* — the things a
player navigates by — modelled properly and dropped on top of the box that
already collides there.

That split is deliberate. Collision stays cheap, axis-aligned and identical to
what the simulation believes, and the renderer gets to put something worth
looking at where the box is. A prop and its collider disagreeing by a few
centimetres is invisible; a prop that *is* the collider means every art change
is a gameplay change.
"""

import math

import bpy

import mech_kit as kit


def palette():
    return {
        "container": kit.material("PRP_container", (0.34, 0.38, 0.34), metallic=0.55, roughness=0.62),
        "container_alt": kit.material("PRP_container_alt", (0.42, 0.28, 0.22), metallic=0.5, roughness=0.68),
        "concrete": kit.material("PRP_concrete", (0.46, 0.45, 0.42), metallic=0.0, roughness=0.92),
        "steel": kit.material("PRP_steel", (0.40, 0.43, 0.47), metallic=0.9, roughness=0.34),
        "rust": kit.material("PRP_rust", (0.38, 0.25, 0.17), metallic=0.7, roughness=0.72),
        "hazard": kit.material("PRP_hazard", (0.78, 0.58, 0.10), metallic=0.3, roughness=0.55),
        "dark": kit.material("PRP_dark", (0.10, 0.11, 0.12), metallic=0.5, roughness=0.7),
    }


def shipping_container(mats, length=12.0, width=2.9, height=3.0):
    """A standard container. The yard is full of them and they are what gives
    the arena its scale: everybody knows how big one is."""
    parts = []
    wall = 0.16
    parts.append(kit.slab("cont_floor", (width, length, 0.24), (0, 0, 0.12), mats["dark"], bevel=0.03))

    for side in (1, -1):
        # Corrugation: repeated shallow ribs down each long wall. Cheap, and it
        # is the single detail that makes a box read as a container.
        ribs = int(length / 0.62)
        for index in range(ribs):
            y = (index - (ribs - 1) / 2.0) * (length / ribs)
            parts.append(kit.slab("cont_rib", (0.06, length / ribs * 0.55, height * 0.78),
                                  (side * (width / 2 - wall * 0.4), y, height * 0.52),
                                  mats["container"], bevel=0.015))
        parts.append(kit.slab("cont_corner", (wall * 1.6, wall * 1.6, height),
                              (side * (width / 2 - wall * 0.7), length / 2 - wall * 0.8, height / 2),
                              mats["rust"], bevel=0.02))
        parts.append(kit.slab("cont_corner", (wall * 1.6, wall * 1.6, height),
                              (side * (width / 2 - wall * 0.7), -length / 2 + wall * 0.8, height / 2),
                              mats["rust"], bevel=0.02))

    for end in (1, -1):
        parts.append(kit.slab("cont_end", (width, wall * 1.4, height),
                              (0, end * (length / 2 - wall * 0.7), height / 2),
                              mats["container"], bevel=0.02))
        for hinge in (-1, 1):
            parts.append(kit.slab("cont_door", (0.24, 0.10, height * 0.16),
                                  (hinge * width * 0.28, end * (length / 2), height * 0.42),
                                  mats["dark"], bevel=0.02))

    parts.append(kit.slab("cont_roof", (width, length, wall), (0, 0, height - wall / 2),
                          mats["container"], bevel=0.03))
    return kit.join(parts, "prop_container")


def concrete_barrier(mats, length=3.6, width=1.0, height=1.1):
    """A Jersey barrier. Tapered, which is what makes it look like it would
    actually stop something."""
    parts = []
    parts.append(kit.slab("bar_base", (width, length, height * 0.42),
                          (0, 0, height * 0.21), mats["concrete"], bevel=0.05))
    parts.append(kit.slab("bar_mid", (width * 0.68, length, height * 0.34),
                          (0, 0, height * 0.58), mats["concrete"], bevel=0.04))
    parts.append(kit.slab("bar_top", (width * 0.44, length, height * 0.28),
                          (0, 0, height * 0.86), mats["concrete"], bevel=0.04))
    for index in range(4):
        y = (index - 1.5) * (length / 5)
        parts.append(kit.slab("bar_stripe", (width * 0.48, length / 10, height * 0.10),
                              (0, y, height * 0.80), mats["hazard"], bevel=0.01))
    return kit.join(parts, "prop_barrier")


def fuel_tank(mats, radius=3.0, height=6.0):
    """A vertical storage tank, dished at both ends, with a ladder and a pipe."""
    parts = []
    parts.append(kit.tube("tank_body", radius, height * 0.72, (0, 0, height * 0.5),
                          mats["steel"], axis="Z", segments=28, bevel=0.06))
    for end, z in (("base", height * 0.10), ("top", height * 0.90)):
        dome = kit.tube(f"tank_{end}", radius * 0.98, height * 0.20, (0, 0, z),
                        mats["steel"], axis="Z", segments=28, bevel=0.10)
        parts.append(dome)
    for index in range(3):
        z = height * (0.26 + index * 0.24)
        parts.append(kit.tube("tank_band", radius * 1.02, 0.16, (0, 0, z),
                              mats["rust"], axis="Z", segments=28, bevel=0.02))
    parts.append(kit.tube("tank_pipe", 0.20, height * 0.8, (radius * 0.86, 0, height * 0.5),
                          mats["rust"], axis="Z", segments=12))
    for index in range(7):
        parts.append(kit.slab("tank_rung", (0.06, 0.7, 0.05),
                              (-radius * 0.94, 0, height * (0.16 + index * 0.10)),
                              mats["dark"], bevel=0.0))
    return kit.join(parts, "prop_tank")


def crate_stack(mats, size=1.8):
    """A stack of crates, slightly out of line, because a perfectly aligned
    stack reads as a texture rather than as objects."""
    parts = []
    offsets = [(0.0, 0.0), (0.12, -0.08), (-0.09, 0.14), (0.05, 0.04)]
    for index, (dx, dy) in enumerate(offsets):
        z = size * (index + 0.5)
        crate = kit.slab("crate", (size, size * 1.12, size * 0.94),
                         (dx, dy, z), mats["container_alt"] if index % 2 else mats["container"],
                         bevel=0.05, rotation=(0.0, 0.0, math.radians(index * 3.0)))
        parts.append(crate)
        for edge in (-1, 1):
            parts.append(kit.slab("crate_band", (size * 1.02, size * 1.14, size * 0.09),
                                  (dx, dy, z + edge * size * 0.34), mats["dark"], bevel=0.02,
                                  rotation=(0.0, 0.0, math.radians(index * 3.0))))
    return kit.join(parts, "prop_crates")


def pipe_run(mats, length=10.0, radius=0.42):
    """Two pipes on trestles. Horizontal lines break up a yard of verticals."""
    parts = []
    for index, x in enumerate((-0.55, 0.55)):
        parts.append(kit.tube("pipe", radius, length, (x, 0, 1.5),
                              mats["rust"] if index else mats["steel"], axis="Y", segments=16))
    for index in range(3):
        y = (index - 1) * (length / 2.6)
        parts.append(kit.slab("trestle", (2.0, 0.28, 0.24), (0, y, 0.9), mats["steel"], bevel=0.03))
        for side in (1, -1):
            parts.append(kit.slab("trestle_leg", (0.22, 0.22, 0.9),
                                  (side * 0.8, y, 0.45), mats["steel"], bevel=0.03))
    return kit.join(parts, "prop_pipes")


def build():
    kit.reset()
    mats = palette()
    made = [
        shipping_container(mats),
        concrete_barrier(mats),
        fuel_tank(mats),
        crate_stack(mats),
        pipe_run(mats),
    ]
    for obj in made:
        kit.shade_auto_smooth(obj, 30.0)
    return {"parts": [o.name for o in made], "stats": kit.stats(*made)}
