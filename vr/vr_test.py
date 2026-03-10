import bpy
import numpy as np
from bpy.app import handlers
from bpy.app.translations import pgettext_iface as iface_
from bpy.types import Panel, Operator, Gizmo, GizmoGroup
from mathutils import Vector, Quaternion, Matrix
import gpu

from utilities.console import console_print


class VRState:
    left_pos = Vector((0, 0, 0))
    right_pos = Vector((0, 0, 0))
    pickers = {}

    @classmethod
    def update_picker(self, key):
        import Qianyi_DP as qydp
        if key == '/user/hand/left':
            pos = self.left_pos
        else:
            pos = self.right_pos
        pos = np.array(pos)
        if key not in self.pickers:
            self.pickers[key] = -1
        if key in self.pickers:
            if self.pickers[key] == -1:
                self.pickers[key] = qydp.add_picker(pos)
                console_print("add_picker", key, self.pickers[key], pos)
            else:
                console_print("update_picker", key, self.pickers[key], pos)
                qydp.update_picker(self.pickers[key], pos)

    @classmethod
    def remove_picker(self, key):
        import Qianyi_DP as qydp
        if key in self.pickers:
            if self.pickers[key] != -1:
                qydp.remove_picker(self.pickers[key])
                console_print("remove_picker", key, self.pickers[key])
                self.pickers[key] = -1


class QYVR_GT_controller_indicator(Gizmo):
    bl_idname = "QYVR_GT_controller_indicator"

    aspect = 1.0, 1.0

    def draw(self, context):
        gpu.state.line_width_set(2.0)
        gpu.state.blend_set('ALPHA')

        # 绘制三个圆圈表示轴向
        self.draw_preset_circle(self.matrix_basis, axis='POS_X')
        self.draw_preset_circle(self.matrix_basis, axis='POS_Y')
        self.draw_preset_circle(self.matrix_basis, axis='POS_Z')


class QYVR_GGT_controllers(GizmoGroup):
    bl_idname = "QYVR_GGT_controllers"
    bl_label = "VR Controller Indicators"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'SCALE', 'VR_REDRAWS'}

    @classmethod
    def poll(cls, context):
        view3d = context.space_data
        return (bpy.types.XrSessionState.is_running(context) and
                not view3d.mirror_xr_session)

    def setup(self, context):
        # 创建左手gizmo
        gizmo = self.gizmos.new(QYVR_GT_controller_indicator.bl_idname)
        gizmo.color = (0.2, 0.6, 1.0)
        gizmo.alpha = 0.8
        self.left_gizmo = gizmo

        # 创建右手gizmo
        gizmo = self.gizmos.new(QYVR_GT_controller_indicator.bl_idname)
        gizmo.color = (1.0, 0.4, 0.2)
        gizmo.alpha = 0.8
        self.right_gizmo = gizmo

    def draw_prepare(self, context):
        wm = context.window_manager
        ss = wm.xr_session_state

        if not ss:
            return

        # 更新左手位置
        scale = 0.01
        try:
            loc = ss.controller_grip_location_get(context, 0)
            rot = ss.controller_grip_rotation_get(context, 0)
            VRState.left_pos = Vector(loc)

            rotmat = Matrix.Identity(3) * scale
            rotmat.rotate(Quaternion(Vector(rot)))
            rotmat.resize_4x4()
            transmat = Matrix.Translation(loc)
            self.left_gizmo.matrix_basis = transmat @ rotmat
        except:
            pass

        # 更新右手位置
        try:
            loc = ss.controller_grip_location_get(context, 1)
            rot = ss.controller_grip_rotation_get(context, 1)
            VRState.right_pos = Vector(loc)

            rotmat = Matrix.Identity(3) * scale
            rotmat.rotate(Quaternion(Vector(rot)))
            rotmat.resize_4x4()
            transmat = Matrix.Translation(loc)
            self.right_gizmo.matrix_basis = transmat @ rotmat
        except:
            pass


class QYVR_OT_trigger(Operator):
    bl_idname = "qy_vr.trigger"
    bl_label = "Trigger Press"
    bl_options = {'REGISTER'}

    def modal(self, context, event):
        if event.type != "XR_ACTION":
            return {"PASS_THROUGH"}

        xr = event.xr

        console_print(
            xr.action,
            event.value,
            xr.bimanual,
            xr.user_path,
            xr.user_path_other,
            xr.state[0],
            xr.state_other[0],
        )
        key = '/user/hand/left'
        other_key = '/user/hand/right'
        if xr.user_path != key:
            key, other_key = other_key, key

        if xr.state[0] > 0.5:
            VRState.update_picker(key)
        else:
            VRState.remove_picker(key)
        if xr.state_other[0] > 0.5:
            VRState.update_picker(other_key)
        else:
            VRState.remove_picker(other_key)


        return {"RUNNING_MODAL"}

    def invoke(self, context, event):
        qmyi = context.scene.qmyi
        if context.area.type != "VIEW_3D" or not qmyi.simulation.enable_simulation:
            return {"CANCELLED"}

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}


@handlers.persistent
def setup_vr_actions(context):
    context = bpy.context
    wm = context.window_manager
    ss = wm.xr_session_state

    if not ss:
        return

    am = ss.actionmaps.new(ss, "qy_vr", True)
    if not am:
        return

    ss.action_set_create(context, am)

    controller_grip = ""
    controller_aim = ""

    # Pose actions
    for name, is_grip, is_aim in [
        ("grip_pose", True, False),
        ("aim_pose", False, True),
    ]:
        ami = am.actionmap_items.new(name, True)
        ami.type = 'POSE'
        ami.user_paths.new("/user/hand/left")
        ami.user_paths.new("/user/hand/right")
        ami.pose_is_controller_grip = is_grip
        ami.pose_is_controller_aim = is_aim

        if is_grip:
            controller_grip = name
        if is_aim:
            controller_aim = name

        ss.action_create(context, am, ami)

        for profile, path in [
            ("/interaction_profiles/oculus/touch_controller", "/input/grip/pose"),
            ("/interaction_profiles/valve/index_controller", "/input/grip/pose"),
        ]:
            amb = ami.bindings.new(name, True)
            amb.profile = profile
            amb.component_paths.new(path)
            amb.component_paths.new(path)
            amb.pose_location = (0, 0, 0)
            amb.pose_rotation = (0, 0, 0)
            ss.action_binding_create(context, am, ami, amb)

    # Trigger
    ami = am.actionmap_items.new("trigger", True)
    ami.type = 'FLOAT'
    ami.user_paths.new("/user/hand/left")
    ami.user_paths.new("/user/hand/right")
    ami.op = "qy_vr.trigger"
    ami.op_mode = 'MODAL'
    ami.bimanual = True
    ss.action_create(context, am, ami)

    for profile, path in [
        ("/interaction_profiles/oculus/touch_controller", "/input/trigger/value"),
        # ("/interaction_profiles/valve/index_controller", "/input/trigger/value"),
    ]:
        amb = ami.bindings.new("trigger", True)
        amb.profile = profile
        amb.component_paths.new(path)
        amb.component_paths.new(path)
        amb.threshold = 0.05
        # amb.axis0_region = 'ANY'
        # amb.axis1_region = 'ANY'
        ss.action_binding_create(context, am, ami, amb)

    # 设置controller pose
    if controller_grip and controller_aim:
        ss.controller_pose_actions_set(context, "qy_vr", controller_grip, controller_aim)

    ss.active_action_set_set(context, "qy_vr")


class QYVR_PT_main(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "QYVR"
    bl_label = "VR"

    def draw(self, context):
        layout = self.layout

        is_running = bpy.types.XrSessionState.is_running(context)

        toggle_info = (
            (iface_("Start VR"), 'PLAY') if not is_running
            else (iface_("Stop VR"), 'SNAP_FACE')
        )
        layout.operator("wm.xr_session_toggle", text=toggle_info[0],
                        icon=toggle_info[1])

        # if is_running:
        #     layout.separator()
        #     col = layout.column()
        #     col.label(text=f"Left: {VRState.left_pos.x:.1f}, {VRState.left_pos.y:.1f}, {VRState.left_pos.z:.1f}")
        #     col.label(text=f"Right: {VRState.right_pos.x:.1f}, {VRState.right_pos.y:.1f}, {VRState.right_pos.z:.1f}")
        #


# =============================================================================
# 8. 注册
# =============================================================================

classes = (
    QYVR_GT_controller_indicator,
    QYVR_GGT_controllers,
    QYVR_OT_trigger,
    QYVR_PT_main,
)


def register():
    if not bpy.app.build_options.xr_openxr:
        return

    for cls in classes:
        bpy.utils.register_class(cls)

    handlers.xr_session_start_pre.append(setup_vr_actions)


def unregister():
    if setup_vr_actions in handlers.xr_session_start_pre:
        handlers.xr_session_start_pre.remove(setup_vr_actions)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
