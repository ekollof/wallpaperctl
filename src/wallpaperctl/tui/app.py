"""Textual TUI: browse, multi-select, delete, set wallpapers."""

from __future__ import annotations

from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

from wallpaperctl.config import OpsConfig
from wallpaperctl.tui.library import WallpaperItem, filter_items, scan_library
from wallpaperctl.tui.preview import PreviewPane


class ConfirmScreen(ModalScreen[bool]):
    """Yes/No confirmation dialog."""

    CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm-box {
        width: 64;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }
    #confirm-box Label {
        width: 100%;
        margin-bottom: 1;
    }
    #confirm-buttons {
        height: auto;
        align: center middle;
    }
    #confirm-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, message: str, *, confirm_label: str = "Delete") -> None:
        super().__init__()
        self.message = message
        self.confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(self.message)
            with Horizontal(id="confirm-buttons"):
                yield Button(self.confirm_label, variant="error", id="yes")
                yield Button("Cancel", variant="primary", id="no")

    @on(Button.Pressed, "#yes")
    def yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no")
    def no(self) -> None:
        self.dismiss(False)

    def on_key(self, event) -> None:
        if event.key == "y":
            self.dismiss(True)
        elif event.key in ("n", "escape"):
            self.dismiss(False)


class WallpaperListItem(ListItem):
    """One library row; *marked* = multi-select for batch ops."""

    def __init__(self, item: WallpaperItem, *, marked: bool = False) -> None:
        self.item = item
        self.marked = marked
        super().__init__(Label(self._text()))

    def _text(self) -> str:
        # Use a clear multi-select glyph (not a search “tag”)
        mark = "● " if self.marked else "  "
        kind = "🎬 " if self.item.is_video else ""
        return f"{mark}{kind}{self.item.rel}"

    def set_marked(self, marked: bool) -> None:
        if self.marked == marked:
            return
        self.marked = marked
        try:
            self.query_one(Label).update(self._text())
        except Exception:
            pass


class MetaPane(Static):
    DEFAULT_CSS = """
    MetaPane {
        height: auto;
        max-height: 8;
        border: solid $accent;
        padding: 0 1;
    }
    """

    def show_item(
        self,
        item: WallpaperItem | None,
        *,
        marked: bool = False,
        mark_count: int = 0,
    ) -> None:
        if item is None:
            extra = f"\n[b]Marked:[/b] {mark_count}" if mark_count else ""
            self.update(f"[dim]Select a wallpaper[/dim]{extra}")
            return
        sel = "yes" if marked else "no"
        batch = f"  ·  marked set: {mark_count}" if mark_count else ""
        kind = "[b]animated video[/b]\n" if item.is_video else ""
        self.update(
            f"[b]{item.rel}[/b]\n"
            f"{kind}"
            f"Size: {item.size_label}   Dims: {item.dim_label}   "
            f"Modified: {item.mtime_label}\n"
            f"In selection: {sel}{batch}\n"
            f"[dim]{item.path}[/dim]"
        )


class ManageApp(App[None]):
    """Wallpaper library manager with multi-select batch ops."""

    TITLE = "wallpaperctl manage"
    CSS = """
    Screen {
        layout: vertical;
    }
    #toolbar {
        height: 3;
        padding: 0 1;
        dock: top;
    }
    #toolbar Input {
        width: 1fr;
        margin-right: 1;
    }
    #body {
        height: 1fr;
    }
    #list-col {
        width: 2fr;
        min-width: 30;
    }
    #preview-col {
        width: 3fr;
    }
    #status {
        height: 1;
        dock: bottom;
        background: $boost;
        color: $text;
        padding: 0 1;
    }
    ListView {
        height: 1fr;
        border: solid $primary;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "help", "Help", key_display="?"),
        Binding("slash", "focus_search", "Search", key_display="/"),
        Binding("s", "set_wallpaper", "Set"),
        Binding("d", "delete", "Delete"),
        Binding("space", "toggle_mark", "Mark", key_display="space"),
        Binding("t", "toggle_mark", "Mark", show=False),
        Binding("a", "mark_all", "Mark all"),
        Binding("u", "unmark_current", "Unmark"),
        Binding("c", "clear_marks", "Clear marks"),
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "set_wallpaper", "Set", show=False),
    ]

    def __init__(
        self,
        *,
        library_root: Path,
        ops: OpsConfig,
        no_kitty: bool = False,
        videos: bool = False,
    ) -> None:
        super().__init__()
        self.library_root = library_root.expanduser().resolve()
        self.ops = ops
        self.no_kitty = no_kitty
        self.videos = videos
        self._all: list[WallpaperItem] = []
        self._query = ""
        self._selected: WallpaperItem | None = None
        # Multi-select: resolved path strings
        self._marked: set[str] = set()
        self._warm_stop: object | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="toolbar"):
            yield Input(placeholder="Search filename…", id="search")
            yield Label("", id="count-label")
        with Horizontal(id="body"):
            with Vertical(id="list-col"):
                yield ListView(id="wall-list")
                yield MetaPane(id="meta")
            with Vertical(id="preview-col"):
                yield PreviewPane(no_kitty=self.no_kitty, id="preview")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._reload_library()
        self.query_one("#wall-list", ListView).focus()
        backend = self.query_one("#preview", PreviewPane).backend_label
        mode = "videos (frame thumbnails)" if self.videos else "images"
        self._status(
            f"Library: {self.library_root}  ·  mode: {mode}  ·  "
            f"preview: {backend}  ·  "
            f"space/t mark · d deletes selection"
        )
        self._start_cache_warm()

    def on_unmount(self) -> None:
        stop = self._warm_stop
        if stop is not None and hasattr(stop, "set"):
            stop.set()  # type: ignore[union-attr]

    def _start_cache_warm(self) -> None:
        """Background-fill Kitty PNG / sixel disk cache for the library."""
        from wallpaperctl.term_graphics import GraphicsBackend, detect_backend, have_cmd
        from wallpaperctl.tui.preview_cache import start_background_warm

        info = detect_backend(no_kitty=self.no_kitty)
        if info.backend == GraphicsBackend.KITTY:
            warm_kitty, warm_sixel = True, False
        elif info.backend == GraphicsBackend.SIXEL:
            warm_kitty, warm_sixel = False, True
        else:
            # Optional: still warm sixel if tools exist for later sessions
            if have_cmd("chafa") or have_cmd("img2sixel"):
                warm_kitty, warm_sixel = False, True
            else:
                return

        paths: list[Path] = []
        for it in self._all:
            preview = self._preview_path_for(it)
            if preview is not None and preview.is_file():
                paths.append(preview)
        if not paths:
            return

        def on_progress(i: int, n: int, path: Path) -> None:
            if i == 1 or i == n or i % 25 == 0:
                self.call_from_thread(
                    self._status,
                    f"Warming preview cache {i}/{n}: {path.name}",
                )

        def on_done(stats: dict) -> None:
            self.call_from_thread(
                self._status,
                f"Preview cache warm: png={stats.get('ok_png', 0)} "
                f"sixel={stats.get('ok_sixel', 0)} "
                f"fail={stats.get('fail', 0)}  ·  ready",
            )

        _thread, stop = start_background_warm(
            paths,
            kitty=warm_kitty,
            sixel=warm_sixel,
            on_progress=on_progress,
            on_done=on_done,
        )
        self._warm_stop = stop

    def post_display_hook(self) -> None:
        """Paint Kitty/sixel *after* Textual draws the frame (inline graphics)."""
        try:
            pane = self.query_one("#preview", PreviewPane)
        except Exception:
            return
        driver = self._driver
        if driver is None:
            return
        if self._modal_open():
            pane.clear_protocol(driver.write)
            return
        pane.emit_protocol(driver.write)

    def _modal_open(self) -> bool:
        try:
            if len(self.screen_stack) > 1:
                return True
            return isinstance(self.screen, ModalScreen)
        except Exception:
            return False

    def _status(self, msg: str) -> None:
        self.query_one("#status", Static).update(msg)

    def _key(self, path: Path) -> str:
        return str(path.expanduser().resolve())

    def _is_marked(self, item: WallpaperItem) -> bool:
        return self._key(item.path) in self._marked

    def _mark_count(self) -> int:
        return len(self._marked)

    def _targets_for_batch(self) -> list[WallpaperItem]:
        """Marked items if any, else the focused row alone."""
        if self._marked:
            by_key = {self._key(it.path): it for it in self._all}
            return [by_key[k] for k in self._marked if k in by_key]
        cur = self._current_item()
        return [cur] if cur else []

    def _refresh_meta(self) -> None:
        item = self._selected
        marked = self._is_marked(item) if item else False
        self.query_one("#meta", MetaPane).show_item(
            item, marked=marked, mark_count=self._mark_count()
        )

    def _update_count_label(self, n_visible: int) -> None:
        m = self._mark_count()
        mark_s = f"  ·  ● {m} marked" if m else ""
        q = f"  ·  q={self._query!r}" if self._query else ""
        self.query_one("#count-label", Label).update(
            f"{n_visible}/{len(self._all)}{mark_s}{q}"
        )

    def _preview_path_for(self, item: WallpaperItem | None) -> Path | None:
        """Thumbnail source: the extracted frame for videos, else the file."""
        if item is None:
            return None
        if not item.is_video:
            return item.path
        from wallpaperctl.tui.library import video_frame

        return video_frame(item.path, self.ops) or item.path

    def _reload_library(self) -> None:
        self._all = scan_library(
            self.library_root,
            tags=None,
            with_dimensions=True,
            videos=self.videos,
            ops=self.ops,
        )
        # Drop marks for files that disappeared
        alive = {self._key(it.path) for it in self._all}
        self._marked &= alive
        self._apply_filter()

    def _apply_filter(self, *, select_index: int | None = None) -> None:
        items = filter_items(self._all, query=self._query, tag="")
        lv = self.query_one("#wall-list", ListView)
        lv.clear()
        for it in items:
            lv.append(WallpaperListItem(it, marked=self._is_marked(it)))
        self._update_count_label(len(items))
        if not items:
            self._selected = None
            self.query_one("#preview", PreviewPane).path = None
            self._refresh_meta()
            return
        if select_index is not None:
            self._select_index(select_index)

    def _current_index(self) -> int | None:
        return self.query_one("#wall-list", ListView).index

    def _select_index(self, index: int) -> None:
        lv = self.query_one("#wall-list", ListView)
        n = len(lv.children)
        if n == 0:
            self._selected = None
            self.query_one("#preview", PreviewPane).path = None
            self._refresh_meta()
            return
        index = max(0, min(int(index), n - 1))
        lv.index = index
        child = lv.children[index]
        item = child.item if isinstance(child, WallpaperListItem) else None
        self._selected = item
        self.query_one("#preview", PreviewPane).path = self._preview_path_for(item)
        self._refresh_meta()
        try:
            lv.scroll_to_widget(child, animate=False)
        except Exception:
            pass

    def _current_item(self) -> WallpaperItem | None:
        lv = self.query_one("#wall-list", ListView)
        if lv.index is None:
            return None
        try:
            child = lv.children[lv.index]
        except IndexError:
            return None
        if isinstance(child, WallpaperListItem):
            return child.item
        return None

    def _current_list_item(self) -> WallpaperListItem | None:
        lv = self.query_one("#wall-list", ListView)
        if lv.index is None:
            return None
        try:
            child = lv.children[lv.index]
        except IndexError:
            return None
        return child if isinstance(child, WallpaperListItem) else None

    @on(ListView.Highlighted, "#wall-list")
    def on_highlight(self, event: ListView.Highlighted) -> None:
        item = None
        if event.item is not None and isinstance(event.item, WallpaperListItem):
            item = event.item.item
        self._selected = item
        self.query_one("#preview", PreviewPane).path = self._preview_path_for(item)
        self._refresh_meta()

    @on(ListView.Selected, "#wall-list")
    def on_selected(self, event: ListView.Selected) -> None:
        # Click only focuses/previews — does not set wallpaper or toggle mark
        if isinstance(event.item, WallpaperListItem):
            self._selected = event.item.item
            self.query_one("#preview", PreviewPane).path = self._preview_path_for(
                event.item.item
            )
            self._refresh_meta()

    @on(Input.Changed, "#search")
    def on_search(self, event: Input.Changed) -> None:
        self._query = event.value
        self._apply_filter()

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_refresh(self) -> None:
        self._reload_library()
        self._status("Library refreshed")

    def action_help(self) -> None:
        self._status(
            "space/t mark · a mark-all · u unmark · c clear-marks · "
            "d delete (marked or current) · s set · / search · q quit"
        )

    def action_toggle_mark(self) -> None:
        row = self._current_list_item()
        if not row:
            self._status("Nothing focused")
            return
        key = self._key(row.item.path)
        if key in self._marked:
            self._marked.discard(key)
            row.set_marked(False)
            self._status(f"Unmarked {row.item.name}  ({self._mark_count()} marked)")
        else:
            self._marked.add(key)
            row.set_marked(True)
            self._status(f"Marked {row.item.name}  ({self._mark_count()} marked)")
        self._update_count_label(len(self.query_one("#wall-list", ListView).children))
        self._refresh_meta()

    def action_mark_all(self) -> None:
        """Mark every row in the current (filtered) list."""
        lv = self.query_one("#wall-list", ListView)
        n = 0
        for child in lv.children:
            if isinstance(child, WallpaperListItem):
                self._marked.add(self._key(child.item.path))
                child.set_marked(True)
                n += 1
        self._update_count_label(n)
        self._refresh_meta()
        self._status(f"Marked all visible ({n})")

    def action_unmark_current(self) -> None:
        row = self._current_list_item()
        if not row:
            self._status("Nothing focused")
            return
        key = self._key(row.item.path)
        if key not in self._marked:
            self._status("Current row is not marked")
            return
        self._marked.discard(key)
        row.set_marked(False)
        self._update_count_label(len(self.query_one("#wall-list", ListView).children))
        self._refresh_meta()
        self._status(f"Unmarked {row.item.name}  ({self._mark_count()} marked)")

    def action_clear_marks(self) -> None:
        if not self._marked:
            self._status("No marks to clear")
            return
        self._marked.clear()
        lv = self.query_one("#wall-list", ListView)
        for child in lv.children:
            if isinstance(child, WallpaperListItem):
                child.set_marked(False)
        self._update_count_label(len(lv.children))
        self._refresh_meta()
        self._status("Cleared multi-selection")

    def action_delete(self) -> None:
        targets = self._targets_for_batch()
        if not targets:
            self._status("Nothing to delete (focus a row or mark some)")
            return

        idx = self._current_index()
        prev_index = 0 if idx is None else max(0, idx - 1)
        batch = len(targets) > 1 or bool(self._marked)
        if batch:
            names = "\n".join(f"  · {t.rel}" for t in targets[:12])
            more = f"\n  … and {len(targets) - 12} more" if len(targets) > 12 else ""
            msg = f"Delete {len(targets)} wallpapers permanently?\n{names}{more}"
        else:
            msg = f"Delete permanently?\n{targets[0].path}"

        def done(ok: bool | None) -> None:
            if not ok:
                self._status("Delete cancelled")
                return
            deleted = 0
            errors = 0
            for t in targets:
                try:
                    t.path.unlink()
                    self._marked.discard(self._key(t.path))
                    deleted += 1
                except OSError:
                    errors += 1
            if errors:
                self._status(f"Deleted {deleted}, failed {errors}")
            else:
                self._status(f"Deleted {deleted} wallpaper(s)")
            self._reload_library()
            self._apply_filter(select_index=prev_index)

        self.push_screen(ConfirmScreen(msg), done)

    @work(thread=True)
    def action_set_wallpaper(self) -> None:
        # Always the focused row only (not the multi-select set)
        item = self._current_item()
        if not item:
            self.call_from_thread(self._status, "Nothing focused")
            return
        if not item.path.is_file():
            self.call_from_thread(self._status, "File missing")
            return

        self.call_from_thread(self._status, f"Setting {item.name}…")
        try:
            from wallpaperctl.app import apply_wallpaper, save_current_wallpaper
            from wallpaperctl.lock import WallpaperLock

            lock = WallpaperLock()
            lock.acquire()
            try:
                save_current_wallpaper(item.path, self.ops)
                ok = apply_wallpaper(item.path, self.ops)
            finally:
                lock.release()
            if ok:
                self.call_from_thread(self._status, f"✓ Set wallpaper: {item.name}")
            else:
                self.call_from_thread(self._status, f"✗ Failed to set: {item.name}")
        except SystemExit as e:
            self.call_from_thread(self._status, f"✗ {e}")
        except Exception as e:
            self.call_from_thread(self._status, f"✗ {e}")
