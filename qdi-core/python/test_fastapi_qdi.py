import sys
import os
import time

# Add paths
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "oqtopus-cloud", "backend"))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from oqtopus_cloud.user.routers.qdi import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)

def test_fastapi_qdi():
    print("Testing discover endpoint...")
    response = client.get("/qdi/v1/devices/test-qpu-1/discover")
    assert response.status_code == 200
    data = response.json()
    print("Discover Response:", data)
    assert data["device_id"] == "mock_qdi_qubit_v1"
    assert data["num_qubits"] == 5

    print("Testing task send (should be 401 unauthorized)...")
    response = client.post(
        "/qdi/v1/devices/test-qpu-1/tasks",
        json={"task_payload": "OPENQASM 3.0;", "task_type": "openqasm3", "shots": 100}
    )
    assert response.status_code == 401
    print("Received expected 401 unauthorized code.")

    print("Testing authenticate...")
    response = client.post(
        "/qdi/v1/devices/test-qpu-1/authenticate",
        json={"token": "valid-token"}
    )
    assert response.status_code == 200
    print("Authentication succeeded:", response.json())

    print("Testing task send (should now succeed)...")
    response = client.post(
        "/qdi/v1/devices/test-qpu-1/tasks",
        json={"task_payload": "OPENQASM 3.0;", "task_type": "openqasm3", "shots": 100}
    )
    assert response.status_code == 200
    send_data = response.json()
    print("Send Response:", send_data)
    task_id = send_data["task_id"]
    assert task_id.startswith("task-")

    print("Testing monitor task status...")
    for _ in range(5):
        response = client.get(f"/qdi/v1/devices/test-qpu-1/tasks/{task_id}/status")
        assert response.status_code == 200
        status_data = response.json()
        print("Status:", status_data)
        if status_data["status"] == "COMPLETED":
            print("Task completed!")
            break
        time.sleep(0.5)

    print("Testing receive results...")
    response = client.get(f"/qdi/v1/devices/test-qpu-1/tasks/{task_id}/results")
    assert response.status_code == 200
    results_data = response.json()
    print("Results:", results_data)
    assert results_data["result_type"] == "counts"
    assert "512" in results_data["result"]

    print("\n--- FASTAPI QDI ENDPOINTS TEST PASSED SUCCESSFULY! ---")

if __name__ == "__main__":
    test_fastapi_qdi()
