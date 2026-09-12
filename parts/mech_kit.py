"""Hard-surface helpers for building mechs out of numbers.

A mech is a great many bevelled boxes at exact positions, and describing them is
both faster and more reviewable than pushing primitives around a viewport. These
helpers exist so that a mech is a list of parts rather than a hundred lines of
operator calls, and so that changing a proportion means changing one number.

Conventions, which the whole kit depends on:

- **Metres.** A six-metre mech is six units tall.
- **Z up, feet at the origin.** The same convention the simulation uses for the
  ground plane, so a model dropped into the arena sits on it without adjustment.
- **Facing -Y.** glTF's Y-up conversion maps Blender -Y to glTF +Z, and the game
  treats +Z as forward. A model built facing -Y faces the right way in Godot
  with no rotation applied at import, which is one less thing to get wrong on a
  Friday.
"""

import bpy
import math
from mathutils import Vector


# ── scene ────────────────────────────────────────────────────────────────────


def reset():
    """Empty the file without touching Blender's Python environment.

    `read_factory_settings` would clear it, but it also tears down and rebuilds
    the interpreter, which in a background Blender ends the script that called
    it. The bridge learned this the hard way.
    """
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for blocks in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras,
                   bpy.data.lights, bpy.data.images):
        for block in list(blocks):
            if block.users == 0:
                blocks.remove(block)
    bpy.context.scene.unit_settings.system = "METRIC"
    return "reset"


def material(name, colour, metallic=0.8, roughness=0.4, emission=None, emission_strength=0.0):
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*colour, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


# ── primitives ───────────────────────────────────────────────────────────────


def slab(name, size, centre, mat, bevel=0.03, segments=3, rotation=(0, 0, 0), collection=None):
    """A bevelled box.

    The bevel is what makes it read as a manufactured part: a mathematically
    sharp edge catches no light, so a box without one looks like a placeholder
    however carefully it is positioned.
    """
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=centre)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (size[0], size[1], size[2])
    obj.rotation_euler = rotation
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        bevel_object(obj, bevel, segments)
    _finish(obj, mat, collection)
    return obj


def tube(name, radius, depth, centre, mat, axis="Z", segments=16, bevel=0.02, collection=None):
    rotation = {"Z": (0, 0, 0), "X": (0, math.pi / 2, 0), "Y": (math.pi / 2, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius, depth=depth, vertices=segments, location=centre, rotation=rotation
    )
    obj = bpy.context.active_object
    obj.name = name
    if bevel > 0:
        bevel_object(obj, bevel, 2)
    _finish(obj, mat, collection)
    return obj


def wedge(name, size, centre, mat, taper=0.5, collection=None):
    """A box whose top is narrower than its bottom in Y, for angled plating."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=centre)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    mesh = obj.data
    for vertex in mesh.vertices:
        if vertex.co.z > 0:
            vertex.co.y *= taper
    bevel_object(obj, 0.02, 2)
    _finish(obj, mat, collection)
    return obj


def _finish(obj, mat, collection):
    if collection is not None:
        for existing in list(obj.users_collection):
            existing.objects.unlink(obj)
        collection.objects.link(obj)
    if mat is not None:
        obj.data.materials.clear()
        obj.data.materials.append(mat)


def bevel_object(obj, width, segments):
    modifier = obj.modifiers.new(name="bevel", type="BEVEL")
    modifier.width = width
    modifier.segments = segments
    modifier.limit_method = "ANGLE"
    modifier.angle_limit = math.radians(40)
    modifier.harden_normals = False
    _apply(obj, modifier.name)


def _apply(obj, modifier_name):
    previous = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier_name)
    if previous is not None:
        bpy.context.view_layer.objects.active = previous


# ── combination ──────────────────────────────────────────────────────────────


def cut(target, cutters):
    """Boolean-subtract cutters from target and delete them.

    Cuts are how a solid becomes a machine: panels get recessed, hulls get
    pierced for joints, and vents get carved rather than drawn on.
    """
    if not isinstance(cutters, (list, tuple)):
        cutters = [cutters]
    for index, cutter in enumerate(cutters):
        modifier = target.modifiers.new(name=f"cut{index}", type="BOOLEAN")
        modifier.operation = "DIFFERENCE"
        modifier.object = cutter
        modifier.solver = "EXACT"
        _apply(target, modifier.name)
        bpy.data.objects.remove(cutter, do_unlink=True)
    return target


def mirror(obj, axis="X", name=None):
    """Copy an object across an axis, keeping the original.

    Modelled rather than applied: a mech is symmetric, and building one side and
    mirroring it is both half the work and the only reliable way to keep the two
    halves identical.
    """
    duplicate = obj.copy()
    duplicate.data = obj.data.copy()
    duplicate.name = name or f"{obj.name}_m"
    bpy.context.scene.collection.objects.link(duplicate)

    index = {"X": 0, "Y": 1, "Z": 2}[axis]
    duplicate.scale[index] = -1
    previous = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = duplicate
    bpy.ops.object.select_all(action="DESELECT")
    duplicate.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # A negative scale inverts the normals; recalculating them is what stops a
    # mirrored half rendering inside out.
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    if previous is not None:
        bpy.context.view_layer.objects.active = previous
    return duplicate


def duplicate(obj, offset=(0, 0, 0), name=None):
    copy = obj.copy()
    copy.data = obj.data.copy()
    copy.name = name or f"{obj.name}_copy"
    copy.location = Vector(obj.location) + Vector(offset)
    bpy.context.scene.collection.objects.link(copy)
    return copy


def join(objects, name):
    """Join into one mesh. Fewer draw calls, and one node in the exported glTF."""
    objects = [o for o in objects if o is not None]
    if not objects:
        raise ValueError("nothing to join")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    joined = bpy.context.active_object
    joined.name = name
    return joined


def shade_auto_smooth(obj, angle=35.0):
    """Smooth the curved surfaces and leave the flat ones faceted.

    A bevelled hard-surface mesh wants this: without it the bevels look like
    painted stripes, and with everything smoothed the panels look like cloth.
    """
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
    return obj


# ── measuring ────────────────────────────────────────────────────────────────


def stats(*objects):
    polygons = 0
    vertices = 0
    for obj in objects:
        if obj.type != "MESH":
            continue
        polygons += len(obj.data.polygons)
        vertices += len(obj.data.vertices)
    low = Vector((1e9, 1e9, 1e9))
    high = Vector((-1e9, -1e9, -1e9))
    for obj in objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            low = Vector((min(low.x, point.x), min(low.y, point.y), min(low.z, point.z)))
            high = Vector((max(high.x, point.x), max(high.y, point.y), max(high.z, point.z)))
    return {
        "polygons": polygons,
        "vertices": vertices,
        "size": [round(high.x - low.x, 3), round(high.y - low.y, 3), round(high.z - low.z, 3)],
        "min": [round(v, 3) for v in low],
        "max": [round(v, 3) for v in high],
    }
