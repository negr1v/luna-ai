"""Small Windows DPAPI wrapper for local ACCIO JARVIS secrets.

The DPAPI user scope intentionally makes encrypted values unavailable when a
portable configuration is copied to a different Windows user or machine.
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes


DPAPI_PREFIX = "dpapi:v1:"
CRYPTPROTECT_UI_FORBIDDEN = 0x1


class SecretStorageError(RuntimeError):
    """Raised without including the protected or plaintext secret value."""


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def is_protected_secret(value: object) -> bool:
    return isinstance(value, str) and value.startswith(DPAPI_PREFIX)


def _to_blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    return (
        DATA_BLOB(
            len(data),
            ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
        ),
        buffer,
    )


def _crypt32():
    if not hasattr(ctypes, "windll"):
        raise SecretStorageError("Windows DPAPI is unavailable on this platform.")

    crypt32 = ctypes.windll.crypt32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(DATA_BLOB),
        wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(DATA_BLOB),
        wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    return crypt32


def _last_error(operation: str) -> SecretStorageError:
    code = ctypes.get_last_error()
    return SecretStorageError(f"Windows DPAPI {operation} failed (error {code}).")


def protect_secret(value: str) -> str:
    if not isinstance(value, str):
        raise SecretStorageError("Secret value must be text.")
    if not value:
        return ""
    if is_protected_secret(value):
        return value

    crypt32 = _crypt32()
    input_blob, _input_buffer = _to_blob(value.encode("utf-8"))
    output_blob = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(input_blob), "ACCIO JARVIS secret", None, None, None,
        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(output_blob),
    ):
        raise _last_error("encryption")

    try:
        encrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        return DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")
    finally:
        if output_blob.pbData:
            ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def unprotect_secret(value: str) -> str:
    if not is_protected_secret(value):
        raise SecretStorageError("Secret does not use the expected DPAPI format.")

    encoded = value[len(DPAPI_PREFIX):]
    try:
        encrypted = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise SecretStorageError("Protected secret data is malformed.") from exc

    crypt32 = _crypt32()
    input_blob, _input_buffer = _to_blob(encrypted)
    output_blob = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(input_blob), None, None, None, None,
        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(output_blob),
    ):
        raise _last_error("decryption")

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SecretStorageError("Protected secret text is invalid.") from exc
    finally:
        if output_blob.pbData:
            ctypes.windll.kernel32.LocalFree(output_blob.pbData)
