from wallpaperctl.detect.desktop import DesktopEnvironment
from wallpaperctl.setup.deps import Kind, classify_deps, de_profile
from wallpaperctl.setup.packages import detect_package_manager


def test_de_profile_hyprland_noctalia():
    de = DesktopEnvironment(hyprland=True, noctalia=True)
    assert de_profile(de) == "hyprland+noctalia"


def test_classify_marks_python():
    de = DesktopEnvironment()
    statuses = classify_deps(de)
    py = [s for s in statuses if s.dep.kind == Kind.PYTHON]
    assert py
    assert all(s.dep.pip for s in py)


def test_package_manager_detection():
    # Just ensure it does not crash; result depends on host
    pm = detect_package_manager()
    if pm:
        assert pm.install_cmd
