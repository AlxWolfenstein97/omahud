import QtQuick
import Quickshell.Io

// OmaHud service plugin.
//
// Colour retints live in bin/omahud; the theme-set hook keeps MangoHud in step
// with Omarchy. This component only re-runs the installer at shell start so the
// Style > HUD Themes menu entry and theme-set hook come back after a refresh.
Item {
    id: root

    property var shell: null
    property var manifest: null
    property string lastError: ""

    readonly property string pluginDir: {
        if (manifest && manifest.__sourceDir)
            return String(manifest.__sourceDir)
        var here = String(Qt.resolvedUrl("."))
        if (here.startsWith("file://"))
            here = here.substring(7)
        if (here.endsWith("/"))
            here = here.slice(0, -1)
        return decodeURIComponent(here)
    }

    Process {
        id: installer

        command: ["bash", root.pluginDir + "/install.sh", "--quiet"]

        stderr: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                var message = String(text || "").trim()
                if (message.length > 0)
                    root.lastError = message.length > 400 ? message.slice(-400) : message
            }
        }

        onExited: function (exitCode) {
            if (exitCode === 0)
                return
            console.warn("omahud: installer exited " + exitCode
                         + (root.lastError.length > 0 ? ": " + root.lastError : ""))
        }
    }

    Timer {
        interval: 2500
        running: true
        repeat: false
        onTriggered: {
            if (!installer.running) {
                root.lastError = ""
                installer.running = true
            }
        }
    }
}
