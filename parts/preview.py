"""Render a model so a person — or an agent — can look at it.

Three views on a neutral backdrop, lit so that form reads rather than so that it
looks nice: a key from the upper front left, a fill from the right, and a rim
from behind. That is the setup that shows whether a shape works, which is the
only question a modelling preview needs to answer.

An agent cannot model what it has not seen, so this is as much a tool as the
extrusion helpers are.
"""

import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def clear_cameras_and_lights():
    for obj in list(bpy.data.objects):
        if obj.type in ("CAMERA", "LIGHT"):
            bpy.data.objects.remove(obj, do_unlink=True)


def studio(strength=1.0):
    """A three-point rig, in world units scaled to whatever is in the scene."""
    clear_cameras_and_lights()
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in \
        [i.identifier for i in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"

    world = bpy.data.worlds.get("Preview") or bpy.data.worlds.new("Preview")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs[0].default_value = (0.05, 0.06, 0.08, 1.0)
        background.inputs[1].default_value = 0.6

    lights = [
        ("key", 4.5 * strength, (1.0, -0.55, 0.75), 3.2, (1.0, 0.97, 0.92)),
        ("fill", 1.2 * strength, (-0.9, -0.4, 0.35), 4.0, (0.72, 0.82, 1.0)),
        ("rim", 2.2 * strength, (-0.3, 0.95, 0.5), 3.0, (0.85, 0.92, 1.0)),
    ]
    for name, energy, direction, distance, colour in lights:
        data = bpy.data.lights.new(name, type="AREA")
        data.energy = energy * 900
        data.size = 6.0
        data.color = colour
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = Vector(direction).normalized() * distance * 8.0
        light.rotation_euler = (Vector((0, 0, 0)) - light.location).to_track_quat("-Z", "Y").to_euler()

    # A ground plane, so the model is standing on something rather than floating
    # in a void. Reads as scale, and catches the contact shadow.
    if "preview_ground" not in bpy.data.objects:
        bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, 0))
        ground = bpy.context.active_object
        ground.name = "preview_ground"
        mat = bpy.data.materials.new("preview_ground")
        mat.use_nodes = True
        bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        bsdf.inputs["Base Color"].default_value = (0.16, 0.17, 0.19, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.85
        ground.data.materials.append(mat)


def bounds(objects):
    """The true bounding box, centre and radius, of some objects."""
    low = Vector((1e9, 1e9, 1e9))
    high = Vector((-1e9, -1e9, -1e9))
    for obj in objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            low = Vector((min(low.x, point.x), min(low.y, point.y), min(low.z, point.z)))
            high = Vector((max(high.x, point.x), max(high.y, point.y), max(high.z, point.z)))
    centre = (low + high) / 2.0
    return centre, (high - low).length / 2.0


def camera_for(objects, angle_degrees, elevation=0.32, lens=40.0, margin=1.25):
    """A camera that frames the objects, whatever size they are.

    Fitted from the bounds rather than from a guess at the size, because a
    preview that crops the thing it is previewing is worse than no preview: it
    looks like the model is fine.
    """
    for obj in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(obj, do_unlink=True)

    centre, radius = bounds(objects)
    yaw = math.radians(angle_degrees)

    data = bpy.data.cameras.new("preview_camera")
    data.lens = lens
    # Half the vertical field of view, from the sensor and the lens, so the
    # distance is right for any lens rather than tuned for one.
    sensor = data.sensor_height if data.sensor_fit == "VERTICAL" else data.sensor_width
    half_fov = math.atan(sensor / (2.0 * lens))
    distance = radius * margin / math.sin(half_fov)

    camera = bpy.data.objects.new("preview_camera", data)
    bpy.context.scene.collection.objects.link(camera)
    position = centre + Vector((math.sin(yaw) * math.cos(elevation),
                                -math.cos(yaw) * math.cos(elevation),
                                math.sin(elevation))) * distance
    camera.location = position
    camera.rotation_euler = (centre - position).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = camera
    return camera


def render(path, width=900, height=700, samples=48):
    scene = bpy.context.scene
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = path
    scene.render.film_transparent = False
    try:
        scene.eevee.taa_render_samples = samples
    except AttributeError:
        pass
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    return {"path": path, "bytes": os.path.getsize(path) if os.path.exists(path) else 0}


def views(objects, out_dir, name, angles=(35, 125, 215, 305), width=900, height=700):
    """Render a turntable. Four angles is enough to catch a shape that only
    works from the front, which is the most common way a model is wrong."""
    import mech_kit as kit

    size = kit.stats(*objects)["size"]
    studio()
    written = []
    for angle in angles:
        camera_for(objects, angle)
        written.append(render(os.path.join(out_dir, f"{name}_{angle:03d}.png"), width, height))
    return {"views": written, "size": size}
