import time
from qdi_python import QdiClient, QDIError

def test_full_lifecycle():
    print("Initializing QDI client...")
    client = QdiClient()

    print("Running Discover...")
    descriptor = client.discover()
    print("Descriptor:", descriptor)
    assert descriptor["device_id"] == "mock_qdi_qubit_v1"
    assert descriptor["num_qubits"] == 32

    print("Attempting Send (should fail unauthorized)...")
    try:
        client.send(b"OPENQASM 3.0;", "openqasm3")
        assert False, "Send should have failed with unauthorized status"
    except QDIError as e:
        print("Successfully caught expected error (code=2/unauthorized):", e)

    print("Running Authenticate...")
    client.authenticate({"token": "valid-token"})
    print("Authenticated successfully!")

    print("Running Send...")
    task_id = client.send(b"OPENQASM 3.0; qubit[1] q; h q[0];", "openqasm3", shots=100)
    print("Task ID generated:", task_id)

    print("Monitoring status...")
    for _ in range(5):
        status, advisory = client.monitor(task_id)
        print(f"Status code: {status}, Advisory info: {advisory}")
        if status == 2:  # COMPLETED
            print("Task completed!")
            break
        time.sleep(0.5)

    print("Receiving results...")
    result, result_type = client.receive(task_id)
    print(f"Result format: {result_type}")
    print(f"Result content: {result}")
    assert "counts" in result_type

    print("Running Resource Estimation...")
    estimation = client.estimate_resources(b"OPENQASM 3.0;", "openqasm3")
    print("Estimation:", estimation)
    assert estimation["logical_depth"] == 3

    print("\n--- ALL TESTS PASSED SUCCESSFULLY! ---")

if __name__ == "__main__":
    test_full_lifecycle()
