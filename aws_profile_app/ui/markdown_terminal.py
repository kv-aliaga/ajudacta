from __future__ import annotations

from html import escape

from markdown_it import MarkdownIt
from tkinterweb import HtmlFrame


_MARKDOWN = MarkdownIt("default", {"html": False}).enable("table").enable("strikethrough")


class MarkdownTerminal(HtmlFrame):
    """Scrollable dark transcript with safe Markdown rendering and live text streaming."""

    def __init__(self, master) -> None:
        super().__init__(
            master,
            messages_enabled=False,
            images_enabled=False,
            javascript_enabled=False,
            forms_enabled=False,
            objects_enabled=False,
            vertical_scrollbar=True,
            horizontal_scrollbar=True,
        )
        self._fragments: list[str] = []
        self._plain_text: list[str] = []
        self._pending: list[str] = []
        self._flush_job: str | None = None
        self._stream_start: int | None = None
        self._plain_stream_start: int | None = None
        self.load_html(self._document(""))

    @staticmethod
    def _document(content: str) -> str:
        return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
html, body {{ background:#050805; color:#55E86B; margin:0; padding:0; }}
body {{ font: 13px Consolas, 'Courier New', monospace; padding:8px 10px; overflow-wrap:anywhere; }}
.line {{ white-space:pre-wrap; color:#55E86B; }}
.system {{ color:#9FB3A2; }} .error {{ color:#FF7777; }}
.command, .human {{ color:#8AB4F8; }} .codex, .output {{ color:#55E86B; }}
.message {{ white-space:normal; margin:0 0 10px; line-height:1.45; }}
.message.human {{ border-left:2px solid #5688D8; padding-left:9px; }}
.message.codex {{ border-left:2px solid #358347; padding-left:9px; }}
p {{ margin:5px 0 9px; }}
h1, h2, h3, h4, h5, h6 {{ color:#D7FFD9; font-family:'Segoe UI', sans-serif; margin:12px 0 7px; }}
h1 {{ font-size:19px; }} h2 {{ font-size:16px; }} h3, h4, h5, h6 {{ font-size:14px; }}
strong {{ color:#D7FFD9; }} em {{ color:#B6DDBB; }}
code {{ color:#FFD479; background:#172018; padding:1px 4px; }}
pre {{ color:#B9E4C0; background:#101711; border:1px solid #26352A; padding:9px; white-space:pre-wrap; }}
pre code {{ color:inherit; background:transparent; padding:0; }}
blockquote {{ color:#A7C7AE; border-left:3px solid #52765A; margin:8px 0; padding:2px 10px; }}
ul, ol {{ padding-left:23px; margin:5px 0 9px; }} li {{ margin:3px 0; }}
hr {{ border:0; border-top:1px solid #52765A; margin:10px 0; }}
a {{ color:#8AB4F8; text-decoration:underline; }}
table {{ border-collapse:collapse; margin:8px 0 12px; }}
th, td {{ border:1px solid #52765A; padding:5px 8px; text-align:left; vertical-align:top; }}
th {{ color:#D7FFD9; background:#101711; }}
tr:nth-child(even) td {{ background:#0B110D; }}
</style></head><body>{content}</body></html>"""

    def append_text(self, text: str, role: str = "codex") -> None:
        if not text:
            return
        fragment = f'<span class="line {escape(role, quote=True)}">{escape(text)}</span>'
        self._fragments.append(fragment)
        self._plain_text.append(text)
        self._pending.append(fragment)
        if self._flush_job is None:
            self._flush_job = self.after(35, self._flush_pending)

    def append_markdown(self, markdown: str, role: str = "codex") -> None:
        self._flush_pending()
        rendered = _MARKDOWN.render(markdown)
        fragment = f'<section class="message {escape(role, quote=True)}">{rendered}</section>'
        self._fragments.append(fragment)
        self._plain_text.append(markdown + "\n")
        self._rebuild()

    def begin_stream(self) -> None:
        self._flush_pending()
        self._stream_start = len(self._fragments)
        self._plain_stream_start = len(self._plain_text)

    def finish_stream(self, markdown: str) -> None:
        self._flush_pending()
        if self._stream_start is None:
            self.append_markdown(markdown)
            return
        self._fragments[self._stream_start:] = [
            f'<section class="message codex">{_MARKDOWN.render(markdown)}</section>'
        ]
        self._plain_text[self._plain_stream_start:] = [markdown + "\n"]
        self._stream_start = None
        self._plain_stream_start = None
        self._rebuild()

    def copy_all(self) -> None:
        self._flush_pending()
        self.clipboard_clear()
        self.clipboard_append("".join(self._plain_text))

    def _flush_pending(self) -> None:
        if self._flush_job is not None:
            try:
                self.after_cancel(self._flush_job)
            except Exception:
                pass
            self._flush_job = None
        if not self._pending:
            return
        batch = "".join(self._pending)
        self._pending.clear()
        self.add_html(batch)
        self.yview_moveto(1.0)

    def _rebuild(self) -> None:
        self.load_html(self._document("".join(self._fragments)))
        self.after_idle(lambda: self.yview_moveto(1.0))
