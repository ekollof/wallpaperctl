import QtQuick
import Quickshell.Io

Item {
  id: root
  property var shell: null
  property var manifest: null
  property string omarchyPath: ""
  property var info: ({})
  property string error: ""
  property bool ready: false
  readonly property bool busy: action.running || pendingAction.length > 0
  property var pendingAction: []
  property string statusOutput: ""

  function refresh() {
    if (status.running || action.running) return
    statusOutput = ""
    status.running = true
  }
  function run(args) {
    if (root.busy) return
    if (status.running) {
      pendingAction = args
      return
    }
    error = ""
    action.command = ["wallpaperctl"].concat(args)
    action.running = true
  }
  function randomize(animated, remote) {
    var args = [remote ? "fetch" : "random", "--sync"]
    if (animated) args.push("--animated")
    run(args)
  }
  function setFile(url) { run(["omarchy-panel", "set", url]) }

  Process {
    id: status
    command: ["wallpaperctl", "omarchy-panel", "status"]
    stdout: StdioCollector {
      onStreamFinished: root.statusOutput = text.slice(0, 32768)
    }
    onRunningChanged: if (running) statusWatchdog.restart()
    onExited: function(code, exitStatus) {
      statusWatchdog.stop()
      if (root.pendingAction.length > 0) {
        var next = root.pendingAction
        root.pendingAction = []
        root.run(next)
      }
      if (code !== 0) {
        root.ready = false
        root.error = "Could not read wallpaper information. Check wallpaperctl is installed."
        return
      }
      try {
        var data = JSON.parse(root.statusOutput)
        if (!data || typeof data.name !== "string" || typeof data.path !== "string")
          throw new Error("Invalid status")
        root.info = data
        if (!root.ready) root.error = ""
        root.ready = true
      } catch (e) {
        root.ready = false
        root.error = "Invalid wallpaper information. Retry after updating wallpaperctl."
      }
    }
  }
  Process {
    id: action
    // Wallpaperctl owns network timeouts, wallpaper locks and theme workers.
    onExited: function(code, exitStatus) {
      watchdog.stop()
      if (code !== 0 && !root.error)
        root.error = "Wallpaper change failed. Check your library or remote provider configuration, then retry."
      root.refresh()
    }
    onRunningChanged: if (running) watchdog.restart()
  }
  Timer {
    id: statusWatchdog
    interval: 15000
    onTriggered: {
      root.error = "Reading wallpaper information timed out. Please retry."
      status.running = false
    }
  }
  Timer {
    id: watchdog
    interval: 600000
    onTriggered: {
      root.error = "Wallpaper change timed out. Please retry."
      action.running = false
    }
  }
  Timer {
    interval: 10000
    repeat: true
    running: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }
  IpcHandler {
    target: "io.github.ekollof.wallpaperctl"
    function refresh(): void { root.refresh() }
    function status(): string {
      return JSON.stringify({ready: root.ready, busy: root.busy, error: root.error, info: root.info})
    }
  }
}
