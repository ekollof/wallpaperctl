from pathlib import Path

from wallpaperctl import notify


def test_safe_notify_does_not_raise(monkeypatch):
    monkeypatch.setattr(notify, "_dbus_notify", lambda *a, **k: False)
    notify.safe_notify("Title", "Body")


def test_packaged_icon_exists():
    icon = notify.notification_icon()
    assert icon
    if icon.startswith("/"):
        assert Path(icon).is_file()
        assert icon.endswith(".png")


def test_dbus_notify_signature_builds():
    try:
        from jeepney import DBusAddress, new_method_call
    except ImportError:
        return

    addr = DBusAddress(
        "/org/freedesktop/Notifications",
        bus_name="org.freedesktop.Notifications",
        interface="org.freedesktop.Notifications",
    )
    hints = {
        "urgency": ("y", 1),
        "image-path": ("s", "/tmp/icon.png"),
    }
    msg = new_method_call(
        addr,
        "Notify",
        "susssasa{sv}i",
        ("wallpaperctl", 0, "/tmp/icon.png", "t", "b", [], hints, 1000),
    )
    assert msg.body[0] == "wallpaperctl"
    assert msg.body[2] == "/tmp/icon.png"
