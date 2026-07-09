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

## Quick Start: GitHub Codespaces (Zero Setup)

1. Click the **Open in GitHub Codespaces** button in your repository (or select **Create Codespace** from the Code dropdown).
2. The environment will automatically:
   * Build the C++ core library inside the container.
   * Install python package dependencies (`fastapi`, `uvicorn`, `qiskit`, `qiskit-aer`, `pyqir`).
   * Start both backend API (Port 8000) and Web Console (Port 3000) servers.
3. Once the Codespace boots, a notification will pop up. Click **Open in Browser** for **Port 3000** to load the web interface.
4. On the Ports tab, ensure **Port 8000** visibility is set to **Public** to allow CORS API calls.

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
pip install fastapi uvicorn httpx qiskit qiskit-aer pyqir
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

### Hosted Dev Server
The same launcher used by Codespaces can run on a hosted development machine,
such as a Mac mini on your LAN:

```bash
bash .devcontainer/start.sh
```

By default this starts the API on `0.0.0.0:8000` and the web console on
`0.0.0.0:3000`. From another machine on the same network, open:

```text
http://<host-name-or-ip>:3000
```

The web console automatically calls the API at the same host on port `8000`.
If you need custom ports:

```bash
QDI_API_PORT=8003 QDI_WEB_PORT=8004 bash .devcontainer/start.sh
```

Then open:

```text
http://<host-name-or-ip>:8004?api=http://<host-name-or-ip>:8003
```

### Mock Device Configuration
The demo device descriptor is configured by:

```text
qdi-core/python/mock_device_config.json
```

Use this file to set device characteristics such as:

* `num_qubits`
* `max_shots`
* `supported_task_types`
* `supported_auth_methods`
* `supports_estimation`
* estimation timing/cost coefficients

To run with a different config without editing the default file:

```bash
QDI_DEVICE_CONFIG=/path/to/device.json bash .devcontainer/start.sh
```

The API uses the configured capabilities for `discover`, task-format
validation, shot-limit validation, qubit-limit validation, and resource
estimation.

---

## Protocol Execution Guide

1. **Discover:** Click **Query** under *1. Discover Device* to trigger `qdi_discover`. The backend returns supported formats (`openqasm3`, `qir`) and available qubits.
2. **Authenticate:** Click **Establish Trust** to run `qdi_authenticate`. This validates the session token and enables job submission.
3. **Execute:** Choose a template from the dropdown menu (e.g. *QIR Bell State* or *PNNL QAOA*), configure the shots, and click **Send Payload** to trigger `qdi_send`.
4. **Monitor & Receive:** The console automatically polls `qdi_monitor` tracking the job state (`QUEUED` ➜ `EXECUTING` ➜ `COMPLETED`), fetches the results via `qdi_receive`, and animates a probability histogram of the physical simulation.
