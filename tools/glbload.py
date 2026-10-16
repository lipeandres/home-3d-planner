# Copyright 2026 Felipe Navarro Murcia. Licensed under the Apache License, Version 2.0 (see LICENSE and NOTICE).
"""Minimal GLB reader: returns triangles per story (scene-graph groups) as numpy arrays, world space, meters."""
import json, struct
import numpy as np

CT = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}

def _accessor(j, binb, i):
    a = j['accessors'][i]; bv = j['bufferViews'][a['bufferView']]
    n = NC[a['type']]; dt = CT[a['componentType']]
    off = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    return np.frombuffer(binb, dtype=dt, count=a['count'] * n, offset=off).reshape(a['count'], n)

def _local(n):
    m = np.eye(4)
    if 'matrix' in n: return np.array(n['matrix']).reshape(4, 4).T
    if 'scale' in n: m = m @ np.diag(list(n['scale']) + [1])
    if 'rotation' in n:
        x, y, z, w = n['rotation']
        r = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)], [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
        m2 = np.eye(4); m2[:3, :3] = r; m = m2 @ m
    if 'translation' in n:
        m2 = np.eye(4); m2[:3, 3] = n['translation']; m = m2 @ m
    return m

def load_stories(path):
    b = open(path, 'rb').read()
    cl, _ = struct.unpack('<I4s', b[12:20]); j = json.loads(b[20:20 + cl])
    off = 20 + cl; bl, _ = struct.unpack('<I4s', b[off:off + 8]); binb = b[off + 8: off + 8 + bl]
    nodes = j['nodes']; stories = {}
    def walk(i, M, story):
        n = nodes[i]; M = M @ _local(n)
        if n.get('name', '').startswith('Story'): story = n['name']
        if 'mesh' in n:
            for p in j['meshes'][n['mesh']]['primitives']:
                pos = _accessor(j, binb, p['attributes']['POSITION']).astype(np.float64)
                idx = _accessor(j, binb, p['indices']).reshape(-1).astype(np.int64) if 'indices' in p else np.arange(len(pos))
                pos = (np.c_[pos, np.ones(len(pos))] @ M.T)[:, :3]
                stories.setdefault(story or 'all', []).append(pos[idx].reshape(-1, 3, 3))
        for c in n.get('children', []): walk(c, M, story)
    for r in j['scenes'][0]['nodes']: walk(r, np.eye(4), None)
    return {k: np.concatenate(v) for k, v in stories.items()}
