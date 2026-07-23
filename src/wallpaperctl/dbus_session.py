"""Session-bus helpers via jeepney (no dbus-send / qdbus)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

log = logging.getLogger("wallpaperctl")


def jeepney_available() -> bool:
    try:
        import jeepney  # noqa: F401

        return True
    except ImportError:
        return False


def call(
    *,
    bus_name: str,
    path: str,
    interface: str,
    method: str,
    signature: str = "",
    body: Sequence[Any] = (),
    timeout: float = 10.0,
) -> tuple[bool, Any]:
    """
    Call a session-bus method.

    Returns (ok, body_or_error). On success body is the reply body tuple
    (or ()). On failure body is an error string.
    """
    try:
        from jeepney import DBusAddress, MessageType, new_method_call
        from jeepney.io.blocking import open_dbus_connection
    except ImportError as e:
        return False, f"jeepney not installed: {e}"

    addr = DBusAddress(path, bus_name=bus_name, interface=interface)
    msg = new_method_call(addr, method, signature, tuple(body))
    try:
        with open_dbus_connection(bus="SESSION") as conn:
            reply = conn.send_and_get_reply(msg, timeout=timeout)
        if reply.header.message_type == MessageType.method_return:
            return True, reply.body
        return False, f"error reply: {reply}"
    except Exception as e:
        log.debug("D-Bus call %s.%s failed: %s", interface, method, e)
        return False, str(e)


def emit_signal(
    *,
    path: str,
    interface: str,
    signal: str,
    signature: str = "",
    body: Sequence[Any] = (),
    timeout: float = 5.0,
) -> bool:
    """Emit a session-bus signal (best-effort)."""
    try:
        from jeepney import DBusAddress, new_signal
        from jeepney.io.blocking import open_dbus_connection
    except ImportError:
        return False

    emitter = DBusAddress(path, interface=interface)
    msg = new_signal(emitter, signal, signature, tuple(body))
    try:
        with open_dbus_connection(bus="SESSION") as conn:
            conn.send(msg)
        return True
    except Exception as e:
        log.debug("D-Bus signal %s.%s failed: %s", interface, signal, e)
        return False


def name_has_owner(bus_name: str, *, timeout: float = 3.0) -> bool:
    """True if *bus_name* is claimed on the session bus."""
    ok, body = call(
        bus_name="org.freedesktop.DBus",
        path="/org/freedesktop/DBus",
        interface="org.freedesktop.DBus",
        method="NameHasOwner",
        signature="s",
        body=(bus_name,),
        timeout=timeout,
    )
    if not ok or not body:
        return False
    return bool(body[0])


def peer_ping(
    bus_name: str,
    object_path: str = "/",
    *,
    timeout: float = 3.0,
) -> bool:
    """org.freedesktop.DBus.Peer.Ping against an object."""
    ok, _ = call(
        bus_name=bus_name,
        path=object_path,
        interface="org.freedesktop.DBus.Peer",
        method="Ping",
        signature="",
        body=(),
        timeout=timeout,
    )
    return ok
