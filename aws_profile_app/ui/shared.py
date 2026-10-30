from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..constants import PALETTE


class SharedUiMixin:
    def build_styles(self) -> None:

        style = ttk.Style(self.root)

        style.theme_use("clam")

        style.configure("TFrame", background=PALETTE["canvas"])

        style.configure("Surface.TFrame", background=PALETTE["surface"])

        style.configure("TLabel", background=PALETTE["canvas"], foreground=PALETTE["ink"], font=("Segoe UI", 10))

        style.configure("Muted.TLabel", foreground=PALETTE["muted"], font=("Segoe UI", 9))

        style.configure("Title.TLabel", foreground=PALETTE["ink"], font=("Segoe UI Semibold", 22))

        style.configure("Section.TLabel", background=PALETTE["surface"], foreground=PALETTE["ink"], font=("Segoe UI Semibold", 11))

        style.configure("TEntry", padding=(10, 9), fieldbackground=PALETTE["surface"], foreground=PALETTE["ink"], bordercolor=PALETTE["line"], lightcolor=PALETTE["line"], darkcolor=PALETTE["line"])

        style.configure("TCombobox", padding=(8, 7), fieldbackground=PALETTE["surface"], foreground=PALETTE["ink"], bordercolor=PALETTE["line"], arrowcolor=PALETTE["muted"])

        style.configure("TButton", font=("Segoe UI Semibold", 9), padding=(13, 9), background=PALETTE["surface"], foreground=PALETTE["ink"], borderwidth=1, relief="flat")

        style.map("TButton", background=[("disabled", "#F1F3F6"), ("active", "#E9EEF5")], foreground=[("disabled", "#9AA6B4"), ("!disabled", PALETTE["ink"])])

        style.configure("Primary.TButton", font=("Segoe UI Semibold", 10), padding=(17, 11), background=PALETTE["blue"], foreground="#FFFFFF", borderwidth=0)

        style.map("Primary.TButton", background=[("disabled", "#A8B8D2"), ("active", PALETTE["blue_hover"])], foreground=[("disabled", "#F5F7FB"), ("!disabled", "#FFFFFF")])

        style.configure("Danger.TButton", font=("Segoe UI Semibold", 9), padding=(14, 10), background="#B84D35", foreground="#FFFFFF", borderwidth=0)

        style.map("Danger.TButton", background=[("disabled", "#D5B3A5"), ("active", "#963B1B"), ("!disabled", "#B84D35")], foreground=[("disabled", "#F5F7FB"), ("!disabled", "#FFFFFF")])

        style.configure("Codex.TButton", font=("Segoe UI Semibold", 9), padding=(14, 10), background="#554CC8", foreground="#FFFFFF", borderwidth=0)

        style.map("Codex.TButton", background=[("disabled", "#B7B5DC"), ("active", "#4940B5"), ("!disabled", "#554CC8")], foreground=[("disabled", "#F5F7FB"), ("!disabled", "#FFFFFF")])

        style.configure("Treeview", background=PALETTE["surface"], fieldbackground=PALETTE["surface"], foreground=PALETTE["ink"], rowheight=29, borderwidth=0, font=("Segoe UI", 9))

        style.configure("Treeview.Heading", background="#EEF2F7", foreground="#526276", font=("Segoe UI Semibold", 9), padding=(9, 9), relief="flat")

        style.map("Treeview", background=[("selected", "#E3EBFF")], foreground=[("selected", PALETTE["ink"])])

        style.map("Treeview.Heading", background=[("active", "#E6ECF3")])





    def step_line(self, parent: tk.Widget, number: str, title: str, detail: str) -> None:

        row = tk.Frame(parent, bg=PALETTE["blue_pale"])

        row.pack(fill="x", pady=(0, 13))

        bubble = tk.Canvas(row, width=25, height=25, bg=PALETTE["blue_pale"], highlightthickness=0)

        bubble.pack(side="left", anchor="n", padx=(0, 10))

        bubble.create_oval(1, 1, 24, 24, fill=PALETTE["surface"], outline="#C9D9FA")

        bubble.create_text(12, 12, text=number, fill=PALETTE["blue"], font=("Segoe UI Semibold", 9))

        copy = tk.Frame(row, bg=PALETTE["blue_pale"])

        copy.pack(side="left", fill="x", expand=True)

        tk.Label(copy, text=title, bg=PALETTE["blue_pale"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 9)).pack(anchor="w")

        tk.Label(copy, text=detail, bg=PALETTE["blue_pale"], fg=PALETTE["muted"], font=("Segoe UI", 8), wraplength=185, justify="left").pack(anchor="w", pady=(2, 0))
