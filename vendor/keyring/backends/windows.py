"""
vendor/keyring/backends/windows.py
Windows Credential Manager backend using ctypes (no compiled extensions).
Targets the Win32 CredRead / CredWrite / CredDelete API.
"""

import sys
import ctypes
import ctypes.wintypes
from typing import Optional

from .base import BaseKeyring
from ..errors import KeyringError, PasswordDeleteError

# Only import advapi32 on Windows
if sys.platform == "win32":
    _advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
else:
    _advapi32 = None

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags",              ctypes.wintypes.DWORD),
        ("Type",               ctypes.wintypes.DWORD),
        ("TargetName",         ctypes.wintypes.LPWSTR),
        ("Comment",            ctypes.wintypes.LPWSTR),
        ("LastWritten",        ctypes.wintypes.FILETIME),
        ("CredentialBlobSize", ctypes.wintypes.DWORD),
        ("CredentialBlob",     ctypes.wintypes.LPBYTE),
        ("Persist",            ctypes.wintypes.DWORD),
        ("AttributeCount",     ctypes.wintypes.DWORD),
        ("Attributes",         ctypes.c_void_p),
        ("TargetAlias",        ctypes.wintypes.LPWSTR),
        ("UserName",           ctypes.wintypes.LPWSTR),
    ]


class WindowsKeyring(BaseKeyring):

    def is_available(self) -> bool:
        return sys.platform == "win32" and _advapi32 is not None

    def _target(self, service: str, username: str) -> str:
        return f"{service}:{username}"

    def get_password(self, service: str, username: str) -> Optional[str]:
        target = self._target(service, username)
        p_cred = ctypes.pointer(_CREDENTIAL())
        try:
            ok = _advapi32.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(p_cred))
            if not ok:
                return None
            cred = p_cred.contents
            blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            return blob.decode("utf-16-le")
        except OSError as exc:
            raise KeyringError(f"Windows CredRead failed: {exc}") from exc
        finally:
            try:
                _advapi32.CredFree(p_cred)
            except Exception:
                pass

    def set_password(self, service: str, username: str, password: str) -> None:
        target = self._target(service, username)
        blob = password.encode("utf-16-le")
        cred = _CREDENTIAL()
        cred.Type               = CRED_TYPE_GENERIC
        cred.TargetName         = target
        cred.UserName           = username
        cred.CredentialBlobSize = len(blob)
        cred.CredentialBlob     = ctypes.cast(
            ctypes.create_string_buffer(blob), ctypes.wintypes.LPBYTE
        )
        cred.Persist            = CRED_PERSIST_LOCAL_MACHINE
        try:
            ok = _advapi32.CredWriteW(ctypes.byref(cred), 0)
            if not ok:
                raise KeyringError(f"Windows CredWrite failed for target={target!r}")
        except OSError as exc:
            raise KeyringError(f"Windows CredWrite failed: {exc}") from exc

    def delete_password(self, service: str, username: str) -> None:
        target = self._target(service, username)
        try:
            ok = _advapi32.CredDeleteW(target, CRED_TYPE_GENERIC, 0)
            if not ok:
                raise PasswordDeleteError(
                    f"Credential not found: service={service!r} username={username!r}"
                )
        except OSError as exc:
            raise KeyringError(f"Windows CredDelete failed: {exc}") from exc
