# backend/main.py
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import subprocess, os, uuid, shutil
from mongo import dolls_collection  # your existing MongoDB collection

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # replace '*' with your Flutter web URL in production
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.join(os.path.dirname(__file__), "dolls")
os.makedirs(BASE_DIR, exist_ok=True)

HOST_URL = "http://172.19.233.247:8000"  # your LAN IP

@app.post("/create_doll")
async def create_doll(
    name: str = Form(...),
    age: int = Form(...),
    height: float = Form(...),
    weight: float = Form(...),
    gender: str = Form("female"),
    skin_color: str = Form("medium"),
    model_type: str = Form("smplx"),
):
    doll_id = str(uuid.uuid4())
    doll_path = os.path.join(BASE_DIR, f"{doll_id}.glb")

    proc = subprocess.run([
        "python3",
        os.path.join(os.path.dirname(__file__), "create_doll.py"),
        "--out", doll_path,
        "--gender", gender,
        "--skin", skin_color,
        "--model", model_type,
        "--height", str(height),
        "--weight", str(weight)
    ], capture_output=True, text=True)

    if proc.returncode != 0 or not os.path.exists(doll_path):
        return JSONResponse(
            content={"error": "Doll generation failed", "stdout": proc.stdout, "stderr": proc.stderr},
            status_code=500
        )

    dolls_collection.insert_one({
        "_id": doll_id,
        "name": name,
        "age": age,
        "height": height,
        "weight": weight,
        "gender": gender,
        "skin_color": skin_color,
        "model_type": model_type,
        "file_url": f"{HOST_URL}/get_doll/{doll_id}.glb"
    })

    return {"doll_id": doll_id, "file": f"/get_doll/{doll_id}.glb"}

@app.get("/get_doll/{doll_id}")
async def get_doll(doll_id: str):
    doll_path = os.path.join(BASE_DIR, f"{doll_id}.glb")
    if not os.path.exists(doll_path):
        return JSONResponse(content={"error": "Doll not found"}, status_code=404)

    return FileResponse(
        doll_path,
        media_type="model/gltf-binary",
        headers={"Access-Control-Allow-Origin": "*"}
    )

@app.post("/upload_clothing/{doll_id}")
async def upload_clothing(
    doll_id: str,
    clothing_type: str = Form(...),
    size: str = Form(...),
    color: str = Form(...),
    file: UploadFile = File(...),
):
    doll_path = os.path.join(BASE_DIR, f"{doll_id}.glb")
    if not os.path.exists(doll_path):
        return JSONResponse(content={"error": "Doll not found"}, status_code=404)

    clothes_dir = os.path.join(BASE_DIR, doll_id, "clothes")
    os.makedirs(clothes_dir, exist_ok=True)
    clothing_path = os.path.join(clothes_dir, file.filename)

    with open(clothing_path, "wb") as f:
        f.write(await file.read())

    updated_path = os.path.join(BASE_DIR, f"{doll_id}_updated.glb")
    proc = subprocess.run([
        "python3",
        os.path.join(os.path.dirname(__file__), "apply_clothing.py"),
        "--doll", doll_path,
        "--img", clothing_path,
        "--out", updated_path,
        "--type", clothing_type
    ], capture_output=True, text=True)

    if proc.returncode != 0 or not os.path.exists(updated_path):
        return JSONResponse(content={
            "error": "Failed to apply clothing",
            "stdout": proc.stdout,
            "stderr": proc.stderr
        }, status_code=500)

    shutil.move(updated_path, doll_path)

    dolls_collection.update_one(
        {"_id": doll_id},
        {"$set": {"file_url": f"{HOST_URL}/get_doll/{doll_id}.glb"}}
    )

    return {"message": f"{clothing_type} applied", "file": f"/get_doll/{doll_id}.glb"}
