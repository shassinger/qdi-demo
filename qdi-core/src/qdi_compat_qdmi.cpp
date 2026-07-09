#include "qdi.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <string>

// We assume standard QDMI definitions are available via standard headers.
// Since QDMI uses prefix-specific naming (e.g., AMAZON_BRAKET_QDMI), we define a mock
// set of types and functions here or link to the actual ones.
// To keep this adapter highly generic and compileable, we define bindings to the standard QDMI C API.

typedef void* QDMI_Session;
typedef void* QDMI_Job;

typedef enum {
    QDMI_STATUS_SUCCESS = 0,
    QDMI_STATUS_ERROR = 1
} QDMI_Status;

typedef enum {
    QDMI_JOB_STATE_CREATED = 0,
    QDMI_JOB_STATE_QUEUED = 1,
    QDMI_JOB_STATE_RUNNING = 2,
    QDMI_JOB_STATE_DONE = 3,
    QDMI_JOB_STATE_CANCELED = 4,
    QDMI_JOB_STATE_FAILED = 5
} QDMI_Job_State;

// These would be linked to the actual QDMI implementation at runtime.
// For the compilation of the adapter, we declare them as weak/external symbols.
extern "C" {
    QDMI_Status QDMI_session_alloc(QDMI_Session* session);
    QDMI_Status QDMI_session_free(QDMI_Session session);
    QDMI_Status QDMI_session_init(QDMI_Session session);
    QDMI_Status QDMI_session_set_parameter(QDMI_Session session, int param, size_t size, const void* value);
    QDMI_Status QDMI_session_query_device_property(QDMI_Session session, int prop, size_t size, void* value, size_t* sizeRet);
    QDMI_Status QDMI_session_create_device_job(QDMI_Session session, QDMI_Job* job);
    QDMI_Status QDMI_job_free(QDMI_Job job);
    QDMI_Status QDMI_job_set_parameter(QDMI_Job job, int param, size_t size, const void* value);
    QDMI_Status QDMI_job_submit(QDMI_Job job);
    QDMI_Status QDMI_job_check(QDMI_Job job, QDMI_Job_State* state);
    QDMI_Status QDMI_job_get_results(QDMI_Job job, int result_type, size_t size, void* data, size_t* sizeRet);
}

// QDI structure wrapping a QDMI session
struct qdi_device {
    QDMI_Session qdmi_session;
    bool authenticated;
};

qdi_status qdi_discover(
    qdi_device_handle device,
    char* descriptor_json_out,
    size_t max_len
) {
    if (!device || !descriptor_json_out) return QDI_ERROR_INVALID_ARGUMENT;

    // In a real implementation, we would query QDMI properties:
    // size_t qubits = 0;
    // QDMI_session_query_device_property(device->qdmi_session, QDMI_DEVICE_PROPERTY_QUBITS, sizeof(qubits), &qubits, nullptr);
    
    // For demonstration, we build a JSON describing the QDMI backend
    const char* desc = 
        "{"
        "\"device_id\": \"qdmi_compatible_device\","
        "\"supported_auth_methods\": [\"qdmi_parameters\"],"
        "\"supported_task_types\": [\"openqasm3\"],"
        "\"is_ready\": true,"
        "\"supports_estimation\": false,"
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

    // Extract authentication keys from credentials_json and set QDMI session parameters.
    // e.g. QDMI_session_set_parameter(device->qdmi_session, QDMI_SESSION_PARAMETER_AUTHFILE, ...)
    
    QDMI_Status status = QDMI_session_init(device->qdmi_session);
    if (status == QDMI_STATUS_SUCCESS) {
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

    QDMI_Job job;
    QDMI_Status status = QDMI_session_create_device_job(device->qdmi_session, &job);
    if (status != QDMI_STATUS_SUCCESS) {
        return QDI_ERROR_UNKNOWN;
    }

    // Set job parameters: program code and shots
    // QDMI_job_set_parameter(job, QDMI_JOB_PARAMETER_PROGRAM, payload_len, task_payload);
    // QDMI_job_set_parameter(job, QDMI_JOB_PARAMETER_SHOTS, sizeof(shots), &shots);

    status = QDMI_job_submit(job);
    if (status != QDMI_STATUS_SUCCESS) {
        QDMI_job_free(job);
        return QDI_ERROR_UNKNOWN;
    }

    // Store the job pointer as the task ID (cast to string)
    snprintf(task_id_out, id_max_len, "%p", job);
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

    // Parse the job pointer from the task ID
    void* job_ptr = nullptr;
    if (sscanf(task_id, "%p", &job_ptr) != 1 || !job_ptr) {
        return QDI_ERROR_TASK_NOT_FOUND;
    }
    QDMI_Job job = static_cast<QDMI_Job>(job_ptr);

    QDMI_Job_State state;
    QDMI_Status status = QDMI_job_check(job, &state);
    if (status != QDMI_STATUS_SUCCESS) {
        return QDI_ERROR_UNKNOWN;
    }

    // Map QDMI job state to QDI task status
    switch (state) {
        case QDMI_JOB_STATE_CREATED:
        case QDMI_JOB_STATE_QUEUED:
            *status_out = QDI_TASK_QUEUED;
            break;
        case QDMI_JOB_STATE_RUNNING:
            *status_out = QDI_TASK_EXECUTING;
            break;
        case QDMI_JOB_STATE_DONE:
            *status_out = QDI_TASK_COMPLETED;
            break;
        case QDMI_JOB_STATE_CANCELED:
            *status_out = QDI_TASK_CANCELLED;
            break;
        case QDMI_JOB_STATE_FAILED:
        default:
            *status_out = QDI_TASK_FAULTED;
            break;
    }

    if (advisory_json_out && advisory_max_len > 0) {
        strncpy(advisory_json_out, "{}", advisory_max_len);
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

    void* job_ptr = nullptr;
    if (sscanf(task_id, "%p", &job_ptr) != 1 || !job_ptr) {
        return QDI_ERROR_TASK_NOT_FOUND;
    }
    QDMI_Job job = static_cast<QDMI_Job>(job_ptr);

    // In a real adapter, we would fetch results from QDMI:
    // QDMI_job_get_results(job, QDMI_JOB_RESULT_COUNTS, max_len, result_payload_out, &sizeRet);
    
    // Return standard counts response format
    const char* res = "{\"0\": 512, \"1\": 512}";
    strncpy(result_payload_out, res, max_len);
    strncpy(result_type_out, "counts", type_max_len);

    // Free the job when results are retrieved
    QDMI_job_free(job);

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
    return QDI_ERROR_ESTIMATION_FAILED; // Simulators / QDMI don't support estimation by default
}
