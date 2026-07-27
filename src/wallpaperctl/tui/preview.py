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
    fit_cells,
    image_pixel_size,
    is_protocol_backend,
    kitty_delete_seq,
    kitty_place_png_seq,
    kitty_put_seq,
    load_png_with_size,
    render_chafa_ansi,
    render_halfblocks,
    render_sixel,
    terminal_cell_pixels,
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
        self._img_w = 0
        self._img_h = 0
        self._sixel: str | None = None
        self._tx_path: Path | None = None  # path last transmitted to kitty
        self._tx_cols = 0
        self._tx_rows = 0
        self._place_cols = 0  # aspect-correct placement size
        self._place_rows = 0
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
        self._img_w = 0
        self._img_h = 0
        self._sixel = None
        self._title = ""
        self._place_cols = 0
        self._place_rows = 0
        if self.backend == GraphicsBackend.KITTY:
            self._kitty_loaded = False
            self._tx_path = None

        if path is None or not path.is_file():
            self._title = "No selection"
            return

        cols, rows = self._cell_size()
        self._title = f"{path.name}  ·  {self.backend_label}"
        iw, ih = image_pixel_size(path)
        self._img_w, self._img_h = iw, ih
        place_c, place_r = fit_cells(iw, ih, cols, rows)
        self._place_cols, self._place_rows = place_c, place_r

        if self.use_protocol and self.backend == GraphicsBackend.KITTY:
            cell_w, cell_h = terminal_cell_pixels()
            max_w = max(200, place_c * cell_w * 2)
            max_h = max(120, place_r * cell_h * 2)
            loaded = load_png_with_size(path, max_w=max_w, max_h=max_h)
            if loaded is None:
                self._load_ansi(path, place_c, place_r)
                return
            self._png, self._img_w, self._img_h = loaded
            # Re-fit using thumbnail pixel size (same aspect)
            self._place_cols, self._place_rows = fit_cells(
                self._img_w, self._img_h, cols, rows
            )
            self._tx_cols = cols
            self._tx_rows = rows
            return

        if self.use_protocol and self.backend == GraphicsBackend.SIXEL:
            # chafa --size fits *inside* the box preserving aspect
            self._sixel = render_sixel(path, cols=place_c, rows=place_r)
            self._tx_cols = cols
            self._tx_rows = rows
            if self._sixel is None:
                self._load_ansi(path, place_c, place_r)
            return

        self._load_ansi(path, place_c, place_r)

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
        avail_cols = max(8, region.width)
        avail_rows = max(4, region.height - 1)

        # Aspect-correct placement (never force full pane c×r — that stretches)
        iw, ih = self._img_w, self._img_h
        if iw <= 0 or ih <= 0:
            iw, ih = image_pixel_size(path)
        place_c, place_r = fit_cells(iw, ih, avail_cols, avail_rows)

        try:
            if self.backend == GraphicsBackend.KITTY and self._png is not None:
                write(cursor_seq(row, col))
                need_tx = (
                    not self._kitty_loaded
                    or self._tx_path != path
                    or abs(self._tx_cols - avail_cols) > 1
                    or abs(self._tx_rows - avail_rows) > 1
                    or self._place_cols != place_c
                    or self._place_rows != place_r
                )
                if need_tx:
                    write(kitty_delete_seq())
                    write(cursor_seq(row, col))
                    write(
                        kitty_place_png_seq(
                            self._png,
                            cols=place_c,
                            rows=place_r,
                            z_index=0,
                        )
                    )
                    self._kitty_loaded = True
                    self._tx_path = path
                    self._tx_cols = avail_cols
                    self._tx_rows = avail_rows
                    self._place_cols = place_c
                    self._place_rows = place_r
                else:
                    write(
                        kitty_put_seq(
                            cols=self._place_cols,
                            rows=self._place_rows,
                            z_index=0,
                        )
                    )
            elif self.backend == GraphicsBackend.SIXEL:
                if (
                    self._sixel is None
                    or abs(avail_cols - self._tx_cols) > 2
                    or abs(avail_rows - self._tx_rows) > 2
                    or self._place_cols != place_c
                    or self._place_rows != place_r
                ):
                    self._sixel = render_sixel(path, cols=place_c, rows=place_r)
                    self._tx_cols = avail_cols
                    self._tx_rows = avail_rows
                    self._place_cols = place_c
                    self._place_rows = place_r
                if self._sixel:
                    write(cursor_seq(row, col))
                    write(self._sixel)
        except Exception:
            pass
