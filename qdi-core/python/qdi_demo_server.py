import sys
import os
import re
import json
from pathlib import Path
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Ensure we can load QDI Python bindings
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from qdi_python import QdiClient, QDIError

# Qiskit Simulators
from qiskit import QuantumCircuit
from qiskit.qasm3 import loads as loads3
from qiskit_aer import AerSimulator

STATIC_DIR = Path(__file__).resolve().parent
REPO_ROOT = STATIC_DIR.parents[1]
DEFAULT_DEVICE_LIBRARY_PATH = STATIC_DIR / "mock_device_library.json"
DEVICE_LIBRARY_STATE_PATH = Path(
    os.environ.get("QDI_DEVICE_LIBRARY_STATE", REPO_ROOT / ".qdi" / "device_library.json")
)

app = FastAPI(title="QDI Demo Server", description="Localhost REST API wrapper for the QDI mock device.")

# Enable CORS for the local browser client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = QdiClient()

# In-memory database of simulation results
simulation_results = {}
session_state = {
    "discovered": False,
    "authenticated": False,
}

DEFAULT_DEVICE_CONFIG = {
    "device_id": "mock_qdi_qubit_v1",
    "display_name": "Mock QDI QPU",
    "supported_auth_methods": ["token"],
    "supported_task_types": ["openqasm3", "openqasm2", "qir"],
    "is_ready": True,
    "supports_estimation": True,
    "num_qubits": 32,
    "max_shots": 10000,
    "estimation": {
        "base_duration_sec": 0.02,
        "duration_per_shot_sec": 0.00003,
        "duration_per_depth_sec": 0.004,
        "cost_per_shot_usd": 0.0,
        "cost_per_qubit_usd": 0.0,
    },
    "task_type_aliases": {
        "qasm3": "openqasm3",
        "qasm2": "openqasm2",
        "llvm": "qir",
    },
}

def normalize_device_config(overrides: dict) -> dict:
    config = DEFAULT_DEVICE_CONFIG.copy()
    config.update(overrides)

    config["num_qubits"] = int(config["num_qubits"])
    config["max_shots"] = int(config.get("max_shots", DEFAULT_DEVICE_CONFIG["max_shots"]))
    config["device_id"] = str(config.get("device_id", "")).strip()
    config["display_name"] = str(config.get("display_name", "")).strip()
    config["supported_task_types"] = list(config["supported_task_types"])
    config["supported_auth_methods"] = list(config["supported_auth_methods"])
    config["supports_estimation"] = bool(config.get("supports_estimation", False))
    config["is_ready"] = bool(config.get("is_ready", True))
    estimation_config = DEFAULT_DEVICE_CONFIG["estimation"].copy()
    estimation_config.update(config.get("estimation", {}))
    config["estimation"] = estimation_config

    aliases = DEFAULT_DEVICE_CONFIG["task_type_aliases"].copy()
    aliases.update(config.get("task_type_aliases", {}))
    config["task_type_aliases"] = aliases

    if config["num_qubits"] < 1:
        raise ValueError("Device config num_qubits must be at least 1.")
    if not config["device_id"]:
        raise ValueError("Device config device_id must not be empty.")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", config["device_id"]):
        raise ValueError("Device config device_id may contain only letters, numbers, dots, underscores, and hyphens.")
    if not config["display_name"]:
        raise ValueError("Device config display_name must not be empty.")
    if config["max_shots"] < 1:
        raise ValueError("Device config max_shots must be at least 1.")
    if not config["supported_task_types"]:
        raise ValueError("Device config supported_task_types must not be empty.")

    return config

def load_device_config() -> dict:
    config_path = os.environ.get(
        "QDI_DEVICE_CONFIG",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_device_config.json")
    )
    loaded_config = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as config_file:
            loaded_config = json.load(config_file)
    else:
        print(f"Device config not found at {config_path}; using built-in defaults.")

    return normalize_device_config(loaded_config)

def load_device_library() -> tuple[dict[str, dict], str]:
    if os.environ.get("QDI_DEVICE_CONFIG"):
        config = load_device_config()
        return {config["device_id"]: config}, config["device_id"]

    library_path = (
        DEVICE_LIBRARY_STATE_PATH
        if DEVICE_LIBRARY_STATE_PATH.exists()
        else DEFAULT_DEVICE_LIBRARY_PATH
    )
    with library_path.open("r", encoding="utf-8") as library_file:
        library_data = json.load(library_file)

    devices = {}
    for device_overrides in library_data.get("devices", []):
        config = normalize_device_config(device_overrides)
        device_id = config["device_id"]
        if device_id in devices:
            raise ValueError(f"Duplicate device_id '{device_id}' in {library_path}.")
        devices[device_id] = config

    if not devices:
        raise ValueError(f"Device library {library_path} must contain at least one device.")

    active_device_id = library_data.get("active_device_id")
    if active_device_id not in devices:
        active_device_id = next(iter(devices))
    return devices, active_device_id

def persist_device_library():
    DEVICE_LIBRARY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "active_device_id": ACTIVE_DEVICE_ID,
        "devices": list(DEVICE_LIBRARY.values()),
    }
    temporary_path = DEVICE_LIBRARY_STATE_PATH.with_suffix(".tmp")
    with temporary_path.open("w", encoding="utf-8") as state_file:
        json.dump(state, state_file, indent=2)
        state_file.write("\n")
    temporary_path.replace(DEVICE_LIBRARY_STATE_PATH)

DEVICE_LIBRARY, ACTIVE_DEVICE_ID = load_device_library()
MOCK_DEVICE_CONFIG = DEVICE_LIBRARY[ACTIVE_DEVICE_ID]

def activate_device(device_id: str) -> dict:
    global ACTIVE_DEVICE_ID, MOCK_DEVICE_CONFIG
    if device_id not in DEVICE_LIBRARY:
        raise KeyError(device_id)
    ACTIVE_DEVICE_ID = device_id
    MOCK_DEVICE_CONFIG = DEVICE_LIBRARY[device_id]
    reset_runtime_state()
    persist_device_library()
    return MOCK_DEVICE_CONFIG

class AuthRequest(BaseModel):
    token: str

class TaskSubmitRequest(BaseModel):
    task_payload: str
    task_type: str = "openqasm3"
    shots: int = 100

class EstimateRequest(BaseModel):
    task_payload: str
    task_type: str = "openqasm3"
    shots: int = 100

def reset_runtime_state():
    session_state["discovered"] = False
    session_state["authenticated"] = False
    simulation_results.clear()

def require_discovered():
    if not session_state["discovered"]:
        raise HTTPException(
            status_code=409,
            detail="Discovery required before this operation. Run qdi_discover first."
        )

def require_authenticated():
    if not session_state["authenticated"]:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Complete the QDI handshake before submitting work."
        )

def validate_task_type(task_type: str):
    normalized_type = normalize_task_type(task_type)
    if normalized_type not in MOCK_DEVICE_CONFIG["supported_task_types"]:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported task_type '{task_type}'. Supported types: {', '.join(MOCK_DEVICE_CONFIG['supported_task_types'])}."
        )
    return normalized_type

def normalize_task_type(task_type: str) -> str:
    return MOCK_DEVICE_CONFIG.get("task_type_aliases", {}).get(task_type, task_type)

def validate_shots(shots: int):
    if shots < 1:
        raise HTTPException(status_code=422, detail="shots must be at least 1.")
    max_shots = MOCK_DEVICE_CONFIG["max_shots"]
    if shots > max_shots:
        raise HTTPException(status_code=422, detail=f"shots exceeds device max_shots of {max_shots}.")

def parse_qasm_qubits(program: str) -> int:
    declarations = [
        r"\bqubit\s*\[\s*(\d+)\s*\]",
        r"\bqreg\s+\w+\s*\[\s*(\d+)\s*\]",
    ]
    for pattern in declarations:
        match = re.search(pattern, program)
        if match:
            return int(match.group(1))
    return 1

def parse_qir_qubits(program: str) -> int:
    qubit_indices = {0} if "__quantum__" in program else set()
    for match in re.finditer(r"i64\s+(\d+)\s+to\s+%Qubit\*", program):
        qubit_indices.add(int(match.group(1)))
    return max(qubit_indices) + 1 if qubit_indices else 1

def estimate_logical_depth(program: str, task_type: str) -> int:
    if task_type == "qir":
        return max(1, len(re.findall(r"__quantum__qis__\w+__body", program)))
    gate_lines = [
        line.strip()
        for line in program.splitlines()
        if line.strip()
        and not line.strip().startswith("//")
        and not line.strip().startswith("OPENQASM")
        and not line.strip().startswith("include")
        and not line.strip().startswith("qubit")
        and not line.strip().startswith("bit")
        and not line.strip().startswith("qreg")
        and not line.strip().startswith("creg")
    ]
    return max(1, len(gate_lines))

def estimate_payload_qubits(program: str, task_type: str) -> int:
    if task_type == "qir":
        return parse_qir_qubits(program)
    return parse_qasm_qubits(program)

def validate_payload_fits_device(program: str, task_type: str) -> int:
    requested_qubits = estimate_payload_qubits(program, task_type)
    if requested_qubits > MOCK_DEVICE_CONFIG["num_qubits"]:
        raise HTTPException(
            status_code=422,
            detail=f"Program requires {requested_qubits} qubits, but device supports {MOCK_DEVICE_CONFIG['num_qubits']}."
        )
    return requested_qubits

def estimate_resources(program: str, task_type: str, shots: int) -> dict:
    requested_qubits = validate_payload_fits_device(program, task_type)
    logical_depth = estimate_logical_depth(program, task_type)
    estimation_config = MOCK_DEVICE_CONFIG.get("estimation", {})

    duration = (
        float(estimation_config.get("base_duration_sec", 0.0))
        + shots * float(estimation_config.get("duration_per_shot_sec", 0.0))
        + logical_depth * float(estimation_config.get("duration_per_depth_sec", 0.0))
    )
    cost = (
        shots * float(estimation_config.get("cost_per_shot_usd", 0.0))
        + requested_qubits * float(estimation_config.get("cost_per_qubit_usd", 0.0))
    )

    return {
        "device_id": MOCK_DEVICE_CONFIG["device_id"],
        "task_type": task_type,
        "requested_qubits": requested_qubits,
        "max_qubits": MOCK_DEVICE_CONFIG["num_qubits"],
        "shots": shots,
        "logical_depth": logical_depth,
        "shots_duration_sec": round(duration, 6),
        "estimated_cost_usd": round(cost, 6),
    }

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

@app.get("/health")
def health():
    return {"status": "ok", "active_device_id": ACTIVE_DEVICE_ID}

@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def web_console():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/qdi/v1/devices/mock/config")
def get_device_config():
    return MOCK_DEVICE_CONFIG

@app.get("/qdi/v1/devices")
def list_devices():
    return {
        "active_device_id": ACTIVE_DEVICE_ID,
        "devices": list(DEVICE_LIBRARY.values()),
    }

@app.post("/qdi/v1/devices", status_code=201)
def create_device(config_update: dict):
    try:
        config = normalize_device_config(config_update)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    device_id = config["device_id"]
    if device_id in DEVICE_LIBRARY:
        raise HTTPException(status_code=409, detail=f"Device ID '{device_id}' already exists.")

    DEVICE_LIBRARY[device_id] = config
    activate_device(device_id)
    return {
        "status": "created",
        "message": "Device created and activated. Discovery and authentication state were reset.",
        "config": config,
    }

@app.post("/qdi/v1/devices/{device_id}/activate")
def select_device(device_id: str):
    try:
        config = activate_device(device_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Device ID '{device_id}' was not found.")
    return {
        "status": "activated",
        "message": "Device activated. Discovery and authentication state were reset.",
        "config": config,
    }

@app.put("/qdi/v1/devices/mock/config")
def update_device_config(config_update: dict):
    global ACTIVE_DEVICE_ID, MOCK_DEVICE_CONFIG
    try:
        updated_config = normalize_device_config(config_update)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    updated_device_id = updated_config["device_id"]
    if updated_device_id != ACTIVE_DEVICE_ID and updated_device_id in DEVICE_LIBRARY:
        raise HTTPException(status_code=409, detail=f"Device ID '{updated_device_id}' already exists.")

    del DEVICE_LIBRARY[ACTIVE_DEVICE_ID]
    DEVICE_LIBRARY[updated_device_id] = updated_config
    ACTIVE_DEVICE_ID = updated_device_id
    MOCK_DEVICE_CONFIG = updated_config

    reset_runtime_state()
    persist_device_library()
    return {
        "status": "updated",
        "message": "Mock device config updated. Discovery and authentication state were reset.",
        "config": MOCK_DEVICE_CONFIG
    }

@app.get("/qdi/v1/devices/mock/discover")
def discover():
    try:
        descriptor = client.discover()
        descriptor.update(MOCK_DEVICE_CONFIG)
        session_state["discovered"] = True
        return descriptor
    except QDIError as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/qdi/v1/devices/mock/authenticate")
def authenticate(req: AuthRequest):
    require_discovered()
    try:
        client.authenticate({"token": req.token})
        session_state["authenticated"] = True
        return {"status": "authenticated"}
    except QDIError as e:
        session_state["authenticated"] = False
        raise HTTPException(status_code=401, detail="Authentication failed (invalid token).")

@app.post("/qdi/v1/devices/mock/tasks")
def send(req: TaskSubmitRequest):
    require_discovered()
    require_authenticated()
    task_type = validate_task_type(req.task_type)
    validate_shots(req.shots)
    validate_payload_fits_device(req.task_payload, task_type)
    try:
        # Run C-ABI Send call to get a valid task ID and manage execution state machine
        task_id = client.send(
            task_payload=req.task_payload.encode("utf-8"),
            task_type=task_type,
            shots=req.shots
        )
        
        # Perform real classical simulation inside the server wrapper
        try:
            if task_type == "qir":
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

@app.post("/qdi/v1/devices/mock/estimate")
def estimate(req: EstimateRequest):
    require_discovered()
    require_authenticated()
    task_type = validate_task_type(req.task_type)
    validate_shots(req.shots)
    if not MOCK_DEVICE_CONFIG["supports_estimation"]:
        raise HTTPException(status_code=501, detail="This device does not support resource estimation.")

    return estimate_resources(req.task_payload, task_type, req.shots)

@app.get("/qdi/v1/devices/mock/tasks/{task_id}/status")
def monitor(task_id: str):
    require_discovered()
    require_authenticated()
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
    require_discovered()
    require_authenticated()
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
    host = os.environ.get("QDI_API_HOST", "0.0.0.0")
    port = int(os.environ.get("QDI_API_PORT", "8000"))
    print(f"Starting QDI Demo Server on http://{host}:{port} ...")
    uvicorn.run(app, host=host, port=port)
