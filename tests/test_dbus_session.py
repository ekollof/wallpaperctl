from wallpaperctl.dbus_session import call, jeepney_available, name_has_owner


def test_jeepney_available():
    assert jeepney_available() is True


def test_list_names_on_session_bus():
    ok, body = call(
        bus_name="org.freedesktop.DBus",
        path="/org/freedesktop/DBus",
        interface="org.freedesktop.DBus",
        method="ListNames",
        signature="",
        body=(),
        timeout=5.0,
    )
    # Session bus should exist on a normal desktop login
    assert ok is True
    assert body and isinstance(body[0], (list, tuple))
    assert "org.freedesktop.DBus" in body[0]


def test_name_has_owner_dbus():
    assert name_has_owner("org.freedesktop.DBus") is True
