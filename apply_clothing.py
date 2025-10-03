#!/usr/bin/env python3
# apply_clothing.py
"""
Improved clothing application for SMPL/SMPL-X doll.

Approach (MVP+):
 - Load doll GLB and take the main body mesh.
 - Estimate torso region by sampling vertices in a Y-range relative to bounding box.
 - Build a convex-hull from those torso vertices to create a clothing mesh surface.
 - Compute cylindrical UVs for the clothing mesh (wrap around Y axis).
 - Apply the clothing image as a texture (alpha preserved if present).
 - Combine body + clothing and export updated GLB.

Usage:
 python3 apply_clothing.py --doll backend/dolls/<id>.glb --img path/to/shirt.png --out backend/dolls/<id>_updated.glb
Optional:
 --type: 'tshirt'|'dress'|'jacket' (used for heuristics)
 --torso_min / --torso_max: adjust torso vertical region (fractions 0..1)
"""
import argparse
import os
import sys
import numpy as np
from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument("--doll", required=True)
parser.add_argument("--img", required=True)
parser.add_argument("--out", required=True)
parser.add_argument("--type", default="tshirt", choices=["tshirt","dress","jacket","shirt"])
parser.add_argument("--torso_min", type=float, default=0.40, help="fraction of bbox height to start torso (0..1)")
parser.add_argument("--torso_max", type=float, default=0.85, help="fraction of bbox height to end torso (0..1)")
args = parser.parse_args()

try:
    import trimesh
except Exception as e:
    print("Missing dependency: trimesh (pip install trimesh).", e)
    sys.exit(2)

if not os.path.exists(args.doll):
    print("Doll file not found:", args.doll)
    sys.exit(3)
if not os.path.exists(args.img):
    print("Clothing image not found:", args.img)
    sys.exit(4)

# --- Load scene and pick body mesh ---
scene = trimesh.load(args.doll, force='scene')

# Find largest geometry (likely the body)
geoms = list(scene.geometry.items())
if len(geoms) == 0:
    print("No geometry found in doll glb")
    sys.exit(5)

# Choose the geometry with largest number of vertices (heuristic for body)
body_name, body = max(geoms, key=lambda kv: getattr(kv[1], 'vertices', np.zeros((0,))).shape[0])

if not isinstance(body, trimesh.Trimesh):
    # try convert
    try:
        body = trimesh.Trimesh(vertices=body.vertices, faces=body.faces, process=False)
    except Exception as e:
        print("Could not coerce body geometry to Trimesh:", e)
        sys.exit(6)

# Ensure faces exist
if body.faces is None or body.faces.shape[0] == 0:
    print("The body mesh has no faces.")
    sys.exit(7)

# --- Compute bounding box and torso region ---
bbox_min, bbox_max = body.bounds
extent = bbox_max - bbox_min
min_y = bbox_min[1]
max_y = bbox_max[1]
height = max_y - min_y

# torso range in world Y (user-adjustable by torso_min/torso_max)
t_min = min_y + args.torso_min * height
t_max = min_y + args.torso_max * height

verts = body.vertices  # (N,3)
# Select vertices inside torso vertical slice and reasonably near center XZ
# Compute horizontal center
center_x = (bbox_min[0] + bbox_max[0]) / 2.0
center_z = (bbox_min[2] + bbox_max[2]) / 2.0
# radial limit (use 0.6 of half-width)
radial_limit = max(extent[0], extent[2]) * 0.55

mask = (verts[:,1] >= t_min) & (verts[:,1] <= t_max)
# also ensure within radial distance from center (avoid legs)
dx = verts[:,0] - center_x
dz = verts[:,2] - center_z
mask = mask & (dx*dx + dz*dz <= radial_limit * radial_limit)

verts_torso = verts[mask]
if verts_torso.shape[0] < 10:
    # fallback: widen vertical band
    t_min = min_y + 0.35*height
    t_max = min_y + 0.90*height
    mask = (verts[:,1] >= t_min) & (verts[:,1] <= t_max)
    verts_torso = verts[mask]

if verts_torso.shape[0] < 10:
    print("Couldn't find enough torso vertices to generate clothing. Try adjusting torso_min/torso_max.")
    sys.exit(8)

# --- Build a surface mesh for clothing: convex hull of torso vertices (fast, robust) ---
try:
    torso_cloud = trimesh.Trimesh(vertices=verts_torso, faces=[], process=False)
    clothing_mesh = torso_cloud.convex_hull
except Exception as e:
    # fallback: simple planar triangulation of the point cloud (less ideal)
    print("Convex hull failed, falling back to quick triangulation:", e)
    try:
        clothing_mesh = trimesh.Trimesh(vertices=verts_torso, process=True).convex_hull
    except Exception as e2:
        print("Failed to create clothing mesh:", e2)
        sys.exit(9)

# Ensure clothing mesh is a proper Trimesh
if not isinstance(clothing_mesh, trimesh.Trimesh) or clothing_mesh.faces.size == 0:
    print("Generated clothing mesh is invalid.")
    sys.exit(10)

# --- Compute cylindrical UV mapping for clothing mesh (wrap around Y axis) ---
cm_verts = clothing_mesh.vertices.copy()
# center in XZ plane
cx = center_x
cz = center_z
# compute angle around Y for each vertex (atan2 uses (z - cz, x - cx) ordering depending on orientation)
angles = np.arctan2(cm_verts[:,2] - cz, cm_verts[:,0] - cx)  # range [-pi, pi]
u = (angles + np.pi) / (2*np.pi)  # 0..1
# v as normalized height within clothing mesh vertical range
v_min = cm_verts[:,1].min()
v_max = cm_verts[:,1].max()
v_range = max(1e-6, v_max - v_min)
v = (cm_verts[:,1] - v_min) / v_range
uv = np.column_stack((u, v))  # per-vertex UVs

# --- Load clothing image, optionally respect alpha ---
image = Image.open(args.img).convert("RGBA")
# Optionally: resize the texture to something reasonable to keep file sizes small
max_tex = 2048
if max(image.size) > max_tex:
    scale = max_tex / max(image.size)
    new_size = (int(image.size[0]*scale), int(image.size[1]*scale))
    image = image.resize(new_size, Image.LANCZOS)

# Build TextureVisuals using per-vertex uv.
try:
    visual = trimesh.visual.texture.TextureVisuals(uv=uv, image=image)
    # assign texture to a new mesh using the clothing mesh faces
    textured_cloth = trimesh.Trimesh(vertices=cm_verts, faces=clothing_mesh.faces.copy(), visual=visual, process=False)
except Exception as e:
    # If TextureVisuals with per-vertex uv fails, fallback to plain color
    print("Could not assign texture visual directly, falling back to flat color. Error:", e)
    # create neutral gray
    colored = np.tile(np.array([200,200,200,255], dtype=np.uint8), (clothing_mesh.vertices.shape[0], 1))
    textured_cloth = trimesh.Trimesh(vertices=cm_verts, faces=clothing_mesh.faces.copy(), vertex_colors=colored, process=False)

# Slightly offset the clothing mesh along normals so it sits above the body (avoid z-fighting)
try:
    normals = textured_cloth.vertex_normals
    offset = 0.005 * max(extent)  # 0.5% of model maximum dimension
    textured_cloth.apply_translation(normals * offset)
except Exception:
    # fallback: small uniform translation outward along vector from center
    dir_out = np.column_stack((cm_verts[:,0]-cx, cm_verts[:,1]-v_min, cm_verts[:,2]-cz))
    dir_norm = np.linalg.norm(dir_out, axis=1, keepdims=True)
    dir_norm[dir_norm == 0] = 1.0
    dir_out = dir_out / dir_norm
    textured_cloth.vertices += dir_out * (0.003 * max(extent))

# Name the clothing geometry for export clarity
textured_cloth.metadata = {"name": f"cloth_{args.type}"}

# --- Combine body & clothing into scene ---
out_scene = trimesh.Scene()
# Add original scene geometry to preserve possible materials / nodes
# We'll add all geometries but replace the body geometry with our original body mesh (to ensure same transform)
for name, geom in scene.geometry.items():
    # if this was the chosen body geometry, use our 'body' variable to ensure consistency
    if name == body_name:
        out_scene.add_geometry(body, node_name="body")
    else:
        out_scene.add_geometry(geom, node_name=name)

# Add clothing mesh
out_scene.add_geometry(textured_cloth, node_name="cloth")

# Export GLB
out_dir = os.path.dirname(args.out)
if out_dir:
    os.makedirs(out_dir, exist_ok=True)

try:
    out_scene.export(args.out)
    print("Wrote updated GLB with clothing to", args.out)
except Exception as e:
    print("Failed to export updated GLB:", e)
    sys.exit(11)
