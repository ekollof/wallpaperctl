from wallpaperctl.set.xfce import XfceSetter


def test_monitor_keys_merge_connected_and_existing():
    s = XfceSetter()
    connected = ["eDP-1", "DP-8", "DP-9"]
    props = [
        "/backdrop/screen0/monitoreDP-1/workspace0/last-image",
        "/backdrop/screen0/monitorDP-1-1/workspace0/last-image",  # stale dock
        "/backdrop/screen0/monitorDP-1-1/workspace1/image-path",
    ]
    keys = s._monitor_keys(connected, props)
    assert keys[0] == "monitoreDP-1"
    assert "monitorDP-8" in keys
    assert "monitorDP-9" in keys
    assert "monitorDP-1-1" in keys  # still updated for re-plug of old name


def test_workspace_ids_from_props():
    s = XfceSetter()
    props = [
        "/backdrop/screen0/monitoreDP-1/workspace0/last-image",
        "/backdrop/screen0/monitoreDP-1/workspace2/last-image",
    ]
    # May also pick up real xfwm4 count on the host; ensure at least 0 and 2
    ids = s._workspace_ids(props)
    assert "0" in ids
    assert "2" in ids
