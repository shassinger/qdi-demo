#include "qdi.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <unordered_map>
#include <string>

struct task_info {
    int qubits;
    int shots;
    int seed;
};

// Concrete structure for mock device
struct qdi_device {
    bool authenticated;
    std::unordered_map<std::string, qdi_task_status> task_statuses;
    std::unordered_map<std::string, int> poll_counts;
    std::unordered_map<std::string, task_info> task_infos;
};

// Simple QASM qubit parser helper
int parse_qubits(const std::string& qasm) {
    size_t pos = qasm.find("qubit[");
    if (pos == std::string::npos) {
        pos = qasm.find("qreg ");
    }
    if (pos != std::string::npos) {
        size_t start = qasm.find_first_of("0123456789", pos);
        if (start != std::string::npos) {
            size_t end = qasm.find_first_not_of("0123456789", start);
            if (end != std::string::npos) {
                try {
                    return std::stoi(qasm.substr(start, end - start));
                } catch (...) {
                    return 5;
                }
            }
        }
    }
    return 5; // Default fallback
}

// Compute string character sum to seed RNG consistently per payload
int get_seed(const std::string& qasm) {
    int s = 0;
    for (char c : qasm) {
        s += static_cast<int>(c);
    }
    return s > 0 ? s : 1234;
}

// Exported creation function for tests/mocks
extern "C" qdi_device_handle qdi_mock_device_create() {
    qdi_device* dev = new qdi_device();
    dev->authenticated = false;
    return dev;
}

extern "C" void qdi_mock_device_free(qdi_device_handle device) {
    delete device;
}

qdi_status qdi_discover(
    qdi_device_handle device,
    char* descriptor_json_out,
    size_t max_len
) {
    if (!device || !descriptor_json_out) return QDI_ERROR_INVALID_ARGUMENT;

    const char* desc = 
        "{"
        "\"device_id\": \"mock_qdi_qubit_v1\","
        "\"supported_auth_methods\": [\"token\"],"
        "\"supported_task_types\": [\"openqasm3\", \"openqasm2\", \"qir\"],"
        "\"is_ready\": true,"
        "\"supports_estimation\": true,"
        "\"num_qubits\": 32"
        "}";

    if (strlen(desc) >= max_len) {
        return QDI_ERROR_UNKNOWN;
    }
    strncpy(descriptor_json_out, desc, max_len);
    return QDI_SUCCESS;
}

qdi_status qdi_authenticate(
    qdi_device_handle device,
    const char* credentials_json
) {
    if (!device || !credentials_json) return QDI_ERROR_INVALID_ARGUMENT;

    const char* configured_token = getenv("QDI_AUTH_TOKEN");
    const std::string expected_token = configured_token ? configured_token : "valid-token";
    const std::string credentials(credentials_json);
    const size_t token_key = credentials.find("\"token\"");
    const size_t colon = token_key == std::string::npos
        ? std::string::npos
        : credentials.find(':', token_key + 7);
    const size_t value_start = colon == std::string::npos
        ? std::string::npos
        : credentials.find_first_not_of(" \t\r\n", colon + 1);
    const size_t value_end = value_start == std::string::npos || credentials[value_start] != '"'
        ? std::string::npos
        : credentials.find('"', value_start + 1);

    if (
        value_end != std::string::npos
        && credentials.substr(value_start + 1, value_end - value_start - 1) == expected_token
    ) {
        device->authenticated = true;
        return QDI_SUCCESS;
    }

    return QDI_ERROR_UNAUTHORIZED;
}

qdi_status qdi_send(
    qdi_device_handle device,
    const uint8_t* task_payload,
    size_t payload_len,
    const char* task_type,
    uint32_t shots,
    char* task_id_out,
    size_t id_max_len
) {
    if (!device || !task_payload || !task_type || !task_id_out) {
        return QDI_ERROR_INVALID_ARGUMENT;
    }

    if (!device->authenticated) {
        return QDI_ERROR_UNAUTHORIZED;
    }

    // Generate a simple task ID
    int rand_id = rand() % 9000 + 1000;
    snprintf(task_id_out, id_max_len, "task-%d", rand_id);

    std::string tid(task_id_out);
    device->task_statuses[tid] = QDI_TASK_QUEUED;
    device->poll_counts[tid] = 0;

    // Parse info from payload string
    std::string qasm(reinterpret_cast<const char*>(task_payload), payload_len);
    task_info info;
    info.qubits = parse_qubits(qasm);
    if (info.qubits < 1) info.qubits = 1;
    if (info.qubits > 32) info.qubits = 32;
    info.shots = (shots > 0) ? shots : 100;
    info.seed = get_seed(qasm);

    device->task_infos[tid] = info;

    return QDI_SUCCESS;
}

qdi_status qdi_monitor(
    qdi_device_handle device,
    const char* task_id,
    qdi_task_status* status_out,
    char* advisory_json_out,
    size_t advisory_max_len
) {
    if (!device || !task_id || !status_out) return QDI_ERROR_INVALID_ARGUMENT;

    std::string tid(task_id);
    if (device->task_statuses.find(tid) == device->task_statuses.end()) {
        return QDI_ERROR_TASK_NOT_FOUND;
    }

    // Transition state based on how many times polled
    int count = device->poll_counts[tid]++;
    if (count >= 2) {
        device->task_statuses[tid] = QDI_TASK_COMPLETED;
    } else if (count == 1) {
        device->task_statuses[tid] = QDI_TASK_EXECUTING;
    } else {
        device->task_statuses[tid] = QDI_TASK_QUEUED;
    }

    *status_out = device->task_statuses[tid];

    if (advisory_json_out && advisory_max_len > 0) {
        snprintf(advisory_json_out, advisory_max_len, 
                 "{\"queue_position\": %d}", (2 - count) > 0 ? (2 - count) : 0);
    }

    return QDI_SUCCESS;
}

qdi_status qdi_receive(
    qdi_device_handle device,
    const char* task_id,
    char* result_payload_out,
    size_t max_len,
    char* result_type_out,
    size_t type_max_len
) {
    if (!device || !task_id || !result_payload_out || !result_type_out) {
        return QDI_ERROR_INVALID_ARGUMENT;
    }

    std::string tid(task_id);
    if (device->task_statuses.find(tid) == device->task_statuses.end()) {
        return QDI_ERROR_TASK_NOT_FOUND;
    }

    if (device->task_statuses[tid] != QDI_TASK_COMPLETED) {
        return QDI_ERROR_UNKNOWN;
    }

    task_info info = device->task_infos[tid];
    
    // Seed the RNG deterministically per payload so results are consistent for same input
    srand(info.seed);

    std::string state0(info.qubits, '0');
    std::string state1(info.qubits, '1');

    std::string state2 = "";
    std::string state3 = "";
    for (int i = 0; i < info.qubits; i++) {
        state2 += (rand() % 2 == 0) ? '0' : '1';
        state3 += (rand() % 2 == 0) ? '0' : '1';
    }

    // Divide shots among 4 states
    int c0 = rand() % info.shots;
    int c1 = rand() % (info.shots - c0);
    int c2 = (info.shots - c0 - c1 > 0) ? rand() % (info.shots - c0 - c1) : 0;
    int c3 = info.shots - c0 - c1 - c2;
    if (c3 < 0) c3 = 0;

    std::string json = "{";
    char buf[256];
    if (c0 > 0) {
        snprintf(buf, sizeof(buf), "\"%s\": %d", state0.c_str(), c0);
        json += buf;
    }
    if (c1 > 0) {
        if (json.length() > 1) json += ", ";
        snprintf(buf, sizeof(buf), "\"%s\": %d", state1.c_str(), c1);
        json += buf;
    }
    if (c2 > 0 && state2 != state0 && state2 != state1) {
        if (json.length() > 1) json += ", ";
        snprintf(buf, sizeof(buf), "\"%s\": %d", state2.c_str(), c2);
        json += buf;
    }
    if (c3 > 0 && state3 != state0 && state3 != state1 && state3 != state2) {
        if (json.length() > 1) json += ", ";
        snprintf(buf, sizeof(buf), "\"%s\": %d", state3.c_str(), c3);
        json += buf;
    }
    json += "}";

    const char* rtype = "counts";

    if (json.length() >= max_len || strlen(rtype) >= type_max_len) {
        return QDI_ERROR_UNKNOWN;
    }

    strncpy(result_payload_out, json.c_str(), max_len);
    strncpy(result_type_out, rtype, type_max_len);

    return QDI_SUCCESS;
}

qdi_status qdi_estimate_resources(
    qdi_device_handle device,
    const uint8_t* task_payload,
    size_t payload_len,
    const char* task_type,
    char* estimation_json_out,
    size_t max_len
) {
    if (!device || !task_payload || !task_type || !estimation_json_out) {
        return QDI_ERROR_INVALID_ARGUMENT;
    }

    const char* est = 
        "{"
        "\"shots_duration_sec\": 0.05,"
        "\"logical_depth\": 3,"
        "\"estimated_cost_usd\": 0.0"
        "}";

    if (strlen(est) >= max_len) {
        return QDI_ERROR_UNKNOWN;
    }

    strncpy(estimation_json_out, est, max_len);
    return QDI_SUCCESS;
}
