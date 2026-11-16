"""Parts as manifold meshes, for the geometry checks.

The checks run on meshes rather than on OpenCascade solids: manifold
booleans are fast and robust over dozens of assemblies, and the same code
then checks a third-party skin that only exists as an STL.
"""

from __future__ import annotations

from pathlib import Path

import manifold3d as m3
import numpy as np
from build123d import Shape

# Chord tolerance of the tessellation, in mm. Gaps measured on curved
# surfaces are good to about this much.
TOLERANCE = 0.05


class MeshError(ValueError):
    pass


def _weld(vertices: np.ndarray, triangles: np.ndarray) -> m3.Manifold:
    # OpenCascade tessellates face by face, so a vertex on a shared edge
    # appears once per face. The edges are discretised once, so the copies
    # are bit-identical: weld them on a fine grid.
    key = np.round(vertices / 1e-6).astype(np.int64)
    uniq, inverse = np.unique(key, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    merged = np.zeros((len(uniq), 3))
    merged[inverse] = vertices
    tris = inverse[triangles]
    keep = (
        (tris[:, 0] != tris[:, 1])
        & (tris[:, 1] != tris[:, 2])
        & (tris[:, 0] != tris[:, 2])
    )
    mesh = m3.Mesh(
        vert_properties=merged.astype(np.float32),
        tri_verts=tris[keep].astype(np.uint32),
    )
    return m3.Manifold(mesh)


def to_manifold(shape: Shape, tolerance: float = TOLERANCE) -> m3.Manifold:
    """`shape` as a closed manifold mesh, or MeshError if it is not closed."""
    verts, tris = shape.tessellate(tolerance, 0.2)
    if not tris:
        return m3.Manifold()
    vertices = np.array([[p.X, p.Y, p.Z] for p in verts], dtype=np.float64)
    triangles = np.array(tris, dtype=np.int64)
    man = _weld(vertices, triangles)
    if man.status() != m3.Error.NoError:
        raise MeshError(f"not a closed solid ({man.status().name})")
    return man


def from_arrays(vertices: np.ndarray, triangles: np.ndarray) -> m3.Manifold:
    man = _weld(
        np.asarray(vertices, dtype=np.float64), np.asarray(triangles, dtype=np.int64)
    )
    if man.status() != m3.Error.NoError:
        raise MeshError(f"not a closed solid ({man.status().name})")
    return man


def arrays(man: m3.Manifold) -> tuple[np.ndarray, np.ndarray]:
    mesh = man.to_mesh()
    return np.asarray(mesh.vert_properties)[:, :3].astype(np.float64), np.asarray(
        mesh.tri_verts
    ).astype(np.int64)


def volume(man: m3.Manifold) -> float:
    return float(man.volume())


def intersection_volume(a: m3.Manifold, b: m3.Manifold) -> float:
    return float((a ^ b).volume())


def min_gap(a: m3.Manifold, b: m3.Manifold, search: float = 5.0) -> float:
    """The smallest distance between `a` and `b`, or `search` if farther.
    Overlapping meshes give 0."""
    return float(a.min_gap(b, search))


def bounds(man: m3.Manifold) -> tuple[np.ndarray, np.ndarray]:
    lo, hi = man.bounding_box()[:3], man.bounding_box()[3:]
    return np.array(lo), np.array(hi)


_3MF_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels"
 ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="model"
 ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
"""
_3MF_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Target="/3D/3dmodel.model" Id="rel0"
 Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""


def write_3mf(man: m3.Manifold, path: Path, name: str) -> None:
    """A 3MF file of one closed mesh, in millimetres."""
    import zipfile
    from xml.sax.saxutils import quoteattr

    vertices, triangles = arrays(man)
    vs = "\n".join(
        f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in vertices
    )
    ts = "\n".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in triangles)
    model = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
        f'<resources><object id="1" type="model" name={quoteattr(name)}>'
        f"<mesh><vertices>\n{vs}\n</vertices><triangles>\n{ts}\n</triangles></mesh>"
        "</object></resources>\n"
        '<build><item objectid="1"/></build>\n</model>\n'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _3MF_TYPES)
        z.writestr("_rels/.rels", _3MF_RELS)
        z.writestr("3D/3dmodel.model", model)


def load_mesh_file(path: Path) -> m3.Manifold:
    """A part supplied as STL (binary or ASCII) or 3MF, as a manifold mesh."""
    suffix = path.suffix.lower()
    if suffix == ".stl":
        vertices, triangles = _read_stl(path)
    elif suffix == ".3mf":
        vertices, triangles = _read_3mf(path)
    else:
        raise MeshError(f"{path.name}: expected an .stl or .3mf file")
    try:
        return from_arrays(vertices, triangles)
    except MeshError as e:
        raise MeshError(f"{path.name}: {e}") from None


def _read_stl(path: Path) -> tuple[np.ndarray, np.ndarray]:
    data = path.read_bytes()
    if len(data) >= 84:
        count = int.from_bytes(data[80:84], "little")
        if len(data) == 84 + 50 * count:
            rec = np.frombuffer(
                data[84:],
                dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]),
            )
            verts = rec["v"].reshape(-1, 3).astype(np.float64)
            return verts, np.arange(len(verts)).reshape(-1, 3)
    pts = [
        [float(x) for x in line.split()[1:4]]
        for line in data.decode("ascii", "replace").splitlines()
        if line.strip().startswith("vertex")
    ]
    if not pts or len(pts) % 3:
        raise MeshError(f"{path.name}: not a readable STL file")
    verts = np.array(pts, dtype=np.float64)
    return verts, np.arange(len(verts)).reshape(-1, 3)


def _read_3mf(path: Path) -> tuple[np.ndarray, np.ndarray]:
    import xml.etree.ElementTree as ET
    import zipfile

    try:
        with zipfile.ZipFile(path) as z:
            model = next(n for n in z.namelist() if n.lower().endswith(".model"))
            root = ET.fromstring(z.read(model))
    except (zipfile.BadZipFile, StopIteration, ET.ParseError):
        raise MeshError(f"{path.name}: not a readable 3MF file") from None
    all_v: list[np.ndarray] = []
    all_t: list[np.ndarray] = []
    offset = 0
    for mesh in root.iter():
        if not mesh.tag.endswith("}mesh") and mesh.tag != "mesh":
            continue
        vs = [
            [float(e.get("x")), float(e.get("y")), float(e.get("z"))]
            for e in mesh.iter()
            if e.tag.endswith("vertex")
        ]
        ts = [
            [int(e.get("v1")), int(e.get("v2")), int(e.get("v3"))]
            for e in mesh.iter()
            if e.tag.endswith("triangle")
        ]
        all_v.append(np.array(vs, dtype=np.float64).reshape(-1, 3))
        all_t.append(np.array(ts, dtype=np.int64).reshape(-1, 3) + offset)
        offset += len(vs)
    if not all_v:
        raise MeshError(f"{path.name}: the 3MF file holds no mesh")
    return np.vstack(all_v), np.vstack(all_t)
