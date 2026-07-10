import sys
from pathlib import Path

from fastapi.testclient import TestClient


PYTHON_DIR = Path(__file__).resolve().parents[1] / "qdi-core" / "python"
sys.path.insert(0, str(PYTHON_DIR))

from qdi_demo_server import app, reset_runtime_state  # noqa: E402


def test_web_console_and_qdi_lifecycle():
    reset_runtime_state()

    with TestClient(app) as client:
        console = client.get("/")
        assert console.status_code == 200
        assert "Quantum Device Interface (QDI) Control Panel" in console.text
        assert "Create new…" in console.text
        assert "qdi-demo.custom-devices.v1" in console.text

        assert client.get("/qdi/v1/devices").status_code == 404
        assert client.post("/qdi/v1/devices", json={}).status_code == 404

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
