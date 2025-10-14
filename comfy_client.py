import os

#host/IP where ComfyUI runs "http://127.0.0.1:8188" (local), or "http://192.168.1.10:8188" (for LAN)
COMFY_BASE_URL = "http://127.0.0.1:8188"

#my workflow location
WORKFLOW_PATH = os.path.abspath("workflows/3d-mdl-2.json")

#local temp output folder for FastAPI where uploaded images and downloaded 3D results will be stored
OUTPUT_DIR = os.path.abspath("outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Optional: timeout or polling interval for job status checks

COMFY_POLL_INTERVAL = 2    # seconds between each poll
COMFY_TIMEOUT = 60         # total seconds to wait for workflow completion


