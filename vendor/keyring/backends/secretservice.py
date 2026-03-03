"""
vendor/keyring/backends/secretservice.py
Linux SecretService backend using the `dbus` module (available in most
desktop Linux distributions without additional installs).

Falls back gracefully if dbus is unavailable (headless servers, CI, etc.).
"""

import sys
from typing import Optional

from .base import BaseKeyring
from ..errors import KeyringError, PasswordDeleteError


class SecretServiceKeyring(BaseKeyring):

    _SS_BUS   = "org.freedesktop.secrets"
    _SS_PATH  = "/org/freedesktop/secrets"
    _SS_IFACE = "org.freedesktop.Secret.Service"
    _COL_IFACE = "org.freedesktop.Secret.Collection"
    _ITEM_IFACE = "org.freedesktop.Secret.Item"

    def __init__(self) -> None:
        self._dbus = None
        self._bus  = None
        if sys.platform.startswith("linux"):
            try:
                import dbus  # type: ignore
                self._dbus = dbus
                self._bus  = dbus.SessionBus()
            except Exception:
                pass  # dbus unavailable — is_available() will return False

    def is_available(self) -> bool:
        if not sys.platform.startswith("linux") or self._dbus is None:
            return False
        try:
            self._get_service()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_password(self, service: str, username: str) -> Optional[str]:
        try:
            item = self._find_item(service, username)
            if item is None:
                return None
            secret = item.GetSecret(self._open_session())
            return bytes(secret[2]).decode("utf-8")
        except Exception as exc:
            raise KeyringError(f"SecretService get failed: {exc}") from exc

    def set_password(self, service: str, username: str, password: str) -> None:
        try:
            ss      = self._get_service()
            session = self._open_session()
            collection = self._get_default_collection(ss)

            attrs = {
                "service":  service,
                "username": username,
            }
            secret = (session, b"", self._dbus.ByteArray(password.encode("utf-8")), "text/plain")
            props  = {
                "org.freedesktop.Secret.Item.Label":      f"{service}/{username}",
                "org.freedesktop.Secret.Item.Attributes": attrs,
            }
            collection.CreateItem(props, secret, True)  # True = replace existing
        except Exception as exc:
            raise KeyringError(f"SecretService set failed: {exc}") from exc

    def delete_password(self, service: str, username: str) -> None:
        try:
            item = self._find_item(service, username)
            if item is None:
                raise PasswordDeleteError(
                    f"Credential not found: service={service!r} username={username!r}"
                )
            item.Delete()
        except PasswordDeleteError:
            raise
        except Exception as exc:
            raise KeyringError(f"SecretService delete failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_service(self):
        return self._bus.get_object(self._SS_BUS, self._SS_PATH)

    def _open_session(self):
        ss = self._get_service()
        iface = self._dbus.Interface(ss, self._SS_IFACE)
        _, session = iface.OpenSession("plain", self._dbus.String("", variant_level=1))
        return session

    def _get_default_collection(self, ss):
        iface       = self._dbus.Interface(ss, self._SS_IFACE)
        col_path, _ = iface.CreateCollection(
            {"org.freedesktop.Secret.Collection.Label": "default"}, "default"
        )
        if str(col_path) == "/":
            # Collection already exists — look it up
            col_path = iface.ReadAlias("default")
        return self._bus.get_object(self._SS_BUS, col_path)

    def _find_item(self, service: str, username: str):
        ss    = self._get_service()
        iface = self._dbus.Interface(ss, self._SS_IFACE)
        attrs = {"service": service, "username": username}
        unlocked, locked = iface.SearchItems(attrs)

        if locked:
            iface.Unlock(locked)
            unlocked, _ = iface.SearchItems(attrs)

        if not unlocked:
            return None

        return self._bus.get_object(self._SS_BUS, unlocked[0])
