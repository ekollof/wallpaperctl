"""Exercise the actual QML service against a fictional CLI, without a desktop."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which("quickshell"), reason="Quickshell is not installed")
@pytest.mark.parametrize("mode", ["commands", "malformed", "failure", "delete"])
def test_service_runtime(tmp_path, mode):
    source = Path(__file__).resolve().parents[1] / "src/wallpaperctl/data/omarchy-plugin"
    shutil.copy2(source / "Service.qml", tmp_path / "Service.qml")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    cli = binaries / "wallpaperctl"
    cli.write_text("""#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
if args == ['omarchy-panel', 'status']:
    time.sleep(.1)
    print('invalid' if os.environ['TEST_MODE'] == 'malformed' else
          json.dumps({'name': '<img src="https://invalid">', 'path': '/fictional/aurora.png'}))
else:
    with Path(os.environ['TEST_COMMANDS']).open('a') as f:
        f.write(json.dumps(args) + '\\n')
    time.sleep(.1)
    if args[0] == 'omarchy-panel':
        print('private credential-shaped stderr must not reach UI', file=sys.stderr)
        sys.exit(1)
""")
    cli.chmod(0o755)
    (tmp_path / "shell.qml").write_text("""import QtQuick
import Quickshell
ShellRoot {
  property int phase: 0
  property string mode: Quickshell.env("TEST_MODE")
  Service { id: backend }
  Timer {
    interval: 30; repeat: true; running: true
    onTriggered: {
      if (mode === "malformed") {
        if (backend.error) { console.log("PASS malformed"); Qt.quit() }
        return
      }
      if (mode === "failure" || mode === "delete") {
        if (phase === 0 && backend.ready) {
          if (mode === "delete") backend.deleteCurrent("/fictional/aurora.png", "1:2:3:4")
          else backend.setFile("file:///fictional/a%20%23.png")
          phase++
        } else if (phase === 1 && !backend.busy && backend.error) {
          if (backend.error.indexOf("private") >= 0) Qt.exit(1)
          else { console.log("PASS " + mode); Qt.quit() }
        }
        return
      }
      if (phase === 0) {
        backend.randomize(true, true)
        backend.randomize(false, false) // overlapping action must be ignored
        phase++
      } else if (backend.ready && !backend.busy) {
        if (backend.error) { Qt.exit(1); return }
        if (phase === 1) backend.randomize(false, false)
        else if (phase === 2) backend.randomize(true, false)
        else if (phase === 3) backend.randomize(false, true)
        else { console.log("PASS commands"); Qt.quit() }
        phase++
      }
    }
  }
}
""")
    command_log = tmp_path / "commands.jsonl"
    env = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        TEST_MODE=mode,
        TEST_COMMANDS=str(command_log),
        PATH=str(binaries) + os.pathsep + os.environ["PATH"],
    )
    result = subprocess.run(
        ["quickshell", "-p", str(tmp_path), "--no-color"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {mode}" in result.stdout + result.stderr
    if mode == "commands":
        commands = [json.loads(line) for line in command_log.read_text().splitlines()]
        assert commands == [
            ["fetch", "--animated"],
            ["random"],
            ["random", "--animated"],
            ["fetch"],
        ]
    if mode == "failure":
        assert json.loads(command_log.read_text()) == [
            "omarchy-panel",
            "set",
            "file:///fictional/a%20%23.png",
        ]
    if mode == "delete":
        assert json.loads(command_log.read_text()) == [
            "omarchy-panel", "delete", "/fictional/aurora.png", "1:2:3:4"
        ]
