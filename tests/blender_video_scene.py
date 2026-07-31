"""Blender scene construction and render for the synthetic video fixture.

Runs ONLY inside Blender's own Python interpreter -- `bpy` is not
importable elsewhere and is deliberately not a project dependency:

    blender-5.2 --background --python tests/blender_video_scene.py -- <config.json>

`generate_synthetic_video_fixture.py` invokes this; it is never run at
test time. The config JSON supplies texture paths, scene geometry, the
camera path, and output paths (see that module for the shape).

The scene is a TV: a lit 16:9 panel, a dark bezel carrying the printed
markers, and a room wall behind it.

  * 1 Blender unit == 1mm, matching markers.toml's screen-mm convention.
  * Everything faces -Y; the camera sits on the -Y side.
  * Screen-mm (0, 0) is the top-left of the ACTIVE PANEL, per
    markers.toml, so bezel markers have negative coordinates. The panel
    is centred on the TV face, which makes the mapping depend only on
    the panel size: world = (x_mm - w/2, 0, h/2 - y_mm).
  * Surfaces are emissive at differing strengths rather than lit by a
    lamp rig: that is what reproduces README's dominant failure mode --
    a bright screen beside dim paper in a dim room -- as an explicit,
    tunable number instead of an accident of lighting.
  * Ground truth per frame is the intersection of the camera's optical
    axis with the panel plane, computed from the evaluated camera
    transform -- never from cv2/findHomography, so it stays an
    independent check on what solve.py reconstructs.
"""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def screen_mm_to_world(x_mm: float, y_mm: float, screen_size_mm) -> Vector:
    width, height = screen_size_mm
    return Vector((x_mm - width / 2.0, 0.0, height / 2.0 - y_mm))


def world_to_screen_mm(world_x: float, world_z: float, screen_size_mm):
    width, height = screen_size_mm
    return (world_x + width / 2.0, height / 2.0 - world_z)


def _emissive_image_plane(name, image_path, width, height, location, strength):
    """A flat, axis-aligned quad in world XZ textured with an image.

    size=1.0 spans -0.5..+0.5, so scaling by (width, height) yields
    exactly width x height. Scaling a size=1 plane by N gives N, not 2N
    -- getting that backwards silently halves the scene, and it is
    invisible in a centred head-on view because scaling about the centre
    leaves the centre fixed.
    """
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=location)
    plane = bpy.context.active_object
    plane.name = name
    plane.scale = (width, height, 1.0)
    plane.rotation_euler = (math.radians(90), 0, 0)

    image = bpy.data.images.load(image_path)
    material = bpy.data.materials.new(f"{name}Material")
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    emission = tree.nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = strength
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    # Linear, not Closest: these textures are minified (a 1540px canvas
    # across ~700px of frame) and nearest-neighbour sampling aliases the
    # ArUco bit cells badly enough to stop most markers decoding.
    texture.interpolation = "Linear"
    tree.links.new(texture.outputs["Color"], emission.inputs["Color"])
    tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    plane.data.materials.append(material)
    return plane


def build_scene_geometry(config):
    screen_size_mm = config["screen_size_mm"]
    tv_size_mm = config["tv_size_mm"]
    room_size_mm = config["room_size_mm"]
    strengths = config["emission_strength"]

    # Bezel + printed markers. Behind the panel, which covers its middle.
    _emissive_image_plane(
        "TVFace",
        config["tv_face_texture"],
        tv_size_mm[0],
        tv_size_mm[1],
        (0.0, 0.0, 0.0),
        strengths["bezel"],
    )
    # The lit panel, 1mm proud of the bezel so it wins the depth test.
    _emissive_image_plane(
        "Panel",
        config["screen_texture"],
        screen_size_mm[0],
        screen_size_mm[1],
        (0.0, -1.0, 0.0),
        strengths["screen"],
    )
    # Room wall well behind the TV, so it parallaxes as the camera moves.
    _emissive_image_plane(
        "RoomWall",
        config["room_texture"],
        room_size_mm[0],
        room_size_mm[1],
        (0.0, config["room_distance_mm"], 0.0),
        strengths["room"],
    )


def _set_linear_interpolation(animated_object):
    # Blender 5.x layered actions: fcurves live under
    # action.layers[].strips[].channelbags[], not action.fcurves.
    action = animated_object.animation_data.action
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                for fcurve in channelbag.fcurves:
                    for point in fcurve.keyframe_points:
                        point.interpolation = "LINEAR"


def build_aim_target(keyframes, screen_size_mm):
    empty = bpy.data.objects.new("AimTarget", None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = 40.0
    bpy.context.scene.collection.objects.link(empty)

    for keyframe in keyframes:
        empty.location = screen_mm_to_world(
            keyframe["aim_screen_mm"][0],
            keyframe["aim_screen_mm"][1],
            screen_size_mm,
        )
        empty.keyframe_insert(data_path="location", frame=keyframe["frame"])

    _set_linear_interpolation(empty)
    return empty


def build_camera(aim_target, keyframes, config):
    camera_data = bpy.data.cameras.new("Camera")
    camera_data.lens_unit = "FOV"
    camera_data.angle = math.radians(config["camera_fov_deg"])
    # Principal point stays at the image centre. solve.py maps the image
    # centre through the inverse homography, and the ground truth below
    # traces the optical axis -- both assume no lens shift, so this must
    # stay zero even though Blender happily allows shifting it.
    camera_data.shift_x = 0.0
    camera_data.shift_y = 0.0
    # Defaults clip at 100 units; at mm scale the TV sits ~3000 away.
    camera_data.clip_start = 1.0
    camera_data.clip_end = 100000.0

    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)

    for keyframe in keyframes:
        camera.location = Vector(keyframe["camera_position"])
        camera.keyframe_insert(data_path="location", frame=keyframe["frame"])
    _set_linear_interpolation(camera)

    # A TRACK_TO constraint rather than baked rotations, so the saved
    # .blend opens as an editable, obviously animated scene.
    track = camera.constraints.new(type="TRACK_TO")
    track.target = aim_target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    bpy.context.scene.camera = camera
    return camera


def optical_axis_hit_screen_mm(camera, screen_size_mm):
    """Ground truth: where the camera's optical axis meets the panel plane.

    Derived from the evaluated camera transform alone -- no homography,
    no cv2 -- so it is an independent reference for what solve.py
    reconstructs from detected corners.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    matrix_world = camera.evaluated_get(depsgraph).matrix_world
    position = matrix_world.translation
    forward = (matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()

    if abs(forward.y) < 1e-9:
        raise RuntimeError("camera optical axis is parallel to the screen plane")

    distance = -position.y / forward.y
    if distance <= 0.0:
        raise RuntimeError("camera optical axis points away from the screen plane")

    hit = position + forward * distance
    return world_to_screen_mm(hit.x, hit.z, screen_size_mm)


def main() -> None:
    config_path = sys.argv[sys.argv.index("--") + 1]
    config = json.loads(Path(config_path).read_text())
    screen_size_mm = config["screen_size_mm"]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.resolution_x = config["resolution"][0]
    scene.render.resolution_y = config["resolution"][1]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.frame_start = 1
    scene.frame_end = config["frame_count"]
    # Standard, not the default filmic/AgX view transform: those tone-map
    # and desaturate, which would silently rewrite the screen-vs-paper
    # brightness ratio the emission strengths are chosen to express.
    scene.view_settings.view_transform = "Standard"
    # Eevee over Cycles: these are unlit emissive planes, so the engines
    # agree on the projective geometry that matters here, and Eevee
    # renders it far faster headless.
    engines = [
        item.identifier
        for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
    ]
    scene.render.engine = (
        "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else engines[0]
    )

    build_scene_geometry(config)
    aim_target = build_aim_target(config["keyframes"], screen_size_mm)
    camera = build_camera(aim_target, config["keyframes"], config)

    raw_dir = Path(config["raw_dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)

    ground_truth = []
    for frame in range(1, config["frame_count"] + 1):
        scene.frame_set(frame)
        aim_screen_mm = optical_axis_hit_screen_mm(camera, screen_size_mm)
        scene.render.filepath = str(raw_dir / f"frame_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
        ground_truth.append(
            {"frame": frame, "aim_point_screen_mm": list(aim_screen_mm)}
        )

    Path(config["ground_truth_path"]).write_text(json.dumps(ground_truth, indent=2))

    # Saved so the scene can be opened and inspected by hand, rather
    # than existing only as whatever this script happens to construct.
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=config["blend_path"])


if __name__ == "__main__":
    main()
