import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


PYTHON_DIR = Path(__file__).resolve().parents[1] / "qdi-core" / "python"
sys.path.insert(0, str(PYTHON_DIR))

from qdi_demo_server import app, reset_runtime_state  # noqa: E402
from qdi_python import QDIError, QdiClient  # noqa: E402


def test_http_qdi_client_lifecycle_and_bearer_authentication():
    reset_runtime_state()

    with TestClient(app) as transport:
        client = QdiClient(client=transport)
        descriptor = client.discover()
        assert descriptor["device_id"] == "mock_qdi_qubit_v1"

        with pytest.raises(QDIError) as error:
            client.send(b"OPENQASM 3.0;", "openqasm3")
        assert error.value.code == 2

        client.authenticate({"token": "valid-token"})
        assert client.token == "valid-token"

        task_id = client.send(
            (
                b'OPENQASM 2.0; include "qelib1.inc"; '
                b"qreg q[1]; creg c[1]; h q[0]; measure q -> c;"
            ),
            "openqasm2",
            shots=20,
        )
        for _ in range(3):
            status, _advisory = client.monitor(task_id)
        assert status == 2

        result, result_type = client.receive(task_id)
        assert result_type == "counts"
        assert sum(json.loads(result).values()) == 20

        estimate = client.estimate_resources(
            b"OPENQASM 3.0; qubit[1] q; h q[0];",
            "openqasm3",
            shots=20,
        )
        assert estimate["shots"] == 20


def test_http_qdi_client_maps_api_errors():
    reset_runtime_state()

    with TestClient(app) as transport:
        client = QdiClient(client=transport)
        client.discover()

        with pytest.raises(QDIError) as error:
            client.authenticate({"token": "not-the-token"})

        assert error.value.code == 2
        assert "invalid token" in str(error.value)
