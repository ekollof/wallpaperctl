"""Textual TUI: browse, preview, tag, delete, set wallpapers."""

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
from wallpaperctl.tui.tags import TagStore


class ConfirmScreen(ModalScreen[bool]):
    """Yes/No confirmation dialog."""

    CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm-box {
        width: 60;
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

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(self.message)
            with Horizontal(id="confirm-buttons"):
                yield Button("Delete", variant="error", id="yes")
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


class TagScreen(ModalScreen[str | None]):
    """Prompt for a tag name."""

    CSS = """
    TagScreen {
        align: center middle;
    }
    #tag-box {
        width: 50;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, title: str = "Add tag") -> None:
        super().__init__()
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="tag-box"):
            yield Label(self._title)
            yield Input(placeholder="tag name…", id="tag-input")
            with Horizontal(id="confirm-buttons"):
                yield Button("OK", variant="primary", id="ok")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#tag-input", Input).focus()

    @on(Button.Pressed, "#ok")
    def ok(self) -> None:
        val = self.query_one("#tag-input", Input).value.strip()
        self.dismiss(val or None)

    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None:
        self.dismiss(None)

    @on(Input.Submitted, "#tag-input")
    def submit(self) -> None:
        val = self.query_one("#tag-input", Input).value.strip()
        self.dismiss(val or None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class WallpaperListItem(ListItem):
    def __init__(self, item: WallpaperItem) -> None:
        tag_s = f" [{', '.join(item.tags)}]" if item.tags else ""
        label = f"{item.rel}{tag_s}"
        super().__init__(Label(label))
        self.item = item


class MetaPane(Static):
    DEFAULT_CSS = """
    MetaPane {
        height: auto;
        max-height: 8;
        border: solid $accent;
        padding: 0 1;
    }
    """

    def show_item(self, item: WallpaperItem | None) -> None:
        if item is None:
            self.update("[dim]Select a wallpaper[/dim]")
            return
        tags = ", ".join(item.tags) if item.tags else "—"
        self.update(
            f"[b]{item.rel}[/b]\n"
            f"Size: {item.size_label}   Dims: {item.dim_label}   "
            f"Modified: {item.mtime_label}\n"
            f"Tags: {tags}\n"
            f"[dim]{item.path}[/dim]"
        )


class ManageApp(App[None]):
    """Wallpaper library manager."""

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
        Binding("t", "add_tag", "Tag"),
        Binding("u", "untag", "Untag"),
        Binding("r", "refresh", "Refresh"),
        Binding("f", "filter_tag", "Filter tag"),
        Binding("c", "clear_filter", "Clear filter"),
        Binding("enter", "set_wallpaper", "Set", show=False),
    ]

    def __init__(
        self,
        *,
        library_root: Path,
        ops: OpsConfig,
        no_kitty: bool = False,
    ) -> None:
        super().__init__()
        self.library_root = library_root.expanduser().resolve()
        self.ops = ops
        self.no_kitty = no_kitty
        self.tags = TagStore()
        self._all: list[WallpaperItem] = []
        self._query = ""
        self._tag_filter = ""
        self._selected: WallpaperItem | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="toolbar"):
            yield Input(placeholder="Search name/tags…", id="search")
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
        self._status(f"Library: {self.library_root}  ·  preview: {backend}")

    def post_display_hook(self) -> None:
        """Paint Kitty/sixel *after* Textual draws the frame (inline graphics)."""
        try:
            pane = self.query_one("#preview", PreviewPane)
        except Exception:
            return
        driver = self._driver
        if driver is None:
            return
        # Modals (delete confirm, tag prompt) sit in the cell buffer; Kitty/sixel
        # are drawn on top afterward and would cover them unless we clear first.
        if self._modal_open():
            pane.clear_protocol(driver.write)
            return
        pane.emit_protocol(driver.write)

    def _modal_open(self) -> bool:
        """True when a ModalScreen is above the main manage screen."""
        try:
            # Base screen + any pushed overlays
            if len(self.screen_stack) > 1:
                return True
            # Current screen itself may be a modal during transition
            return isinstance(self.screen, ModalScreen)
        except Exception:
            return False

    def _status(self, msg: str) -> None:
        self.query_one("#status", Static).update(msg)

    def _reload_library(self) -> None:
        self._all = scan_library(self.library_root, self.tags, with_dimensions=True)
        self._apply_filter()

    def _apply_filter(self) -> None:
        items = filter_items(self._all, query=self._query, tag=self._tag_filter)
        lv = self.query_one("#wall-list", ListView)
        lv.clear()
        for it in items:
            lv.append(WallpaperListItem(it))
        filt = []
        if self._query:
            filt.append(f"q={self._query!r}")
        if self._tag_filter:
            filt.append(f"tag={self._tag_filter!r}")
        extra = f" ({', '.join(filt)})" if filt else ""
        self.query_one("#count-label", Label).update(f"{len(items)}/{len(self._all)}{extra}")
        if not items:
            self._selected = None
            self.query_one("#preview", PreviewPane).path = None
            self.query_one("#meta", MetaPane).show_item(None)

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

    @on(ListView.Highlighted, "#wall-list")
    def on_highlight(self, event: ListView.Highlighted) -> None:
        item = None
        if event.item is not None and isinstance(event.item, WallpaperListItem):
            item = event.item.item
        self._selected = item
        self.query_one("#meta", MetaPane).show_item(item)
        self.query_one("#preview", PreviewPane).path = item.path if item else None

    @on(ListView.Selected, "#wall-list")
    def on_selected(self, event: ListView.Selected) -> None:
        # Click / activate only selects (preview); set via `s` or Enter binding.
        if isinstance(event.item, WallpaperListItem):
            self._selected = event.item.item
            self.query_one("#meta", MetaPane).show_item(event.item.item)
            self.query_one("#preview", PreviewPane).path = event.item.item.path

    @on(Input.Changed, "#search")
    def on_search(self, event: Input.Changed) -> None:
        self._query = event.value
        self._apply_filter()

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_refresh(self) -> None:
        self.tags.load()
        self._reload_library()
        self._status("Library refreshed")

    def action_clear_filter(self) -> None:
        self._query = ""
        self._tag_filter = ""
        self.query_one("#search", Input).value = ""
        self._apply_filter()
        self._status("Filters cleared")

    def action_help(self) -> None:
        self._status(
            "Keys: / search · s set · d delete · t tag · u untag · "
            "f filter-tag · c clear-filter · r refresh · q quit"
        )

    def action_filter_tag(self) -> None:
        def done(tag: str | None) -> None:
            if tag:
                self._tag_filter = tag
                self._apply_filter()
                self._status(f"Filter tag: {tag}")

        self.push_screen(TagScreen("Filter by tag"), done)

    def action_add_tag(self) -> None:
        item = self._current_item()
        if not item:
            self._status("Nothing selected")
            return

        def done(tag: str | None) -> None:
            if not tag:
                return
            item.tags = self.tags.add(item.path, tag)
            self._reload_library()
            self._status(f"Tagged {item.name}: {', '.join(item.tags)}")

        self.push_screen(TagScreen(f"Tag {item.name}"), done)

    def action_untag(self) -> None:
        item = self._current_item()
        if not item:
            self._status("Nothing selected")
            return
        if not item.tags:
            self._status("No tags on this wallpaper")
            return
        if len(item.tags) == 1:
            item.tags = self.tags.remove(item.path, item.tags[0])
            self._reload_library()
            self._status(f"Removed tag from {item.name}")
            return

        def done(tag: str | None) -> None:
            if not tag:
                return
            item.tags = self.tags.remove(item.path, tag)
            self._reload_library()
            self._status(f"Removed tag {tag!r} from {item.name}")

        self.push_screen(
            TagScreen(f"Remove which tag? ({', '.join(item.tags)})"),
            done,
        )

    def action_delete(self) -> None:
        item = self._current_item()
        if not item:
            self._status("Nothing selected")
            return

        def done(ok: bool | None) -> None:
            if not ok:
                self._status("Delete cancelled")
                return
            try:
                item.path.unlink()
                self.tags.drop_path(item.path)
                self._status(f"Deleted {item.rel}")
            except OSError as e:
                self._status(f"Delete failed: {e}")
                return
            self._reload_library()

        self.push_screen(
            ConfirmScreen(f"Delete permanently?\n{item.path}"),
            done,
        )

    @work(thread=True)
    def action_set_wallpaper(self) -> None:
        item = self._current_item()
        if not item:
            self.call_from_thread(self._status, "Nothing selected")
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
