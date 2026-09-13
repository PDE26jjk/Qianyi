from .utilities.pdb_mapper import PDBToEXEMapper
import ctypes
import gpu
from ctypes import c_void_p, c_int, wintypes


def get_blender_exe_path():
    """返回 blender.exe 的完整路径"""
    # 获取主模块（blender.exe）的文件名
    buf = (wintypes.WCHAR * 260)()
    size = ctypes.windll.kernel32.GetModuleFileNameW(None, buf, 260)
    if size == 0:
        # 备用方案：通过已知模块名 "blender.exe" 获取
        h = ctypes.windll.kernel32.GetModuleHandleW("blender.exe")
        if h:
            size = ctypes.windll.kernel32.GetModuleFileNameW(h, buf, 260)
    return buf[:size] if size else ""


GPU_BUILTIN_SHADER_ENUM = {
    "gpu_shader_text": 0,
    "gpu_shader_keyframe_shape": 1,
    "gpu_shader_simple_lighting": 2,
    "gpu_shader_icon": 3,
    "gpu_shader_2d_image_rect_color": 4,
    "gpu_shader_2d_image_desaturate_color": 5,
    "gpu_shader_icon_multi": 6,
    "gpu_shader_2d_checker": 7,
    "gpu_shader_2d_diag_stripes": 8,
    "gpu_shader_3d_line_dashed_uniform_color": 9,
    "gpu_shader_3d_depth_only": 10,
    "gpu_shader_2d_image_overlays_merge": 11,
    "gpu_shader_2d_image_overlays_stereo_merge": 12,
    "gpu_shader_2d_image_shuffle_color": 13,
    "gpu_shader_gpencil_stroke": 14,
    "gpu_shader_2d_area_borders": 15,
    "gpu_shader_2d_widget_base": 16,
    "gpu_shader_2d_widget_base_inst": 17,
    "gpu_shader_2d_widget_shadow": 18,
    "gpu_shader_2d_node_socket": 19,
    "gpu_shader_2d_node_socket_inst": 20,
    "gpu_shader_2d_nodelink": 21,
    "gpu_shader_2d_nodelink_inst": 22,

    "gpu_shader_3d_point_varying_size_varying_color": 23,
    "gpu_shader_2d_point_uniform_size_uniform_color_aa": 24,
    "gpu_shader_3d_point_uniform_size_uniform_color_aa": 25,
    "gpu_shader_2d_point_uniform_size_uniform_color_outline_aa": 26,

    "gpu_shader_3d_clipped_uniform_color": 27,
    "gpu_shader_3d_polyline_clipped_uniform_color": 28,

    "gpu_shader_sequencer_strips": 29,
    "gpu_shader_sequencer_thumbs": 30,

    "gpu_shader_indexbuf_points": 31,
    "gpu_shader_indexbuf_lines": 32,
    "gpu_shader_indexbuf_tris": 33,

    "gpu_shader_3d_flat_color": 34,
    "gpu_shader_3d_polyline_flat_color": 35,
    "gpu_shader_3d_point_flat_color": 36,

    "gpu_shader_3d_smooth_color": 37,
    "gpu_shader_3d_polyline_smooth_color": 38,

    "gpu_shader_3d_uniform_color": 39,
    "gpu_shader_3d_polyline_uniform_color": 40,
    "gpu_shader_3d_point_uniform_color": 41,

    "gpu_shader_3d_image": 42,
    "gpu_shader_3d_image_color": 43,
}


def WIN_HACK_get_builtin_shader(shader_name, config='DEFAULT'):
    kernel32 = ctypes.windll.kernel32
    GetModuleHandleW = kernel32.GetModuleHandleW
    GetModuleHandleW.restype = ctypes.c_void_p
    GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    h_blender = GetModuleHandleW('blender.exe')
    exe_path = get_blender_exe_path()
    pdb_path = exe_path.replace("blender.exe", "blender.pdb")
    mapper = PDBToEXEMapper(pdb_path, exe_path)
    mapper.load_files()
    func_name = "GPU_shader_get_builtin_shader_with_config"
    result = mapper.find_function(func_name)
    func_va = h_blender + result['exe_rva']
    prototype = ctypes.CFUNCTYPE(c_void_p, c_int, c_int)

    callable_func = prototype(func_va)
    if shader_name not in GPU_BUILTIN_SHADER_ENUM:
        raise Exception(f"Shader {shader_name} not supported")
    builtin_shader = GPU_BUILTIN_SHADER_ENUM[shader_name]
    shader_config = 0 if config == 'DEFAULT' else 1

    shader_ptr = callable_func(builtin_shader, shader_config)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    obj_address = id(shader)  # PyObject * 的地址
    ptr_field = ctypes.c_void_p.from_address(obj_address + 24)
    ptr_field.value = shader_ptr
    return shader
