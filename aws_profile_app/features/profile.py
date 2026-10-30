from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

try:
    from winotify import Notification
except ImportError:
    Notification = None

from ..constants import PALETTE
from ..profile_config import update_and_validate


def show_notification(title: str, message: str) -> None:
    if Notification is None or os.name != "nt":
        return
    try:
        Notification(app_id="AWS Default Profile", title=title, msg=message).show()
    except Exception:
        # Notifications should never interrupt profile setup or validation.
        pass


class ProfileMixin:
    def build_profile_page(self, profile_page: ttk.Frame) -> None:
        outer = ttk.Frame(profile_page, padding=(30, 24, 30, 22))
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 19))
        titles = ttk.Frame(header)
        titles.pack(side="left", fill="x", expand=True)
        ttk.Label(titles, text="Atualize a sessão AWS", style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text="Cole o perfil temporário e valide o acesso em um só passo.", style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        columns = ttk.Frame(outer)
        columns.pack(fill="both", expand=True)
        columns.columnconfigure(0, weight=8)
        columns.columnconfigure(1, weight=4, minsize=300)
        columns.rowconfigure(0, weight=1)
        editor_card = tk.Frame(columns, bg=PALETTE["surface"], highlightbackground=PALETTE["line"], highlightthickness=1, bd=0)
        editor_card.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        editor_inner = tk.Frame(editor_card, bg=PALETTE["surface"], padx=26, pady=24)
        editor_inner.pack(fill="both", expand=True)
        tk.Label(editor_inner, text="Bloco de credenciais", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 12)).pack(anchor="w")
        tk.Label(editor_inner, text="Cole o INI do Vocareum com a seção [default].", bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 13))
        text_frame = tk.Frame(editor_inner, bg=PALETTE["editor"], highlightbackground=PALETTE["line"], highlightthickness=1, bd=0)
        text_frame.pack(fill="both", expand=True)
        self.input = tk.Text(text_frame, height=self.editor_rows, wrap="none", undo=True, relief="flat", bd=0, padx=17, pady=16, bg=PALETTE["editor"], fg=PALETTE["ink"], insertbackground=PALETTE["blue"], selectbackground=PALETTE["blue_pale"], selectforeground=PALETTE["ink"], font=("Cascadia Mono", 10))
        self.input.pack(side="left", fill="both", expand=True)
        scroll_y = ctk.CTkScrollbar(text_frame, command=self.input.yview, orientation="vertical", width=10, corner_radius=6, fg_color=PALETTE["editor"], button_color="#AAB8CA", button_hover_color=PALETTE["blue"])
        scroll_y.pack(side="right", fill="y")
        scroll_x = ctk.CTkScrollbar(editor_inner, command=self.input.xview, orientation="horizontal", height=10, corner_radius=6, fg_color=PALETTE["surface"], button_color="#AAB8CA", button_hover_color=PALETTE["blue"])
        scroll_x.pack(fill="x")
        self.input.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        privacy = tk.Frame(editor_inner, bg=PALETTE["surface"])
        privacy.pack(fill="x", pady=(12, 0))
        tk.Canvas(privacy, width=12, height=12, bg=PALETTE["surface"], highlightthickness=0).pack(side="left", padx=(0, 7))
        dot = privacy.winfo_children()[0]
        dot.create_oval(2, 2, 10, 10, fill=PALETTE["green"], outline="")
        tk.Label(privacy, text="O texto colado é apagado após cada tentativa.", bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 9)).pack(side="left")
        side = tk.Frame(columns, bg=PALETTE["blue_pale"], highlightbackground="#D6E3FF", highlightthickness=1, bd=0)
        side.grid(row=0, column=1, sticky="nsew")
        side_inner = tk.Frame(side, bg=PALETTE["blue_pale"], padx=23, pady=24)
        side_inner.pack(fill="both", expand=True)
        tk.Label(side_inner, text="O que vai acontecer", bg=PALETTE["blue_pale"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(0, 15))
        self.step_line(side_inner, "1", "Atualizar", "Somente o perfil default")
        self.step_line(side_inner, "2", "Definir região", "Detectada no INI ou mantida")
        self.step_line(side_inner, "3", "Validar", "Consulta de identidade no STS")
        ttk.Separator(side_inner).pack(fill="x", pady=(18, 16))
        tk.Label(side_inner, text="Região AWS", bg=PALETTE["blue_pale"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 10)).pack(anchor="w")
        self.region_entry = ttk.Entry(side_inner, textvariable=self.region_var)
        self.region_entry.pack(fill="x", pady=(7, 5))
        tk.Label(side_inner, text="Usada se o bloco colado não trouxer uma região.", bg=PALETTE["blue_pale"], fg=PALETTE["muted"], font=("Segoe UI", 9), wraplength=230, justify="left").pack(anchor="w")
        ttk.Separator(side_inner).pack(fill="x", pady=(18, 15))
        tk.Label(side_inner, text="Arquivos locais", bg=PALETTE["blue_pale"], fg=PALETTE["muted"], font=("Segoe UI Semibold", 9)).pack(anchor="w")
        tk.Label(side_inner, text="~\\.aws\\credentials\n~\\.aws\\config", bg=PALETTE["blue_pale"], fg=PALETTE["ink"], font=("Cascadia Mono", 8), justify="left").pack(anchor="w", pady=(6, 0))
        tk.Label(side_inner, text="O AWS CLI mantém as credenciais nesses arquivos locais para uso no computador.", bg=PALETTE["blue_pale"], fg=PALETTE["muted"], font=("Segoe UI", 9), wraplength=230, justify="left").pack(anchor="w", pady=(8, 0))
        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(19, 0))
        tk.Label(footer, text="Os outros perfis AWS são preservados.", bg=PALETTE["canvas"], fg=PALETTE["muted"], font=("Segoe UI", 9)).pack(side="left", anchor="w")
        self.button = ttk.Button(footer, text="Atualizar perfil e validar", style="Primary.TButton", command=self.start_update)
        self.button.pack(side="right")
        status_frame = tk.Frame(outer, bg=PALETTE["surface"], highlightbackground=PALETTE["line"], highlightthickness=1, bd=0)
        status_frame.pack(fill="x", pady=(14, 0))
        self.status_dot = tk.Canvas(status_frame, width=16, height=16, bg=PALETTE["surface"], highlightthickness=0)
        self.status_dot.pack(side="left", padx=(13, 7), pady=10)
        self.status_dot_id = self.status_dot.create_oval(3, 3, 13, 13, fill=PALETTE["muted"], outline="")
        self.status_label = tk.Label(status_frame, textvariable=self.status_var, bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 9))
        self.status_label.pack(side="left", pady=10)
        self.input.focus_set()
    def start_update(self) -> None:
        if self.busy:
            return
        raw = self.input.get("1.0", "end-1c")
        region = self.region_var.get().strip()
        self.input.delete("1.0", "end")
        self.input.edit_reset()
        if not raw.strip():
            self.set_status("Cole o bloco [default] antes de continuar.", "error")
            return
        self.busy = True
        self.button.configure(state="disabled")
        self.set_status("Atualizando o perfil e consultando o STS…", "busy")
        def work() -> None:
            try:
                result = update_and_validate(raw, region)
            except Exception as exc:
                result = (False, str(exc), region)
            self.root.after(0, lambda: self.finish_update(result))
        threading.Thread(target=work, daemon=True).start()
    def finish_update(self, result: tuple[bool, str, str]) -> None:
        success, message, region = result
        self.busy = False
        self.button.configure(state="normal")
        if success:
            self.region_var.set(region)
            self.set_status(f"{message} Região ativa: {region}.", "success")
            show_notification("Perfil atualizado", f"AWS default validado com STS. Região: {region}.")
        else:
            self.set_status(message, "error")
            show_notification("Validação não concluída", "Confira os detalhes no app. O perfil anterior foi restaurado quando necessário.")
    def set_status(self, message: str, kind: str = "idle") -> None:
        color = {"idle": PALETTE["muted"], "busy": PALETTE["blue"], "success": PALETTE["green"], "error": PALETTE["red"]}[kind]
        self.status_var.set(message)
        self.status_label.configure(fg=color)
        self.status_dot.itemconfigure(self.status_dot_id, fill=color)
