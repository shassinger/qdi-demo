#ifndef QDI_H
#define QDI_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include <stdint.h>

// QDI status return codes
typedef enum {
    QDI_SUCCESS = 0,
    QDI_ERROR_INVALID_ARGUMENT = 1,
    QDI_ERROR_UNAUTHORIZED = 2,
    QDI_ERROR_CONNECTION_FAILED = 3,
    QDI_ERROR_TASK_NOT_FOUND = 4,
    QDI_ERROR_UNSUPPORTED_FORMAT = 5,
    QDI_ERROR_HARDWARE_FAULT = 6,
    QDI_ERROR_ESTIMATION_FAILED = 7,
    QDI_ERROR_UNKNOWN = 99
} qdi_status;

// QDI Task execution states
typedef enum {
    QDI_TASK_QUEUED = 0,
    QDI_TASK_EXECUTING = 1,
    QDI_TASK_COMPLETED = 2,
    QDI_TASK_FAULTED = 3,
    QDI_TASK_CANCELLED = 4
} qdi_task_status;

// Opaque device handle
typedef struct qdi_device* qdi_device_handle;

/**
 * @brief Discover the device properties, capabilities, and configurations.
 * 
 * @param device The device handle.
 * @param descriptor_json_out Buffer to store the JSON string detailing device descriptors.
 * @param max_len Size of the output buffer.
 * @return qdi_status QDI_SUCCESS if successful.
 */
qdi_status qdi_discover(
    qdi_device_handle device,
    char* descriptor_json_out,
    size_t max_len
);

/**
 * @brief Authenticate and establish trust between Host and Device.
 * 
 * @param device The device handle.
 * @param credentials_json Credentials JSON string (e.g., tokens, keys).
 * @return qdi_status QDI_SUCCESS if authentication succeeded.
 */
qdi_status qdi_authenticate(
    qdi_device_handle device,
    const char* credentials_json
);

/**
 * @brief Submit an opaque task payload to the device.
 * 
 * @param device The device handle.
 * @param task_payload Opaque bytes representing the circuit or pulse schedule.
 * @param payload_len Length of task_payload in bytes.
 * @param task_type Format/type identifier string (e.g., "openqasm3", "qir").
 * @param shots Execution shots limit.
 * @param task_id_out Buffer to write the generated unique task ID.
 * @param id_max_len Size of task_id_out buffer.
 * @return qdi_status QDI_SUCCESS on successful queuing.
 */
qdi_status qdi_send(
    qdi_device_handle device,
    const uint8_t* task_payload,
    size_t payload_len,
    const char* task_type,
    uint32_t shots,
    char* task_id_out,
    size_t id_max_len
);

/**
 * @brief Query the status of a submitted task.
 * 
 * @param device The device handle.
 * @param task_id Unique task ID string.
 * @param status_out Pointer to write the task status enum.
 * @param advisory_json_out Buffer to write optional advisory metadata (e.g. queue position).
 * @param advisory_max_len Size of advisory_json_out buffer.
 * @return qdi_status QDI_SUCCESS if status retrieved successfully.
 */
qdi_status qdi_monitor(
    qdi_device_handle device,
    const char* task_id,
    qdi_task_status* status_out,
    char* advisory_json_out,
    size_t advisory_max_len
);

/**
 * @brief Retrieve execution results for a completed task.
 * 
 * @param device The device handle.
 * @param task_id Unique task ID string.
 * @param result_payload_out Buffer to store the opaque result payload (JSON, binary counts).
 * @param max_len Size of the result buffer.
 * @param result_type_out Buffer to write the format type of the result.
 * @param type_max_len Size of the result_type buffer.
 * @return qdi_status QDI_SUCCESS if result was retrieved successfully.
 */
qdi_status qdi_receive(
    qdi_device_handle device,
    const char* task_id,
    char* result_payload_out,
    size_t max_len,
    char* result_type_out,
    size_t type_max_len
);

/**
 * @brief Dry-run a task to estimate required resources or cost.
 * 
 * @param device The device handle.
 * @param task_payload Opaque bytes representing the circuit or pulse schedule.
 * @param payload_len Length of task_payload in bytes.
 * @param task_type Format/type identifier string.
 * @param estimation_json_out Buffer to store the estimation JSON string response.
 * @param max_len Size of the estimation buffer.
 * @return qdi_status QDI_SUCCESS if estimation succeeded.
 */
qdi_status qdi_estimate_resources(
    qdi_device_handle device,
    const uint8_t* task_payload,
    size_t payload_len,
    const char* task_type,
    char* estimation_json_out,
    size_t max_len
);

#ifdef __cplusplus
}
#endif

#endif // QDI_H
