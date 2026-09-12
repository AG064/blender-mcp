---
name: blender-mcp
description: Model in Blender from an agent — build geometry, assign materials, render previews, and export glTF for a game engine. Use when asked to create or change 3D models, props, characters or environments, or to get models out of Blender and into a project.
---

# Modelling in Blender

You have an `aurum-blender` MCP server. It drives a running Blender over a
loopback socket, and it exposes 25 tools. Read `blender_status` first: it tells
you whether Blender is reachable, which version it is, and whether the open file
has unsaved work that a careless step would throw away.

## The shape of the work

Model in **metres**, at **game scale**, with the **origin at the feet** and
**+Z up**. A three-metre crate is `size: 3`. A six-metre mech is six metres
tall. Getting this wrong is the most expensive mistake available here, because
everything downstream — colliders, camera framing, animation — assumes it.

Build from primitives, then refine:

1. **Block the silhouette** with `blender_object_create`. Cubes and cylinders at
   exact sizes, positioned to read as the thing from across the room. Do not
   detail a shape that does not read yet.
2. **Cut and combine** with `blender_mesh_boolean`. Panels recessed, hulls
   pierced, joints exposed. `objects[0]` is the target; the rest are cutters and
   are consumed.
3. **Break the edges** with `blender_mesh_bevel`, `width` around 1–2% of the
   object's smallest dimension, 2–3 segments. This is the single change that
   most makes a box read as a manufactured part: a real edge catches light.
4. **Repeat** with `blender_mesh_modifier` — `MIRROR` for symmetry, `ARRAY` for
   rows of vents, `SOLIDIFY` for plate.
5. **Surface it** with `blender_material_new` and `blender_material_assign`.
6. **Look at it** with `blender_capture`. Do this often. You cannot model what
   you have not seen, and the render is how you see it.
7. **Export** with `blender_export_gltf` using `GLB`.

## What good looks like

- **Silhouette first.** If it does not read as the object in flat black, no
  amount of surface detail will save it.
- **Nothing is a plain box.** Every mass has a reason: thicker where the load
  is, narrower where it moves, cut away where something passes through.
- **Greebles are cheap and they are not clutter.** A few small extrusions —
  handles, vents, bolts — give the eye somewhere to land and give the model
  scale. A dozen per machine, placed with intent.
- **Material separates forms.** A model in one flat colour loses its own
  geometry. Two or three materials with different roughness reads as a
  machine; a dozen reads as noise.
- **Check from three angles.** Front, side, three-quarter. A shape that only
  works from one is a shape that will embarrass you the moment the camera
  moves.

## Working practice

- **`blender_execute` is the escape hatch** and you should use it freely for
  anything the named tools do not cover: reading a bounding box, selecting by
  name pattern, checking a normals direction, counting polygons. Bind what you
  want back to `result`.
- **`blender_new_scene` refuses to discard unsaved work** unless you pass
  `discard_changes`. That refusal is the feature. Do not pass it reflexively.
- **Save when a stage is right** — `blender_save` with a path. Blender holds
  unsaved work in memory and an agent that has not saved has not finished.
- **Export only what you mean to ship.** Pass `objects` to `blender_export_gltf`
  rather than exporting the whole file, and `blender_object_apply_transform`
  first so the exported nodes have identity transforms and the engine has
  nothing to undo.
- **Report polycount.** `blender_execute` with `result = sum(len(o.data.polygons)
  for o in bpy.data.objects if o.type == 'MESH')`. A game model that arrives at
  200k triangles is a bug report, not an asset.

## When something is refused

The add-on raises rather than guessing. A refusal names what was wrong — no
object by that name, nothing selected and none named, unsaved work in the way.
Read it and fix the call. Retrying the same call unchanged will produce the same
refusal.

If `blender_status` says Blender is unreachable, call `blender_launch`. If that
reports that Blender started but never opened the bridge, the add-on is not
enabled — tell the user to press **Start Bridge** in the *Aurum MCP* sidebar
panel, rather than trying to work around it.
