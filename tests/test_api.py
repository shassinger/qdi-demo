import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient


PYTHON_DIR = Path(__file__).resolve().parents[1] / "qdi-core" / "python"
sys.path.insert(0, str(PYTHON_DIR))
DEVICE_LIBRARY_STATE = Path(tempfile.gettempdir()) / f"qdi-device-library-{uuid.uuid4().hex}.json"
os.environ["QDI_DEVICE_LIBRARY_STATE"] = str(DEVICE_LIBRARY_STATE)

from qdi_demo_server import app, reset_runtime_state  # noqa: E402


def test_web_console_and_qdi_lifecycle():
    reset_runtime_state()

    with TestClient(app) as client:
        console = client.get("/")
        assert console.status_code == 200
        assert "Quantum Device Interface (QDI) Control Panel" in console.text
        assert "Create new…" in console.text

        library = client.get("/qdi/v1/devices")
        assert library.status_code == 200
        assert library.json()["active_device_id"] == "mock_qdi_qubit_v1"
        assert {device["device_id"] for device in library.json()["devices"]} == {
            "mock_qdi_qubit_v1",
            "compact_qdi_5q",
            "qir_testbed_16q",
        }

        file_origin = client.get("/health", headers={"Origin": "null"})
        assert file_origin.status_code == 200
        assert file_origin.headers["access-control-allow-origin"] == "*"

        file_preflight = client.options(
            "/qdi/v1/devices/mock/authenticate",
            headers={
                "Origin": "null",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert file_preflight.status_code == 200
        assert file_preflight.headers["access-control-allow-origin"] == "*"
        assert "POST" in file_preflight.headers["access-control-allow-methods"]

        discovery = client.get("/qdi/v1/devices/mock/discover")
        assert discovery.status_code == 200
        assert discovery.json()["device_id"] == "mock_qdi_qubit_v1"

        authentication = client.post(
            "/qdi/v1/devices/mock/authenticate",
            json={"token": "valid-token"},
        )
        assert authentication.status_code == 200

        submission = client.post(
            "/qdi/v1/devices/mock/tasks",
            json={
                "task_payload": (
                    'OPENQASM 2.0;\ninclude "qelib1.inc";\n'
                    "qreg q[1];\ncreg c[1];\nh q[0];\nmeasure q -> c;"
                ),
                "task_type": "openqasm2",
                "shots": 100,
            },
        )
        assert submission.status_code == 200
        task_id = submission.json()["task_id"]

        statuses = []
        for _ in range(3):
            response = client.get(f"/qdi/v1/devices/mock/tasks/{task_id}/status")
            assert response.status_code == 200
            statuses.append(response.json()["status"])
        assert statuses[-1] == "COMPLETED"

        result = client.get(f"/qdi/v1/devices/mock/tasks/{task_id}/results")
        assert result.status_code == 200
        assert result.json()["result_type"] == "counts"
        assert sum(result.json()["result"].values()) == 100

        activated = client.post("/qdi/v1/devices/compact_qdi_5q/activate")
        assert activated.status_code == 200
        assert activated.json()["config"]["num_qubits"] == 5

        session_was_reset = client.post(
            "/qdi/v1/devices/mock/tasks",
            json={"task_payload": "OPENQASM 3.0;", "task_type": "openqasm3", "shots": 10},
        )
        assert session_was_reset.status_code == 409

        duplicate = client.post(
            "/qdi/v1/devices",
            json=activated.json()["config"],
        )
        assert duplicate.status_code == 409

        invalid_id = client.post(
            "/qdi/v1/devices",
            json={**activated.json()["config"], "device_id": "not a path/id"},
        )
        assert invalid_id.status_code == 422

        created = client.post(
            "/qdi/v1/devices",
            json={
                **activated.json()["config"],
                "device_id": "custom_demo_7q",
                "display_name": "Custom Demo 7-Qubit",
                "num_qubits": 7,
            },
        )
        assert created.status_code == 201
        assert created.json()["config"]["device_id"] == "custom_demo_7q"

        updated_library = client.get("/qdi/v1/devices").json()
        assert updated_library["active_device_id"] == "custom_demo_7q"
        assert len(updated_library["devices"]) == 4

        persisted_library = json.loads(DEVICE_LIBRARY_STATE.read_text(encoding="utf-8"))
        assert persisted_library["active_device_id"] == "custom_demo_7q"
        assert len(persisted_library["devices"]) == 4
