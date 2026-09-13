import struct

import gpu
import numpy as np
from gpu.types import GPUShader
from gpu.types import GPUShaderCreateInfo

vertex_shader = '''
// layout(location = 0) in vec2 pos;
// uniform mat4 ModelMatrix;
// uniform mat4 ModelViewProjectionMatrix; // Set by blender

void main()
{
    gl_Position = ModelViewProjectionMatrix * ubo_buf.ModelMatrix * vec4(pos, 0.0, 1.0);
}
'''

fragment_shader = '''
// uniform vec4 color;

// out vec4 fragColor;

void main()
{
    fragColor = color;
}
'''


class BaseRenderer:
    shader = None
    ubo = None

    def __init__(self):
        if self.shader is None:
            # self.shader = GPUShader(vertex_shader, fragment_shader)
            self.shader = self._create_shader()
            self.ubo = gpu.types.GPUUniformBuf(struct.pack('16f', *([0.0] * 16)))

    def _create_shader(self):
        # 使用GPUShaderCreateInfo构建着色器
        shader_info = GPUShaderCreateInfo()

        # 添加输入输出定义
        shader_info.vertex_in(0, 'VEC2', "pos")
        shader_info.fragment_out(0, 'VEC4', "fragColor")
        typedef_source = '''
                struct MyUniforms {
                    mat4 ModelMatrix;
                };
                '''
        shader_info.typedef_source(typedef_source)
        shader_info.uniform_buf(0, "MyUniforms", "ubo_buf")
        shader_info.push_constant('MAT4', "ModelViewProjectionMatrix")
        # shader_info.push_constant('MAT4', "ModelMatrix")
        shader_info.push_constant("VEC4", "color")

        # 设置着色器源代码
        shader_info.vertex_source(vertex_shader)
        shader_info.fragment_source(fragment_shader)

        # 创建着色器
        return gpu.shader.create_from_info(shader_info)

    def update_model_matrix(self, matrix):
        """辅助方法：供子类调用，更新 UBO 中的 ModelMatrix"""
        # 展平矩阵 (Blender矩阵按列主序展开)
        # model_flat = [val for col in matrix for val in col]
        # data = struct.pack('16f', *model_flat)

        # 更新并绑定 UBO
        self.ubo.update(np.array(matrix, dtype=np.float32).T.tobytes())
        self.shader.uniform_block("ubo_buf", self.ubo)
