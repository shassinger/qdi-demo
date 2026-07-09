import sys
import os
import re
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure we can load QDI Python bindings
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from qdi_python import QdiClient, QDIError

# Qiskit Simulators
from qiskit import QuantumCircuit
from qiskit.qasm3 import loads as loads3
from qiskit_aer import AerSimulator

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

# In-memory database of simulation results
simulation_results = {}

class AuthRequest(BaseModel):
    token: str

class TaskSubmitRequest(BaseModel):
    task_payload: str
    task_type: str = "openqasm3"
    shots: int = 100

def parse_qasm(qasm_str: str) -> QuantumCircuit:
    if "OPENQASM 3" in qasm_str:
        return loads3(qasm_str)
    else:
        # Standard fallback for OpenQASM 2.0
        return QuantumCircuit.from_qasm_str(qasm_str)

def simulate_qir(qir_str: str, shots: int = 1000) -> dict:
    qubit_indices = set()
    gates = []
    
    # Match any calls to @__quantum__qis__*__body (using greedy matching for balanced args)
    pattern = re.compile(r"__quantum__qis__(\w+)__body\((.*)\)")
    
    for line in qir_str.splitlines():
        m = pattern.search(line)
        if m:
            gate = m.group(1)
            args_str = m.group(2)
            if args_str.endswith(")"):
                args_str = args_str[:-1]
            
            # Split arguments by commas, ignoring commas inside parenthesis
            args = []
            current = []
            depth = 0
            for char in args_str:
                if char == ',' and depth == 0:
                    args.append("".join(current).strip())
                    current = []
                else:
                    if char == '(':
                        depth += 1
                    elif char == ')':
                        depth -= 1
                    current.append(char)
            if current:
                args.append("".join(current).strip())
            
            indices = []
            for arg in args:
                if re.search(r"\bnull\b", arg):
                    indices.append(0)
                else:
                    num_match = re.search(r"i64 (\d+)", arg)
                    if num_match:
                        indices.append(int(num_match.group(1)))
                    else:
                        indices.append(0)
            
            gates.append((gate, indices))
            # Track all qubits used
            if gate == "mz":
                qubit_indices.add(indices[0])
            else:
                for idx in indices:
                    qubit_indices.add(idx)

    num_qubits = max(qubit_indices) + 1 if qubit_indices else 1
    qc = QuantumCircuit(num_qubits, num_qubits)
    
    for gate, indices in gates:
        if gate == "h":
            qc.h(indices[0])
        elif gate == "cnot" or gate == "cx":
            qc.cx(indices[0], indices[1])
        elif gate == "x":
            qc.x(indices[0])
        elif gate == "y":
            qc.y(indices[0])
        elif gate == "z":
            qc.z(indices[0])
        elif gate == "s":
            qc.s(indices[0])
        elif gate == "sdg":
            qc.sdg(indices[0])
        elif gate == "t":
            qc.t(indices[0])
        elif gate == "tdg":
            qc.tdg(indices[0])
        elif gate == "mz":
            qc.measure(indices[0], indices[1])
            
    sim = AerSimulator()
    job = sim.run(qc, shots=shots)
    return job.result().get_counts()

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
        # Run C-ABI Send call to get a valid task ID and manage execution state machine
        task_id = client.send(
            task_payload=req.task_payload.encode("utf-8"),
            task_type=req.task_type,
            shots=req.shots
        )
        
        # Perform real classical simulation inside the server wrapper
        try:
            if req.task_type == "qir":
                counts = simulate_qir(req.task_payload, req.shots)
            else:
                qc = parse_qasm(req.task_payload)
                sim = AerSimulator()
                job = sim.run(qc, shots=req.shots)
                counts = job.result().get_counts()
                
            # Store counts in local database for subsequent retrieval
            simulation_results[task_id] = counts
        except Exception as sim_err:
            # Fallback to standard mock C-ABI counts if simulation fails (e.g. syntax error)
            print(f"Simulation warning: {sim_err}")
            
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
        
        # If we have real simulation results cached, return them!
        if task_id in simulation_results:
            return {
                "task_id": task_id,
                "result_type": "counts",
                "result": simulation_results[task_id]
            }
            
        # Otherwise fallback to standard driver outputs
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
    print("Starting QDI Demo Server on http://0.0.0.0:8000 ...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
