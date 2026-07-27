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
    is_protocol_backend,
    kitty_delete_seq,
    kitty_place_png_seq,
    kitty_put_seq,
    terminal_cell_pixels,
)
from wallpaperctl.tui.preview_cache import get_preview_cache


class PreviewPane(Widget):
    """Image preview.

    * **Kitty / sixel** — widget cells stay blank; the app's ``post_display_hook``
      calls :meth:`emit_protocol` so the terminal paints the image *after*
      Textual's frame (true inline graphics).
    * **chafa / halfblocks** — Rich ``Text.from_ansi`` inside the widget.

    Encoded payloads are cached (memory LRU + ``~/.cache/wallpaperctl/previews``).
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
        if no_kitty and self.backend == GraphicsBackend.KITTY:
            info = detect_backend(no_kitty=True)
            self.backend = info.backend
            self.backend_label = (
                f"{info.backend.value} ({info.detail})"
                if info.detail
                else info.backend.value
            )
            self.use_protocol = is_protocol_backend(self.backend)

        self._cache = get_preview_cache()
        self._ansi: Text | None = None
        self._title = ""
        self._png: bytes | None = None
        self._img_w = 0
        self._img_h = 0
        self._sixel: str | None = None
        # Kitty: cache full transmit sequence so re-browse is cheap
        self._kitty_tx_seq: str | None = None
        self._tx_path: Path | None = None
        self._tx_cols = 0
        self._tx_rows = 0
        self._place_cols = 0
        self._place_rows = 0
        self._kitty_loaded = False

    def watch_path(self, path: Path | None) -> None:
        self._prepare(path)
        self.refresh()

    def on_unmount(self) -> None:
        app = self.app
        if self.backend == GraphicsBackend.KITTY and app is not None:
            driver = getattr(app, "_driver", None)
            if driver is not None:
                try:
                    driver.write(kitty_delete_seq())
                except Exception:
                    pass

    def _cell_size(self) -> tuple[int, int]:
        try:
            region = self.content_region
            cols = max(16, region.width)
            rows = max(6, region.height - 1)
        except Exception:
            cols, rows = 40, 18
        return cols, rows

    def _prepare(self, path: Path | None) -> None:
        self._ansi = None
        self._png = None
        self._img_w = 0
        self._img_h = 0
        self._sixel = None
        self._kitty_tx_seq = None
        self._title = ""
        self._place_cols = 0
        self._place_rows = 0
        # Keep kitty_loaded if same path so put-only still works after soft refresh
        if path is None or self._tx_path != path:
            if self.backend == GraphicsBackend.KITTY:
                self._kitty_loaded = False
                self._tx_path = None

        if path is None or not path.is_file():
            self._title = "No selection"
            return

        cols, rows = self._cell_size()
        self._title = f"{path.name}  ·  {self.backend_label}"
        iw, ih = self._cache.get_image_size(path)
        self._img_w, self._img_h = iw, ih
        place_c, place_r = fit_cells(iw, ih, cols, rows)
        self._place_cols, self._place_rows = place_c, place_r

        if self.use_protocol and self.backend == GraphicsBackend.KITTY:
            cell_w, cell_h = terminal_cell_pixels()
            max_w = max(200, place_c * cell_w * 2)
            max_h = max(120, place_r * cell_h * 2)
            payload = self._cache.get_png(path, max_w=max_w, max_h=max_h)
            if payload is None:
                self._load_ansi(path, place_c, place_r)
                return
            self._png = payload.data
            self._img_w, self._img_h = payload.width, payload.height
            self._place_cols, self._place_rows = fit_cells(
                self._img_w, self._img_h, cols, rows
            )
            # Pre-build transmit sequence (base64 is the expensive bit)
            self._kitty_tx_seq = kitty_place_png_seq(
                self._png,
                cols=self._place_cols,
                rows=self._place_rows,
                z_index=0,
            )
            self._tx_cols = cols
            self._tx_rows = rows
            return

        if self.use_protocol and self.backend == GraphicsBackend.SIXEL:
            self._sixel = self._cache.get_sixel(
                path, cols=place_c, rows=place_r
            )
            self._tx_cols = cols
            self._tx_rows = rows
            if self._sixel is None:
                self._load_ansi(path, place_c, place_r)
            return

        self._load_ansi(path, place_c, place_r)

    def _load_ansi(self, path: Path, cols: int, rows: int) -> None:
        ansi = self._cache.get_ansi(path, cols=cols, rows=rows)
        if not ansi:
            self._ansi = Text("(no preview)", style="dim")
            return
        self._ansi = Text.from_ansi(ansi)

    def render(self) -> Text:
        title = Text(self._title + "\n", style="bold")
        if self._ansi is not None:
            return title + self._ansi
        if self.use_protocol and (self._png is not None or self._sixel is not None):
            cols, rows = self._cell_size()
            blank = Text("\n".join(" " * max(1, cols) for _ in range(max(1, rows))))
            return title + blank
        if self._title == "No selection":
            return Text("No selection", style="dim")
        return Text("(no preview)", style="dim")

    def clear_protocol(self, write) -> None:
        """Remove Kitty image so modals/UI are not covered (sixel is ephemeral)."""
        if self.backend != GraphicsBackend.KITTY:
            return
        try:
            write(kitty_delete_seq())
        except Exception:
            pass
        # Force full retransmit when the modal closes
        self._kitty_loaded = False

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

        row = region.y + 2
        col = region.x + 1
        avail_cols = max(8, region.width)
        avail_rows = max(4, region.height - 1)

        iw, ih = self._img_w, self._img_h
        if iw <= 0 or ih <= 0:
            iw, ih = self._cache.get_image_size(path)
            self._img_w, self._img_h = iw, ih
        place_c, place_r = fit_cells(iw, ih, avail_cols, avail_rows)

        try:
            if self.backend == GraphicsBackend.KITTY and self._png is not None:
                write(cursor_seq(row, col))
                size_changed = (
                    abs(self._tx_cols - avail_cols) > 2
                    or abs(self._tx_rows - avail_rows) > 2
                    or self._place_cols != place_c
                    or self._place_rows != place_r
                )
                need_tx = (
                    not self._kitty_loaded
                    or self._tx_path != path
                    or size_changed
                    or not self._kitty_tx_seq
                )
                if need_tx:
                    if size_changed and self._tx_path == path:
                        # Rebuild sequence for new place size (PNG already cached)
                        self._kitty_tx_seq = kitty_place_png_seq(
                            self._png,
                            cols=place_c,
                            rows=place_r,
                            z_index=0,
                        )
                    write(kitty_delete_seq())
                    write(cursor_seq(row, col))
                    if self._kitty_tx_seq:
                        write(self._kitty_tx_seq)
                    else:
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
                    # Hot path: only re-place already-uploaded image id
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
                    self._sixel = self._cache.get_sixel(
                        path, cols=place_c, rows=place_r
                    )
                    self._tx_cols = avail_cols
                    self._tx_rows = avail_rows
                    self._place_cols = place_c
                    self._place_rows = place_r
                if self._sixel:
                    write(cursor_seq(row, col))
                    write(self._sixel)
        except Exception:
            pass
