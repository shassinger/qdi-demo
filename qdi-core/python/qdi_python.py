import ctypes
import os
import json
from ctypes import c_char_p, c_size_t, c_uint32, c_int, POINTER, Structure, c_void_p

# Load QDI library
_lib_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "libqdi_mock.dylib")
if not os.path.exists(_lib_path):
    # Try .so if not dylib (e.g., Linux fallback)
    _lib_path = _lib_path.replace(".dylib", ".so")

try:
    _lib = ctypes.CDLL(_lib_path)
except Exception as e:
    _lib = None

# Typedefs
qdi_device_handle = c_void_p

# Setup function signatures if library loaded
if _lib:
    # qdi_mock_device_create
    _lib.qdi_mock_device_create.argtypes = []
    _lib.qdi_mock_device_create.restype = qdi_device_handle

    # qdi_mock_device_free
    _lib.qdi_mock_device_free.argtypes = [qdi_device_handle]
    _lib.qdi_mock_device_free.restype = None

    # qdi_discover
    _lib.qdi_discover.argtypes = [qdi_device_handle, c_char_p, c_size_t]
    _lib.qdi_discover.restype = c_int

    # qdi_authenticate
    _lib.qdi_authenticate.argtypes = [qdi_device_handle, c_char_p]
    _lib.qdi_authenticate.restype = c_int

    # qdi_send
    _lib.qdi_send.argtypes = [qdi_device_handle, POINTER(ctypes.c_ubyte), c_size_t, c_char_p, c_uint32, c_char_p, c_size_t]
    _lib.qdi_send.restype = c_int

    # qdi_monitor
    _lib.qdi_monitor.argtypes = [qdi_device_handle, c_char_p, POINTER(c_int), c_char_p, c_size_t]
    _lib.qdi_monitor.restype = c_int

    # qdi_receive
    _lib.qdi_receive.argtypes = [qdi_device_handle, c_char_p, c_char_p, c_size_t, c_char_p, c_size_t]
    _lib.qdi_receive.restype = c_int

    # qdi_estimate_resources
    _lib.qdi_estimate_resources.argtypes = [qdi_device_handle, POINTER(ctypes.c_ubyte), c_size_t, c_char_p, c_char_p, c_size_t]
    _lib.qdi_estimate_resources.restype = c_int


class QDIError(Exception):
    """Exception raised for QDI errors."""
    def __init__(self, code):
        self.code = code
        super().__init__(f"QDI function failed with status code {code}")


class QdiClient:
    """Python wrapper for QDI C-ABI client."""
    
    def __init__(self, device_handle=None):
        if not _lib:
            raise RuntimeError(f"QDI shared library not found at {_lib_path}. Build it first.")
        if device_handle is None:
            self.device = _lib.qdi_mock_device_create()
            self._own_device = True
        else:
            self.device = device_handle
            self._own_device = False

    def __del__(self):
        if hasattr(self, '_own_device') and self._own_device and self.device and _lib:
            _lib.qdi_mock_device_free(self.device)

    def discover(self) -> dict:
        buf = ctypes.create_string_buffer(4096)
        res = _lib.qdi_discover(self.device, buf, len(buf))
        if res != 0:
            raise QDIError(res)
        return json.loads(buf.value.decode("utf-8"))

    def authenticate(self, credentials_dict: dict) -> None:
        creds_str = json.dumps(credentials_dict).encode("utf-8")
        res = _lib.qdi_authenticate(self.device, creds_str)
        if res != 0:
            raise QDIError(res)

    def send(self, task_payload: bytes, task_type: str, shots: int = 100) -> str:
        payload_len = len(task_payload)
        payload_arr = (ctypes.c_ubyte * payload_len)(*task_payload)
        id_buf = ctypes.create_string_buffer(128)
        
        res = _lib.qdi_send(
            self.device,
            payload_arr,
            payload_len,
            task_type.encode("utf-8"),
            shots,
            id_buf,
            len(id_buf)
        )
        if res != 0:
            raise QDIError(res)
        return id_buf.value.decode("utf-8")

    def monitor(self, task_id: str) -> tuple[int, dict]:
        status_val = c_int(0)
        advisory_buf = ctypes.create_string_buffer(1024)
        
        res = _lib.qdi_monitor(
            self.device,
            task_id.encode("utf-8"),
            ctypes.byref(status_val),
            advisory_buf,
            len(advisory_buf)
        )
        if res != 0:
            raise QDIError(res)
        
        advisory_str = advisory_buf.value.decode("utf-8")
        advisory = json.loads(advisory_str) if advisory_str else {}
        return status_val.value, advisory

    def receive(self, task_id: str) -> tuple[str, str]:
        res_buf = ctypes.create_string_buffer(4096)
        type_buf = ctypes.create_string_buffer(128)
        
        res = _lib.qdi_receive(
            self.device,
            task_id.encode("utf-8"),
            res_buf,
            len(res_buf),
            type_buf,
            len(type_buf)
        )
        if res != 0:
            raise QDIError(res)
            
        return res_buf.value.decode("utf-8"), type_buf.value.decode("utf-8")

    def estimate_resources(self, task_payload: bytes, task_type: str) -> dict:
        payload_len = len(task_payload)
        payload_arr = (ctypes.c_ubyte * payload_len)(*task_payload)
        est_buf = ctypes.create_string_buffer(4096)
        
        res = _lib.qdi_estimate_resources(
            self.device,
            payload_arr,
            payload_len,
            task_type.encode("utf-8"),
            est_buf,
            len(est_buf)
        )
        if res != 0:
            raise QDIError(res)
            
        return json.loads(est_buf.value.decode("utf-8"))
