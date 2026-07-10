# QDI Demo Sandbox

An interactive demonstration of the Quantum Device Interface (QDI) standard.
It combines a compiled C-ABI mock device, a FastAPI wrapper, Qiskit simulation,
and a browser control panel.

The dashboard and API are served by one process on one port. The same commands
work in a local clone and in GitHub Codespaces.

## Current status

The default `main` branch is the current stable demo. It supports both local
and Codespaces startup through the same scripts, serves the dashboard and API
from one process, and includes a browser-only device library. The QDI server
still exposes one mock device; there is no device collection API.

## Run locally

Requirements:

- macOS or Linux
- Python 3.11 or newer
- a C++17 compiler (`c++`, `clang++`, or `g++`)

Clone and start the demo:

```bash
git clone https://github.com/shassinger/qdi-demo.git
cd qdi-demo
./scripts/start
```

The first start creates `.venv`, installs the pinned Python dependencies, and
builds the native mock library. Later starts reuse the environment when
`requirements.txt` is unchanged.

Open:

```text
http://127.0.0.1:8000/
```

Press Ctrl-C to stop the foreground server.

### Open `index.html` directly

You can also open `qdi-core/python/index.html` from the checkout. A page loaded
with `file://` automatically calls the local API at `http://127.0.0.1:8000`.
The server must still be running with `./scripts/start`.

To point a directly opened page at another server, add an encoded `api` query
parameter:

```text
file:///path/to/qdi-core/python/index.html?api=http://host.example:8000
```

### Background mode

```bash
./scripts/start --background
tail -f server.log
```

The process ID is stored in `server.pid`. Stop that exact process with:

```bash
kill "$(cat server.pid)"
```

### Custom host, port, or Python

```bash
QDI_API_HOST=127.0.0.1 QDI_PORT=8003 ./scripts/start
QDI_PYTHON=python3.12 ./scripts/bootstrap
```

Custom ports also work with a directly opened dashboard:

```text
file:///path/to/index.html?api=http://127.0.0.1:8003
```

## Run in GitHub Codespaces

1. Open the repository on GitHub.
2. Select **Code**, then **Codespaces**.
3. Create a Codespace from the desired branch.

The container runs `./scripts/bootstrap` once after creation and starts the
demo in the background whenever the Codespace starts. Only port `8000` is
forwarded. The dashboard and API share the same authenticated Codespaces URL,
so public port visibility is not required.

If the browser does not open automatically, open the **Ports** panel and select
the globe icon beside **QDI Demo** on port `8000`.

Useful diagnostics:

```bash
curl -i http://127.0.0.1:8000/health
tail -100 server.log
./scripts/start --background
```

Expected health response:

```json
{"status":"ok"}
```

## Demo flow

1. Click **Query** to discover the mock device.
2. Click **Establish Trust** to authenticate.
3. Choose an OpenQASM or QIR sample and set the number of shots.
4. Click **Send Payload**.
5. Watch the task move through `QUEUED`, `EXECUTING`, and `COMPLETED`.
6. Inspect the result histogram and the QDI X-Ray payload panel.

The C-ABI implementation exercises `qdi_discover`, `qdi_authenticate`,
`qdi_send`, `qdi_monitor`, `qdi_receive`, and resource estimation. Qiskit Aer
provides the server-side circuit simulation.

## Device library

Select the **Server Online** control to open the device library. The menu lists
the active device and all available presets, followed by **Configure
selected…** and **Create new…**. Selecting or creating a device resets
discovery, authentication, and task state so the next interaction begins with
a clean dashboard state.

The library is exclusively a browser-side convenience feature. Built-in
presets live in `index.html`, and custom devices are saved in browser
`localStorage`. The server and QDI protocol continue to represent exactly one
device. Selecting, creating, or editing a library entry triggers no API
request. Normal page-load setup and health monitoring continue independently,
and explicit protocol actions such as Discover, Authenticate, and task
operations contact the server. The library adds no QDI commands or API
endpoints.

Library entries are client-side profiles used by the dashboard. They do not
reconfigure the running mock server. Clicking **Query** always discovers the
server's singular device and displays the descriptor returned by that server.

The built-in collection includes the general 32-qubit mock QPU, a compact
5-qubit device, and a QIR-only 16-qubit testbed. Each entry controls values
including:

- `num_qubits`
- `max_shots`
- `supported_task_types`
- `supported_auth_methods`
- resource-estimation timing and cost coefficients

Devices created or edited in the dashboard are private to that browser origin.
Clear the site's browser storage to return to the built-in collection.

Use a single boot configuration instead of the library:

```bash
QDI_DEVICE_CONFIG=/path/to/device.json ./scripts/start
```

## Development and tests

Run the complete local test suite:

```bash
./scripts/bootstrap
.venv/bin/python qdi-core/python/test_qdi.py
.venv/bin/python -m pytest
```

GitHub Actions runs these checks on both Ubuntu and macOS and smoke-tests the
one-process launcher. Dependency versions are intentionally pinned in
`requirements.txt`; update them deliberately and verify both CI platforms.

## API endpoints

The interactive OpenAPI documentation is available at:

```text
http://127.0.0.1:8000/docs
```

The QDI demonstration operations are:

```text
GET  /qdi/v1/devices/mock/discover
POST /qdi/v1/devices/mock/authenticate
POST /qdi/v1/devices/mock/tasks
GET  /qdi/v1/devices/mock/tasks/{task_id}/status
GET  /qdi/v1/devices/mock/tasks/{task_id}/results
POST /qdi/v1/devices/mock/estimate
```

The demo harness also provides these support endpoints:

```text
GET  /health
GET  /qdi/v1/devices/mock/config
PUT  /qdi/v1/devices/mock/config
GET  /qdi/v1/circuits
```

The configuration route controls the singular mock server and is not used by
the browser device library. There is intentionally no `GET` or `POST`
collection endpoint at `/qdi/v1/devices`.
