import sys
import os
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure we can load QDI Python bindings
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from qdi_python import QdiClient, QDIError

app = FastAPI(title="QDI Demo Server", description="Localhost REST API wrapper for the QDI mock device.")

# Enable CORS for the local browser client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = QdiClient()

class AuthRequest(BaseModel):
    token: str

class TaskSubmitRequest(BaseModel):
    task_payload: str
    task_type: str = "openqasm3"
    shots: int = 100

@app.get("/qdi/v1/devices/mock/discover")
def discover():
    try:
        return client.discover()
    except QDIError as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/qdi/v1/devices/mock/authenticate")
def authenticate(req: AuthRequest):
    try:
        client.authenticate({"token": req.token})
        return {"status": "authenticated"}
    except QDIError as e:
        raise HTTPException(status_code=401, detail="Authentication failed (invalid token).")

@app.post("/qdi/v1/devices/mock/tasks")
def send(req: TaskSubmitRequest):
    try:
        task_id = client.send(
            task_payload=req.task_payload.encode("utf-8"),
            task_type=req.task_type,
            shots=req.shots
        )
        return {"task_id": task_id, "status": "submitted"}
    except QDIError as e:
        if e.code == 2:
            raise HTTPException(status_code=401, detail="Authentication required.")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/qdi/v1/devices/mock/tasks/{task_id}/status")
def monitor(task_id: str):
    try:
        status_code, advisory = client.monitor(task_id)
        status_mapping = {
            0: "QUEUED",
            1: "EXECUTING",
            2: "COMPLETED",
            3: "FAULTED",
            4: "CANCELLED"
        }
        return {
            "task_id": task_id,
            "status": status_mapping.get(status_code, "UNKNOWN"),
            "advisory_metadata": advisory
        }
    except QDIError as e:
        raise HTTPException(status_code=404, detail="Task not found.")

@app.get("/qdi/v1/devices/mock/tasks/{task_id}/results")
def receive(task_id: str):
    try:
        result, result_type = client.receive(task_id)
        import json
        return {
            "task_id": task_id,
            "result_type": result_type,
            "result": json.loads(result)
        }
    except QDIError as e:
        raise HTTPException(status_code=500, detail=str(e))

import urllib.request
PNNL_CIRCUITS = {
    "qaoa_n3": "https://raw.githubusercontent.com/pnnl/QASMBench/master/small/qaoa_n3/qaoa_n3.qasm",
    "deutsch_n2": "https://raw.githubusercontent.com/pnnl/QASMBench/master/small/deutsch_n2/deutsch_n2.qasm",
    "toffoli_n3": "https://raw.githubusercontent.com/pnnl/QASMBench/master/small/toffoli_n3/toffoli_n3.qasm",
    "qft_n4": "https://raw.githubusercontent.com/pnnl/QASMBench/master/small/qft_n4/qft_n4.qasm",
    "lpn_n5": "https://raw.githubusercontent.com/pnnl/QASMBench/master/small/lpn_n5/lpn_n5.qasm",
    "error_correctiond3_n5": "https://raw.githubusercontent.com/pnnl/QASMBench/master/small/error_correctiond3_n5/error_correctiond3_n5.qasm",
    "grover_n2": "https://raw.githubusercontent.com/pnnl/QASMBench/master/small/grover_n2/grover_n2.qasm"
}
cached_circuits = {}

@app.get("/qdi/v1/circuits")
def get_pnnl_circuits():
    for name, url in PNNL_CIRCUITS.items():
        if name not in cached_circuits:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=3) as conn:
                    cached_circuits[name] = conn.read().decode("utf-8")
            except Exception as e:
                cached_circuits[name] = f"// Error fetching {name} from PNNL QASMBench: {e}\nOPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[5];\ncreg c[5];\n"
    return cached_circuits



if __name__ == "__main__":
    print("Starting QDI Demo Server on http://127.0.0.1:8000 ...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
