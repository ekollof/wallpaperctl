"""Preview widget: Kitty/sixel protocol paint after Textual frames, else ANSI."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from wallpaperctl.term_graphics import (
    GraphicsBackend,
    cursor_seq,
    detect_backend,
    is_protocol_backend,
    kitty_delete_seq,
    kitty_place_png_seq,
    kitty_put_seq,
    load_png_bytes,
    render_chafa_ansi,
    render_halfblocks,
    render_sixel,
)


class PreviewPane(Widget):
    """Image preview.

    * **Kitty / sixel** — widget cells stay blank; the app's ``post_display_hook``
      calls :meth:`emit_protocol` so the terminal paints the image *after*
      Textual's frame (true inline graphics).
    * **chafa / halfblocks** — Rich ``Text.from_ansi`` inside the widget.
    """

    DEFAULT_CSS = """
    PreviewPane {
        width: 1fr;
        height: 1fr;
        border: solid $primary;
        padding: 0 1;
        overflow: hidden;
    }
    """

    path: reactive[Path | None] = reactive(None, layout=False)

    def __init__(self, *, no_kitty: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.no_kitty = no_kitty
        info = detect_backend(no_kitty=no_kitty)
        self.backend = info.backend
        if info.detail:
            self.backend_label = f"{info.backend.value} ({info.detail})"
        else:
            self.backend_label = info.backend.value
        self.use_protocol = is_protocol_backend(self.backend) and not (
            no_kitty and self.backend == GraphicsBackend.KITTY
        )
        # If sixel chosen but we forced no_kitty only, still ok.
        if no_kitty and self.backend == GraphicsBackend.KITTY:
            # Re-detect without kitty
            info = detect_backend(no_kitty=True)
            self.backend = info.backend
            self.backend_label = (
                f"{info.backend.value} ({info.detail})"
                if info.detail
                else info.backend.value
            )
            self.use_protocol = is_protocol_backend(self.backend)

        self._ansi: Text | None = None
        self._title = ""
        # Protocol cache
        self._png: bytes | None = None
        self._sixel: str | None = None
        self._tx_path: Path | None = None  # path last transmitted to kitty
        self._tx_cols = 0
        self._tx_rows = 0
        self._kitty_loaded = False

    def watch_path(self, path: Path | None) -> None:
        self._prepare(path)
        self.refresh()

    def on_unmount(self) -> None:
        # Best-effort cleanup when leaving the TUI
        app = self.app
        if self.backend == GraphicsBackend.KITTY and app is not None:
            driver = getattr(app, "_driver", None)
            if driver is not None:
                try:
                    driver.write(kitty_delete_seq())
                except Exception:
                    pass

    def _cell_size(self) -> tuple[int, int]:
        # Prefer content region once laid out; fall back to sensible defaults
        try:
            region = self.content_region
            cols = max(16, region.width)
            rows = max(6, region.height - 1)  # leave 1 row for title
        except Exception:
            cols, rows = 40, 18
        return cols, rows

    def _prepare(self, path: Path | None) -> None:
        self._ansi = None
        self._png = None
        self._sixel = None
        self._title = ""
        if self.backend == GraphicsBackend.KITTY:
            self._kitty_loaded = False
            self._tx_path = None

        if path is None or not path.is_file():
            self._title = "No selection"
            return

        cols, rows = self._cell_size()
        self._title = f"{path.name}  ·  {self.backend_label}"

        if self.use_protocol and self.backend == GraphicsBackend.KITTY:
            # Pixel budget roughly matches cell box
            max_w = max(200, cols * 12)
            max_h = max(120, rows * 24)
            self._png = load_png_bytes(path, max_w=max_w, max_h=max_h)
            self._tx_cols = cols
            self._tx_rows = rows
            if self._png is None:
                # Fall back to ANSI for this file
                self._load_ansi(path, cols, rows)
            return

        if self.use_protocol and self.backend == GraphicsBackend.SIXEL:
            self._sixel = render_sixel(path, cols=cols, rows=rows)
            self._tx_cols = cols
            self._tx_rows = rows
            if self._sixel is None:
                self._load_ansi(path, cols, rows)
            return

        self._load_ansi(path, cols, rows)

    def _load_ansi(self, path: Path, cols: int, rows: int) -> None:
        ansi = render_chafa_ansi(path, cols=cols, rows=rows)
        if not ansi:
            ansi = render_halfblocks(path, cols=cols, rows=rows)
        # Text.from_ansi is required — raw \\033… strings show as garbage in Textual
        self._ansi = Text.from_ansi(ansi)

    def render(self) -> Text:
        title = Text(self._title + "\n", style="bold")
        if self._ansi is not None:
            return title + self._ansi
        if self.use_protocol and (self._png is not None or self._sixel is not None):
            # Reserve blank rows so protocol graphics have a clean cell region
            cols, rows = self._cell_size()
            # Spaces (not empty) so Textual still paints the region each frame
            blank = Text("\n".join(" " * max(1, cols) for _ in range(max(1, rows))))
            hint = Text(
                f"\n[dim]inline {self.backend.value} graphics[/dim]",
                style="dim",
            )
            return title + blank + hint
        if self._title == "No selection":
            return Text("No selection", style="dim")
        return Text("(no preview)", style="dim")

    def emit_protocol(self, write) -> None:
        """Paint Kitty/sixel after Textual's frame. *write* is driver.write."""
        if not self.use_protocol:
            return
        path = self.path
        if path is None or not path.is_file():
            if self.backend == GraphicsBackend.KITTY:
                try:
                    write(kitty_delete_seq())
                except Exception:
                    pass
            return

        try:
            region = self.content_region
        except Exception:
            return
        if region.width < 4 or region.height < 3:
            return

        # 1-based terminal coords; skip title line inside content
        row = region.y + 2  # +1 for 1-based, +1 for title line
        col = region.x + 1
        cols = max(8, region.width)
        rows = max(4, region.height - 1)

        try:
            if self.backend == GraphicsBackend.KITTY and self._png is not None:
                write(cursor_seq(row, col))
                if (
                    not self._kitty_loaded
                    or self._tx_path != path
                    or self._tx_cols != cols
                    or self._tx_rows != rows
                ):
                    # (Re)transmit when path or cell box changes
                    write(kitty_delete_seq())
                    write(cursor_seq(row, col))
                    # z=0: draw above Textual cell glyphs so the image is visible
                    write(
                        kitty_place_png_seq(
                            self._png,
                            cols=cols,
                            rows=rows,
                            z_index=0,
                        )
                    )
                    self._kitty_loaded = True
                    self._tx_path = path
                    self._tx_cols = cols
                    self._tx_rows = rows
                else:
                    # Cheap re-place after Textual redraw
                    write(kitty_put_seq(cols=cols, rows=rows, z_index=0))
            elif self.backend == GraphicsBackend.SIXEL and self._sixel is not None:
                # Re-encode if size changed substantially
                if abs(cols - self._tx_cols) > 2 or abs(rows - self._tx_rows) > 2:
                    self._sixel = render_sixel(path, cols=cols, rows=rows)
                    self._tx_cols = cols
                    self._tx_rows = rows
                if self._sixel:
                    write(cursor_seq(row, col))
                    write(self._sixel)
        except Exception:
            pass
