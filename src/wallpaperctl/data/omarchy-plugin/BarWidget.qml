import QtQuick
import QtQuick.Dialogs
import Quickshell
import qs.Commons
import qs.Commons as Commons
import qs.Ui

Panel {
  id: root
  moduleName: "io.github.ekollof.wallpaperctl"
  manageIpc: false
  property var shell: null
  property var manifest: null
  property string omarchyPath: ""
  property var service: null
  readonly property var backend: service || (bar && bar.shell ? bar.shell.serviceFor(moduleName) : null)
  readonly property var info: backend ? backend.info : ({})
  readonly property bool busy: backend ? backend.busy : false
  readonly property bool animated: setting("animated", false) === true
  readonly property bool remote: setting("remote", false) === true
  property int selectedControl: 0

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function open(payloadJson) {
    selectedControl = 0
    controller.show()
  }

  function setPreference(key, value) {
    var entry = {id: moduleName}
    for (var name in settings) if (name !== "id") entry[name] = settings[name]
    entry[key] = value
    var api = bar ? bar.shell : shell
    if (api && api.updateEntryInline(moduleName, entry)) root.settings = entry
  }
  function activateControl() {
    if (selectedControl === 4) { close(); return }
    if (!backend || busy) return
    if (selectedControl === 0) backend.randomize(animated, remote)
    else if (selectedControl === 1) { root.close(); picker.open() }
    else if (selectedControl === 2) setPreference("animated", !animated)
    else if (selectedControl === 3) setPreference("remote", !remote)
  }
  onOpenedChanged: if (opened && backend) backend.refresh()

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰸉"
    active: root.opened || root.busy
    tooltipText: "Wallpaper · left/right click: information and controls"
    onPressed: function(mouseButton) {
      if (mouseButton === Qt.LeftButton || mouseButton === Qt.RightButton) root.toggle()
    }
  }
  FileDialog {
    id: picker
    title: "Choose wallpaper"
    fileMode: FileDialog.OpenFile
    currentFolder: root.info.library_url || "file:///"
    nameFilters: ["Wallpapers (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff *.avif *.jxl *.mp4 *.webm *.mov *.mkv)", "All files (*)"]
    onAccepted: if (root.backend) root.backend.setFile(selectedFile.toString())
  }
  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keys
    contentWidth: panel.fittedContentWidth(Style.space(360))
    contentHeight: panel.fittedContentHeight(content.implicitHeight, Style.space(650))
    PanelKeyCatcher {
      id: keys
      anchors.fill: parent
      onCloseRequested: root.close()
      onMoveRequested: function(dx, dy) { root.selectedControl = (root.selectedControl + (dy || dx) + 5) % 5 }
      onTabRequested: function(direction) { root.selectedControl = (root.selectedControl + direction + 5) % 5 }
      onActivateRequested: root.activateControl()
      Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight
        clip: true
        Column {
          id: content
          width: parent.width
          spacing: Style.spacing.sm
          Text {
            text: "Wallpaper"
            textFormat: Text.PlainText
            color: Commons.Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.subtitle
            font.bold: true
          }
          Image {
            width: parent.width
            height: visible ? Style.space(150) : 0
            visible: source.toString() !== ""
            source: root.info.preview || ""
            sourceSize.width: 720
            sourceSize.height: 300
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
          }
          Text {
            width: parent.width
            text: root.info.name || "Loading wallpaper information…"
            textFormat: Text.PlainText
            wrapMode: Text.WrapAnywhere
            color: Commons.Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.body
            font.bold: true
          }
          Text {
            width: parent.width
            text: [root.info.kind || "", root.info.dimensions || "", root.info.size ? (root.info.size / 1048576).toFixed(1) + " MiB" : ""].filter(function(x) { return x !== "" }).join(" · ") + (root.info.missing ? " · File missing" : "")
            textFormat: Text.PlainText
            color: Commons.Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
            wrapMode: Text.Wrap
          }
          Text {
            width: parent.width
            text: root.info.path || ""
            textFormat: Text.PlainText
            wrapMode: Text.WrapAnywhere
            color: Commons.Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
          }
          Text {
            width: parent.width
            visible: text !== ""
            text: root.backend ? root.backend.error : "Wallpaper service unavailable. Enable the widget using the built-in Omarchy bar."
            textFormat: Text.PlainText
            wrapMode: Text.WrapAnywhere
            color: Commons.Color.urgent
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
          }
          Button {
            width: parent.width
            text: root.busy ? "Changing wallpaper…" : "Randomize"
            iconText: "󰒟"
            enabled: !!root.backend && !root.busy
            hasCursor: root.selectedControl === 0
            onClicked: root.backend.randomize(root.animated, root.remote)
          }
          Button {
            width: parent.width
            text: "Choose wallpaper…"
            iconText: "󰉋"
            enabled: !!root.backend && !root.busy
            hasCursor: root.selectedControl === 1
            onClicked: { root.close(); picker.open() }
          }
          Toggle {
            width: parent.width
            label: "Animated"
            description: root.animated ? "Next random wallpaper: video" : "Next random wallpaper: static image"
            checked: root.animated
            enabled: !root.busy
            hasCursor: root.selectedControl === 2
            onClicked: root.setPreference("animated", !root.animated)
          }
          Toggle {
            width: parent.width
            label: "Fetch remotely"
            description: root.remote ? "Randomize fetches from configured providers" : "Randomize picks from your local library"
            checked: root.remote
            enabled: !root.busy
            hasCursor: root.selectedControl === 3
            onClicked: root.setPreference("remote", !root.remote)
          }
          Button {
            width: parent.width
            text: "Close"
            hasCursor: root.selectedControl === 4
            onClicked: root.close()
          }
        }
      }
    }
  }
}
