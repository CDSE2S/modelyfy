from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
import os, json, uuid, requests, time
from comfy_client import COMFY_BASE_URL, WORKFLOW_PATH, OUTPUT_DIR

app = FastAPI(title="Image to 3D API")

def upload_to_comfy(local_path: str) -> str:
    """Upload an image to ComfyUI’s /upload/image endpoint."""
    with open(local_path, "rb") as f:
        files = {"image": (os.path.basename(local_path), f, "image/png")}
        resp = requests.post(f"{COMFY_BASE_URL}/upload/image", files=files)
        if resp.status_code != 200:
            raise Exception(f"ComfyUI upload failed: {resp.text}")
    return os.path.basename(local_path)


@app.post("/convert")
async def convert_images(
    front: UploadFile = File(...),
    left: UploadFile = File(...),
    back: UploadFile = File(...)
):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    #save temporary uploaded files
    def save_temp(file):
        tmp_path = f"{OUTPUT_DIR}/{uuid.uuid4()}_{file.filename}"
        with open(tmp_path, "wb") as f:
            f.write(file.file.read())
        return tmp_path

    front_local = save_temp(front)
    left_local = save_temp(left)
    back_local = save_temp(back)

    #upload to comfy
    try:
        front_name = upload_to_comfy(front_local)
        left_name = upload_to_comfy(left_local)
        back_name = upload_to_comfy(back_local)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    #loading workflow json
    with open(WORKFLOW_PATH, "r") as f:
        workflow = json.load(f)

    workflow["56"]["inputs"]["image"] = front_name
    workflow["78"]["inputs"]["image"] = left_name
    workflow["80"]["inputs"]["image"] = back_name

    # submit workflow to comfy
    resp = requests.post(f"{COMFY_BASE_URL}/prompt", json={"prompt": workflow})
    if resp.status_code != 200:
        return JSONResponse({"error": f"ComfyUI failed: {resp.text}"}, status_code=500)

    prompt_id = resp.json().get("prompt_id")
    if not prompt_id:
        return JSONResponse({"error": "ComfyUI did not return a prompt_id"}, status_code=500)

    # Poll for workflow completion
    for _ in range(90):  # 90s wait time
        hist = requests.get(f"{COMFY_BASE_URL}/history/{prompt_id}")
        if hist.status_code == 200 and hist.json():
            data = hist.json().get(prompt_id, {})
            if data.get("outputs"):
                break
        time.sleep(2)
    else:
        return JSONResponse({"error": "No 3D output found or job timed out"}, status_code=504)

    # finding the SaveGLB node output
    hist = requests.get(f"{COMFY_BASE_URL}/history/{prompt_id}")
    output_path = None

    if hist.status_code == 200 and hist.json():
        data = hist.json().get(prompt_id, {})
        outputs = data.get("outputs", {})
        for node_id, node_data in outputs.items():
            if isinstance(node_data, dict):
                for out_type, items in node_data.items():
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict) and item.get("filename", "").endswith((".glb", ".obj")):
                                filename = item["filename"]
                                subfolder = item.get("subfolder", "")
                                output_path = os.path.join(subfolder, filename)
                                break

    # Fallback to get the most recent .glb via /view/list API
    if not output_path:
        try:
            view_list = requests.get(f"{COMFY_BASE_URL}/view?type=output").json()
            mesh_files = [
                f for f in view_list.get("files", [])
                if f["filename"].endswith(".glb") and "mesh" in f.get("subfolder", "")
            ]
            if mesh_files:
                mesh_files.sort(key=lambda x: x.get("mtime", 0), reverse=True)
                latest = mesh_files[0]
                output_path = os.path.join(latest["subfolder"], latest["filename"])
        except Exception as e:
            return JSONResponse({"error": f"Could not list output files: {str(e)}"}, status_code=500)

    if not output_path:
        return JSONResponse({"error": "3D model was generated but not found in ComfyUI outputs"}, status_code=500)

    # Download from /view endpoint 
    model_url = f"{COMFY_BASE_URL}/view?filename={os.path.basename(output_path)}&subfolder={os.path.dirname(output_path)}&type=output"
    r = requests.get(model_url)
    if r.status_code != 200:
        return JSONResponse({"error": f"Could not download model: {r.text}"}, status_code=500)

    # Save locally and return 
    model_file = os.path.join(OUTPUT_DIR, os.path.basename(output_path))
    with open(model_file, "wb") as f:
        f.write(r.content)

    return FileResponse(model_file, filename=os.path.basename(model_file))



