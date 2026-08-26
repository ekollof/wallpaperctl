import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  unlinkSync,
  unwatchFile,
  watch,
  watchFile,
} from "node:fs"
import { homedir } from "node:os"
import path from "node:path"
import { env } from "node:process"
import type { TuiPlugin, TuiPluginModule } from "@opencode-ai/plugin/tui"

const THEME_FILE_NAME = "wallust.json"
const HOT_PREFIX = "wallust-hot-"

function opencodeConfigDir() {
  const xdg = env.XDG_CONFIG_HOME
  if (xdg) return path.join(xdg, "opencode")
  return path.join(homedir(), ".config", "opencode")
}

const tui: TuiPlugin = async (api, _options, meta) => {
  const themeDir = path.join(opencodeConfigDir(), "themes")
  const source = path.join(themeDir, THEME_FILE_NAME)

  let timer: ReturnType<typeof setTimeout> | undefined
  let inflight = false
  let queued = false
  let dirWatcher: ReturnType<typeof watch> | undefined

  const cleanupHotThemes = (keep: string) => {
    let files: string[] = []
    try {
      files = readdirSync(themeDir)
    } catch {
      return
    }
    for (const file of files) {
      if (!file.startsWith(HOT_PREFIX) || !file.endsWith(".json")) continue
      if (file === keep) continue
      try {
        unlinkSync(path.join(themeDir, file))
      } catch {
        // still in use or already gone
      }
    }
  }

  const apply = async () => {
    if (inflight) {
      queued = true
      return
    }
    inflight = true
    try {
      if (!existsSync(source)) return
      mkdirSync(themeDir, { recursive: true })

      // Do not theme.install("wallust.json"): that name is already loaded, so
      // install no-ops, and rewriting the same file retriggers this watcher.
      const name = `${HOT_PREFIX}${Date.now()}`
      const hotFile = path.join(themeDir, `${name}.json`)
      copyFileSync(source, hotFile)
      meta.state = "updated"
      await api.theme.install(hotFile)
      if (api.theme.has(name)) {
        api.theme.set(name)
      }
      cleanupHotThemes(`${name}.json`)
    } catch (error) {
      api.ui.toast({
        title: "wallust theme",
        message: error instanceof Error ? error.message : String(error),
        variant: "error",
      })
    } finally {
      inflight = false
      if (queued) {
        queued = false
        void apply()
      }
    }
  }

  const schedule = () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = undefined
      void apply()
    }, 200)
  }

  try {
    mkdirSync(themeDir, { recursive: true })
  } catch {
    // apply() will retry
  }

  try {
    dirWatcher = watch(themeDir, (_event, filename) => {
      const name = filename == null ? THEME_FILE_NAME : String(filename)
      if (name !== THEME_FILE_NAME) return
      schedule()
    })
  } catch {
    // watchFile below still covers mtime changes
  }

  watchFile(source, { interval: 250, persistent: true }, (curr, prev) => {
    if (curr.mtimeMs !== prev.mtimeMs || curr.size !== prev.size) schedule()
  })

  api.lifecycle.onDispose(() => {
    if (timer) clearTimeout(timer)
    dirWatcher?.close()
    unwatchFile(source)
  })
}

const plugin: TuiPluginModule & { id: string } = {
  id: "wallust.hot-reload",
  tui,
}

export default plugin
