bl_info = {
    "name": "Camera & Lights Controller",
    "author": "OpenAI Codex",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > Camera & Lights",
    "description": "Per-camera lighting and frame linkage for storyboard-style shots",
    "category": "3D View",
}

import bpy
from bpy.app.handlers import persistent

_CLC_SYNCING = False


def camera_poll(_, obj):
    return obj is not None and obj.type == "CAMERA"


def _iter_scene_lights(scene):
    if not scene:
        return []
    return [obj for obj in scene.objects if obj and obj.type == "LIGHT"]


def _iter_scene_cameras(scene):
    if not scene:
        return []
    return [obj for obj in scene.objects if obj and obj.type == "CAMERA"]


def _cleanup_camera_lights(camera_obj):
    if not camera_obj:
        return
    remove_indices = [i for i, item in enumerate(camera_obj.clc_lights) if item.light is None]
    for index in reversed(remove_indices):
        camera_obj.clc_lights.remove(index)


def _assigned_lights(camera_obj):
    if not camera_obj:
        return set()
    return {item.light for item in camera_obj.clc_lights if item.light}


def apply_lights_for_camera(scene, camera_obj):
    if not scene or not camera_obj:
        return
    _cleanup_camera_lights(camera_obj)
    assigned = _assigned_lights(camera_obj)
    for obj in scene.objects:
        if obj.type != "LIGHT":
            continue
        is_assigned = obj in assigned
        obj.hide_viewport = not is_assigned
        obj.hide_render = not is_assigned


def _sync_frame_from_camera(scene, camera_obj):
    if not scene or not camera_obj:
        return
    if camera_obj.clc_use_frame:
        scene.frame_current = max(1, int(camera_obj.clc_frame))


def on_scene_camera_selected(scene, camera_obj):
    global _CLC_SYNCING
    if _CLC_SYNCING:
        return
    if not scene or not camera_obj:
        return
    _CLC_SYNCING = True
    try:
        if scene.camera != camera_obj:
            scene.camera = camera_obj
        scene.clc_last_camera_name = camera_obj.name
        # Keep the UI dropdown in sync when camera changes via viewport/scene.
        if getattr(scene, "clc_camera_enum", "") != camera_obj.name:
            scene.clc_camera_enum = camera_obj.name
        apply_lights_for_camera(scene, camera_obj)
        _sync_frame_from_camera(scene, camera_obj)
    finally:
        _CLC_SYNCING = False


def on_camera_prop_update(self, context):
    scene = context.scene
    camera_obj = scene.clc_active_camera
    on_scene_camera_selected(scene, camera_obj)


def _camera_enum_items(self, context):
    scene = getattr(context, "scene", None)
    items = []
    cameras = _iter_scene_cameras(scene)
    for idx, cam in enumerate(cameras):
        # identifier, name, description, icon, number
        items.append((cam.name, cam.name, "Camera", "CAMERA_DATA", idx))
    if not items:
        items.append(("", "<No Cameras>", "No camera objects found", "ERROR", 0))
    return items


def on_camera_enum_update(self, context):
    scene = context.scene
    cam_name = scene.clc_camera_enum
    cam_obj = scene.objects.get(cam_name) if cam_name else None
    if cam_obj and cam_obj.type == "CAMERA":
        scene.clc_active_camera = cam_obj


@persistent
def clc_depsgraph_update(scene, depsgraph):
    if not scene:
        return
    camera_obj = scene.camera
    if not camera_obj or camera_obj.type != "CAMERA":
        return
    if scene.clc_last_camera_name != camera_obj.name:
        scene.clc_active_camera = camera_obj
        on_scene_camera_selected(scene, camera_obj)


@persistent
def clc_render_pre(scene):
    if not scene:
        return
    camera_obj = scene.camera
    if camera_obj and camera_obj.type == "CAMERA":
        apply_lights_for_camera(scene, camera_obj)


class CLC_LightItem(bpy.types.PropertyGroup):
    light: bpy.props.PointerProperty(type=bpy.types.Object)


class CLC_OT_toggle_light_assignment(bpy.types.Operator):
    bl_idname = "clc.toggle_light_assignment"
    bl_label = "Toggle Light Assignment"
    bl_options = {"UNDO"}

    light_name: bpy.props.StringProperty()

    def execute(self, context):
        scene = context.scene
        camera_obj = scene.clc_active_camera
        if not camera_obj:
            return {"CANCELLED"}
        light_obj = scene.objects.get(self.light_name)
        if not light_obj or light_obj.type != "LIGHT":
            return {"CANCELLED"}

        for i, item in enumerate(camera_obj.clc_lights):
            if item.light == light_obj:
                camera_obj.clc_lights.remove(i)
                apply_lights_for_camera(scene, camera_obj)
                return {"FINISHED"}

        new_item = camera_obj.clc_lights.add()
        new_item.light = light_obj
        apply_lights_for_camera(scene, camera_obj)
        return {"FINISHED"}


class CLC_OT_assign_selected_lights(bpy.types.Operator):
    bl_idname = "clc.assign_selected_lights"
    bl_label = "Assign Selected Lights"
    bl_options = {"UNDO"}

    def execute(self, context):
        scene = context.scene
        camera_obj = scene.clc_active_camera
        if not camera_obj:
            return {"CANCELLED"}
        assigned = _assigned_lights(camera_obj)
        for obj in context.selected_objects:
            if obj.type != "LIGHT":
                continue
            if obj in assigned:
                continue
            item = camera_obj.clc_lights.add()
            item.light = obj
        apply_lights_for_camera(scene, camera_obj)
        return {"FINISHED"}


class CLC_OT_clear_camera_lights(bpy.types.Operator):
    bl_idname = "clc.clear_camera_lights"
    bl_label = "Clear Camera Lights"
    bl_options = {"UNDO"}

    def execute(self, context):
        scene = context.scene
        camera_obj = scene.clc_active_camera
        if not camera_obj:
            return {"CANCELLED"}
        camera_obj.clc_lights.clear()
        apply_lights_for_camera(scene, camera_obj)
        return {"FINISHED"}


class CLC_OT_assign_all_lights(bpy.types.Operator):
    bl_idname = "clc.assign_all_lights"
    bl_label = "Assign All Lights"
    bl_options = {"UNDO"}

    def execute(self, context):
        scene = context.scene
        camera_obj = scene.clc_active_camera
        if not camera_obj:
            return {"CANCELLED"}

        assigned = _assigned_lights(camera_obj)
        for obj in _iter_scene_lights(scene):
            if obj in assigned:
                continue
            item = camera_obj.clc_lights.add()
            item.light = obj
        apply_lights_for_camera(scene, camera_obj)
        return {"FINISHED"}


class CLC_OT_select_object_in_scene(bpy.types.Operator):
    bl_idname = "clc.select_object_in_scene"
    bl_label = "Select Object"
    bl_options = {"UNDO"}

    object_name: bpy.props.StringProperty()

    def execute(self, context):
        scene = context.scene
        obj = scene.objects.get(self.object_name) if scene else None
        if not obj:
            return {"CANCELLED"}

        # Make selection explicit and predictable.
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {"FINISHED"}


class CLC_OT_rename_light(bpy.types.Operator):
    bl_idname = "clc.rename_light"
    bl_label = "Rename Light"
    bl_options = {"UNDO"}

    light_name: bpy.props.StringProperty()
    new_name: bpy.props.StringProperty(name="New Name", default="")

    def invoke(self, context, event):
        scene = context.scene
        light_obj = scene.objects.get(self.light_name) if scene else None
        if not light_obj or light_obj.type != "LIGHT":
            return {"CANCELLED"}
        self.new_name = light_obj.name
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        scene = context.scene
        light_obj = scene.objects.get(self.light_name) if scene else None
        if not light_obj or light_obj.type != "LIGHT":
            return {"CANCELLED"}
        if not self.new_name or self.new_name.strip() == "":
            return {"CANCELLED"}
        new_name = self.new_name.strip()
        if new_name == light_obj.name:
            return {"CANCELLED"}
        # Check if name already exists
        if new_name in scene.objects:
            self.report({"ERROR"}, f"Name '{new_name}' already exists")
            return {"CANCELLED"}
        light_obj.name = new_name
        return {"FINISHED"}


class CLC_OT_rename_camera(bpy.types.Operator):
    bl_idname = "clc.rename_camera"
    bl_label = "Rename Camera"
    bl_options = {"UNDO"}

    camera_name: bpy.props.StringProperty()
    new_name: bpy.props.StringProperty(name="New Name", default="")

    def invoke(self, context, event):
        scene = context.scene
        camera_obj = scene.objects.get(self.camera_name) if scene else None
        if not camera_obj or camera_obj.type != "CAMERA":
            return {"CANCELLED"}
        self.new_name = camera_obj.name
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        scene = context.scene
        camera_obj = scene.objects.get(self.camera_name) if scene else None
        if not camera_obj or camera_obj.type != "CAMERA":
            return {"CANCELLED"}
        if not self.new_name or self.new_name.strip() == "":
            return {"CANCELLED"}
        new_name = self.new_name.strip()
        if new_name == camera_obj.name:
            return {"CANCELLED"}
        # Check if name already exists
        if new_name in scene.objects:
            self.report({"ERROR"}, f"Name '{new_name}' already exists")
            return {"CANCELLED"}
        old_name = camera_obj.name
        camera_obj.name = new_name
        # Update enum if this was the active camera
        if scene.clc_active_camera == camera_obj:
            scene.clc_camera_enum = new_name
        return {"FINISHED"}


class CLC_OT_open_camera_window(bpy.types.Operator):
    bl_idname = "clc.open_camera_window"
    bl_label = "Open Camera Window"
    bl_options = {"UNDO"}

    def execute(self, context):
        scene = context.scene
        camera_obj = scene.clc_active_camera
        if not camera_obj:
            return {"CANCELLED"}

        bpy.ops.wm.window_new()
        new_window = context.window_manager.windows[-1]
        area = next((a for a in new_window.screen.areas if a.type == "VIEW_3D"), None)
        if not area:
            return {"CANCELLED"}
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        space = area.spaces.active
        space.region_3d.view_perspective = "CAMERA"
        with context.temp_override(window=new_window, area=area, region=region):
            bpy.ops.view3d.view_camera()
        return {"FINISHED"}


class CLC_OT_set_camera_frame_from_current(bpy.types.Operator):
    bl_idname = "clc.set_camera_frame_from_current"
    bl_label = "Set Camera Frame From Current"
    bl_options = {"UNDO"}

    def execute(self, context):
        scene = context.scene
        camera_obj = scene.clc_active_camera
        if not camera_obj:
            return {"CANCELLED"}
        camera_obj.clc_frame = max(1, scene.frame_current)
        camera_obj.clc_use_frame = True
        return {"FINISHED"}


class CLC_OT_jump_to_camera_frame(bpy.types.Operator):
    bl_idname = "clc.jump_to_camera_frame"
    bl_label = "Jump To Camera Frame"
    bl_options = {"UNDO"}

    def execute(self, context):
        scene = context.scene
        camera_obj = scene.clc_active_camera
        if not camera_obj:
            return {"CANCELLED"}
        if camera_obj.clc_use_frame:
            scene.frame_current = max(1, int(camera_obj.clc_frame))
        return {"FINISHED"}


class CLC_OT_insert_keyframes(bpy.types.Operator):
    bl_idname = "clc.insert_keyframes"
    bl_label = "Insert Keyframes (Selected Objects)"
    bl_options = {"UNDO"}

    def execute(self, context):
        selected = context.selected_objects
        if not selected:
            return {"CANCELLED"}
        for obj in selected:
            obj.keyframe_insert(data_path="location")
            if obj.rotation_mode == "QUATERNION":
                obj.keyframe_insert(data_path="rotation_quaternion")
            else:
                obj.keyframe_insert(data_path="rotation_euler")
            obj.keyframe_insert(data_path="scale")

            if obj.data and hasattr(obj.data, "shape_keys") and obj.data.shape_keys:
                for key_block in obj.data.shape_keys.key_blocks:
                    key_block.keyframe_insert(data_path="value")
        return {"FINISHED"}


class CLC_PT_main_panel(bpy.types.Panel):
    bl_label = "Camera & Lights"
    bl_idname = "CLC_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Camera & Lights"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        camera_obj = scene.clc_active_camera

        box = layout.box()
        box.label(text="Camera")
        row = box.row(align=True)
        row.prop(scene, "clc_camera_enum", text="")
        if camera_obj:
            select_op = row.operator("clc.select_object_in_scene", text="", icon="RESTRICT_SELECT_OFF")
            select_op.object_name = camera_obj.name
            rename_op = row.operator("clc.rename_camera", text="", icon="OUTLINER_OB_FONT")
            rename_op.camera_name = camera_obj.name
        row = box.row(align=True)
        row.operator("clc.open_camera_window", text="Open Camera Window", icon="CAMERA_DATA")
        row.operator("clc.insert_keyframes", text="Insert Keyframes", icon="KEY_HLT")

        frame_box = layout.box()
        frame_box.label(text="Camera Frame")
        if camera_obj:
            row = frame_box.row(align=True)
            row.prop(camera_obj, "clc_use_frame", text="Use Frame")
            row.prop(camera_obj, "clc_frame", text="Frame")
            row = frame_box.row(align=True)
            row.operator("clc.set_camera_frame_from_current", text="Set From Current")
            row.operator("clc.jump_to_camera_frame", text="Jump To Frame")
        else:
            frame_box.label(text="Select a camera to set frame")

        lights_box = layout.box()
        lights_box.label(text="Lights For Camera")
        if not camera_obj:
            lights_box.label(text="Select a camera to assign lights")
            return

        _cleanup_camera_lights(camera_obj)
        assigned_now = _assigned_lights(camera_obj)
        for obj in _iter_scene_lights(scene):
            is_assigned = obj in assigned_now
            row = lights_box.row(align=True)

            # Checkbox only (no text) so clicking the name won't do anything to selection.
            icon = "CHECKBOX_HLT" if is_assigned else "CHECKBOX_DEHLT"
            op = row.operator("clc.toggle_light_assignment", text="", icon=icon, emboss=True)
            op.light_name = obj.name

            # Non-clickable label for the name.
            row.label(text=obj.name, icon="LIGHT")

            # Explicit "select in scene" arrow/button.
            sel = row.operator("clc.select_object_in_scene", text="", icon="RESTRICT_SELECT_OFF")
            sel.object_name = obj.name

            # Rename button (Aa icon).
            rename_op = row.operator("clc.rename_light", text="", icon="OUTLINER_OB_FONT")
            rename_op.light_name = obj.name

        row = lights_box.row(align=True)
        row.operator("clc.assign_all_lights", text="Select All", icon="CHECKMARK")
        row.operator("clc.assign_selected_lights", text="Assign Selected")
        row.operator("clc.clear_camera_lights", text="Clear")


classes = (
    CLC_LightItem,
    CLC_OT_toggle_light_assignment,
    CLC_OT_assign_selected_lights,
    CLC_OT_clear_camera_lights,
    CLC_OT_assign_all_lights,
    CLC_OT_select_object_in_scene,
    CLC_OT_rename_light,
    CLC_OT_rename_camera,
    CLC_OT_open_camera_window,
    CLC_OT_set_camera_frame_from_current,
    CLC_OT_jump_to_camera_frame,
    CLC_OT_insert_keyframes,
    CLC_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.clc_active_camera = bpy.props.PointerProperty(
        type=bpy.types.Object,
        poll=camera_poll,
        update=on_camera_prop_update,
    )
    bpy.types.Scene.clc_last_camera_name = bpy.props.StringProperty(default="")
    bpy.types.Scene.clc_camera_enum = bpy.props.EnumProperty(
        name="Cameras",
        description="Choose the active camera",
        items=_camera_enum_items,
        update=on_camera_enum_update,
    )

    bpy.types.Object.clc_lights = bpy.props.CollectionProperty(type=CLC_LightItem)
    bpy.types.Object.clc_frame = bpy.props.IntProperty(min=1, default=1)
    bpy.types.Object.clc_use_frame = bpy.props.BoolProperty(default=False)

    if clc_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(clc_depsgraph_update)
    if clc_render_pre not in bpy.app.handlers.render_pre:
        bpy.app.handlers.render_pre.append(clc_render_pre)


def unregister():
    if clc_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(clc_depsgraph_update)
    if clc_render_pre in bpy.app.handlers.render_pre:
        bpy.app.handlers.render_pre.remove(clc_render_pre)

    del bpy.types.Object.clc_lights
    del bpy.types.Object.clc_frame
    del bpy.types.Object.clc_use_frame
    del bpy.types.Scene.clc_active_camera
    del bpy.types.Scene.clc_last_camera_name
    del bpy.types.Scene.clc_camera_enum

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
