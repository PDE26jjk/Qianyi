from gpu.types import GPUShader

vertex_shader = '''
 uniform mat4 ModelMatrix;
uniform mat4 ModelViewProjectionMatrix; // Set by blender

in vec2 pos;

void main()
{
    gl_Position = ModelViewProjectionMatrix * ModelMatrix * vec4(pos, 0.0, 1.0);
}
'''

fragment_shader = '''
uniform vec4 color;

out vec4 fragColor;

void main()
{
    fragColor = color;
}
'''


class BaseRenderer:
    shader = None

    def __init__(self):
        if self.shader is None:
            self.shader = GPUShader(vertex_shader, fragment_shader)