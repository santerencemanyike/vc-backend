# create_doll.py
"""
Create a realistic SMPL/SMPL-X body and export a GLB.

Usage:
 python3 create_doll.py --out /path/to/out.glb --gender female --skin medium --model smplx --height 170 --weight 65
"""
import argparse, os, sys, numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True)
parser.add_argument("--gender", default="female", choices=["female","male","neutral"])
parser.add_argument("--skin", default="medium")
parser.add_argument("--model", default="smplx", choices=["smpl","smplx"])
parser.add_argument("--height", type=float, default=170.0)
parser.add_argument("--weight", type=float, default=65.0)
args = parser.parse_args()

# --- Ensure model files exist ---
MODEL_BASE = os.path.join(os.path.dirname(__file__), "models")
MODEL_FOLDER = os.path.join(MODEL_BASE, "SMPLX" if args.model=="smplx" else "SMPL")

if not os.path.exists(MODEL_FOLDER):
    print(f"SMPL model folder not found at {MODEL_FOLDER}. Please download model files and place them there.")
    sys.exit(2)

# Import libraries
try:
    import torch
    from smplx import SMPL, SMPLX
    import trimesh
except Exception as e:
    print("Missing dependency: torch/smplx/trimesh. Install them.", e)
    sys.exit(3)

# Load model
body_model = SMPLX(
    model_path=MODEL_FOLDER,
    gender=args.gender,
    use_pca=False,
    create_global_orient=True,
    create_body_pose=True,
    num_betas=10
) if args.model=="smplx" else SMPL(
    model_path=MODEL_FOLDER,
    gender=args.gender,
    create_global_orient=True,
    create_body_pose=True,
    num_betas=10
)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
body_model = body_model.to(device)
betas = torch.zeros((1,10), dtype=torch.float32).to(device)

with torch.no_grad():
    output = body_model(
        betas=betas,
        body_pose=torch.zeros((1, body_model.body_pose.size(1))).to(device) if hasattr(body_model,'body_pose') else torch.zeros((1,69)).to(device),
        global_orient=torch.zeros((1,3)).to(device)
    )

verts = output.vertices.detach().cpu().numpy().squeeze()
faces = body_model.faces if hasattr(body_model, "faces") else None

if faces is None:
    print("Could not access model.faces; ensure SMPL/SMPL-X model loaded properly.")

mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)

skin_map = {
    "light": [240,200,180,255],
    "medium": [195,150,120,255],
    "dark": [100,60,40,255]
}
rgba = np.array(skin_map.get(args.skin, skin_map["medium"]), dtype=np.uint8)
mesh.visual.vertex_colors = np.tile(rgba, (mesh.vertices.shape[0], 1))

os.makedirs(os.path.dirname(args.out), exist_ok=True)
mesh.export(args.out)
print(f"Exported SMPL {args.model} doll to {args.out}")
