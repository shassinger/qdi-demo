# QDI Demo Sandbox (Quantum Device Interface)

An interactive, containerized developer sandbox designed to demonstrate the **Quantum Device Interface (QDI)** standard. QDI provides a standardized C-ABI interface separating quantum hardware control planes from classical software runtimes.

This sandbox compiles the core QDI driver libraries, launches a local FastAPI web server wrapper, and serves an interactive web dashboard for real-time protocol verification.

---

## Key Features

* **C-ABI Compliance:** Implements standard QDI functions (`qdi_discover`, `qdi_authenticate`, `qdi_send`, `qdi_monitor`, `qdi_receive`) inside a compiled C++ mock driver.
* **Hybrid Quantum Simulation:** Real backend execution of **OpenQASM (2.0/3.0)** and **QIR (LLVM Assembly)** using Qiskit Aer in the server layer.
* **PNNL QASMBench Integration:** Dynamically fetches and runs benchmark circuits (like QAOA, Toffoli, and Grover) from the public [PNNL QASMBench](https://github.com/pnnl/QASMBench) library.
* **X-Ray Payload Inspector:** A built-in debug panel in the console displaying exact API request/response JSON payloads, headers, and status codes.
* **Codespaces Integration:** Pre-configured with Dev Containers so you can spin up the entire environment in a browser in under 60 seconds.

---

## Quick Start: GitHub Codespaces Demo

This repository is designed to run as a browser-based demo with no local setup. The Codespace starts two services:

* **Web Console:** port `3000`
* **QDI Backend API:** port `8000`

### 1. Create the Codespace

1. Open this repository on GitHub.
2. Click **Code**.
3. Select the **Codespaces** tab.
4. Click **Create codespace on main**.

The dev container will automatically:

* Create a Python virtual environment.
* Install the Python dependencies (`fastapi`, `uvicorn`, `httpx`, `qiskit`, `qiskit-aer`).
* Compile the C++ mock QDI shared library.
* Start the FastAPI backend on port `8000`.
* Start the static web console on port `3000`.
* Attempt to make ports `3000` and `8000` public so the browser console can call the API.

### 2. Open the Web Console

When the Codespace finishes starting, GitHub should offer to open the forwarded `3000` port. If it does not:

1. Open the **Ports** tab in the Codespace.
2. Find **QDI Web Console** on port `3000`.
3. Click the globe/open-browser icon.

You should see the **Quantum Device Interface (QDI) Control Panel**.

### 3. Verify the Backend

The backend root URL may show:

```json
{"detail":"Not Found"}
```

That is normal. The API endpoint to test is:

```text
/qdi/v1/devices/mock/discover
```

From the Codespace terminal, run:

```bash
curl -i http://127.0.0.1:8000/qdi/v1/devices/mock/discover
```

Expected result:

```json
{
  "device_id": "mock_qdi_qubit_v1",
  "supported_auth_methods": ["token"],
  "supported_task_types": ["openqasm3", "openqasm2", "qir"],
  "is_ready": true,
  "supports_estimation": true,
  "num_qubits": 32
}
```

### 4. Check Port Visibility

The browser page on port `3000` calls the backend through the forwarded port `8000`, so both ports must be public.

The startup script tries to set this automatically. If the UI says **Server Offline** or logs `Failed to fetch`:

1. Open the **Ports** tab.
2. Right-click port `8000`.
3. Choose **Port Visibility**.
4. Select **Public**.
5. Do the same for port `3000` if needed.
6. Refresh the web console.

If an organization or account policy blocks public forwarded ports, you may need to run the demo from your own account, change the policy, or use authenticated requests to the private forwarded port.

### 5. Run the Demo Flow

1. Click **Query** in **1. Discover Device**.
2. Click **Establish Trust** in **2. Authenticate**.
3. Choose a sample circuit, such as **Bell State** or **QIR Bell State**.
4. Set the number of shots.
5. Click **Send Payload**.
6. Watch the status move through `QUEUED`, `EXECUTING`, and `COMPLETED`.
7. Review the result histogram and the **QDI X-Ray Payload Inspector**.

The X-Ray panel shows the exact REST calls made by the client, including request bodies, response bodies, and status codes. This is the easiest way to explain the QDI protocol flow during a live demo.

### Troubleshooting Codespaces

If the web console does not load, check that the static server is running:

```bash
curl -i http://127.0.0.1:3000/
```

If the backend does not answer, check the server logs:

```bash
tail -100 server.log
tail -100 web.log
```

To restart both services manually:

```bash
bash .devcontainer/start.sh
```

The startup script writes process IDs to:

```text
server.pid
web.pid
```

---

## Local Installation & Setup

If running locally on your own machine (macOS / Linux):

### 1. Build the C++ Driver Core
Compile the QDI C-ABI mock shared library:
```bash
cd qdi-core
clang++ -shared -o libqdi_mock.so -Iinclude src/qdi_mock.cpp -std=c++17 -fPIC
```
*(On macOS, compile to `.dylib` instead of `.so`)*

### 2. Set Up Virtual Environment & Dependencies
Initialize your virtual environment and install dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn httpx qiskit qiskit-aer
```

### 3. Launch the API & Web Servers
Run the FastAPI wrapper server:
```bash
python qdi-core/python/qdi_demo_server.py
```
To serve the static web dashboard on port 3000:
```bash
python -m http.server 3000 --directory qdi-core/python
```

Open your browser and navigate to `http://127.0.0.1:3000` to interact with the device.

---

## Protocol Execution Guide

1. **Discover:** Click **Query** under *1. Discover Device* to trigger `qdi_discover`. The backend returns supported formats (`openqasm3`, `qir`) and available qubits.
2. **Authenticate:** Click **Establish Trust** to run `qdi_authenticate`. This validates the session token and enables job submission.
3. **Execute:** Choose a template from the dropdown menu (e.g. *QIR Bell State* or *PNNL QAOA*), configure the shots, and click **Send Payload** to trigger `qdi_send`.
4. **Monitor & Receive:** The console automatically polls `qdi_monitor` tracking the job state (`QUEUED` ➜ `EXECUTING` ➜ `COMPLETED`), fetches the results via `qdi_receive`, and animates a probability histogram of the physical simulation.
