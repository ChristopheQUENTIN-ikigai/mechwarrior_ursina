
from ursina import *
from noise import pnoise2
from config_loader import CFG
from systems.tex_gen import get_texture


class TerrainStreamer:

    def __init__(self):
        self.chunks = {}
        tcfg = CFG['terrain']
        self.chunk_size = tcfg['chunk_size']
        self.noise_scale = tcfg['noise_scale']
        self.noise_height = tcfg['noise_height']
        self.stream_radius = tcfg['stream_radius']
        self.grass_tex = get_texture('grass')

    def generate_chunk(self, cx, cz):
        size = self.chunk_size
        verts = []
        tris = []

        for z in range(size):
            for x in range(size):
                wx = cx * size + x
                wz = cz * size + z
                y = pnoise2(wx / self.noise_scale, wz / self.noise_scale) * self.noise_height
                verts.append(Vec3(wx, y, wz))

        def i(x, z):
            return x + z * size

        for z in range(size - 1):
            for x in range(size - 1):
                tris.append((i(x, z), i(x + 1, z), i(x, z + 1)))
                tris.append((i(x + 1, z), i(x + 1, z + 1), i(x, z + 1)))

        mesh = Mesh(vertices=verts, triangles=tris)
        Entity(model=mesh, texture=self.grass_tex, collider='mesh')

    def update_stream(self, pos):
        cx = int(pos.x / self.chunk_size)
        cz = int(pos.z / self.chunk_size)
        r = self.stream_radius

        for x in range(cx - r, cx + r + 1):
            for z in range(cz - r, cz + r + 1):
                if (x, z) not in self.chunks:
                    self.generate_chunk(x, z)
                    self.chunks[(x, z)] = True
