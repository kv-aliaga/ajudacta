from __future__ import annotations

import os
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


from .constants import APP_ICON_PATH, APP_TITLE, CONFIG_PATH, PALETTE
from .profile_config import default_region, read_optional
from .features.clusters import ClusterMixin
from .features.diagnostics import DiagnosticsMixin
from .features.logs import LogsMixin
from .features.profile import ProfileMixin
from .features.redeploy import RedeployMixin
from .features.rollouts import RolloutMixin
from .features.tokens import TokenMixin
from .ui.shared import SharedUiMixin


def enable_windows_dpi_awareness() -> None:
    """Ask Windows for crisp, per-monitor rendering before Tk creates a window."""
    if os.name != "nt":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        try:
            # PER_MONITOR_AWARE_V2 handles modern mixed-DPI multi-monitor setups.
            user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        # Keep the app usable on older or restricted Windows environments.
        pass


def initial_window_geometry(root: tk.Tk) -> tuple[int, int, int, int]:
    """Fit the initial window to the usable screen area and current DPI."""
    left = top = 0
    work_width = root.winfo_screenwidth()
    work_height = root.winfo_screenheight()

    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class Rect(ctypes.Structure):
                _fields_ = (("left", wintypes.LONG), ("top", wintypes.LONG),
                            ("right", wintypes.LONG), ("bottom", wintypes.LONG))

            area = Rect()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0):
                left, top = area.left, area.top
                work_width = area.right - area.left
                work_height = area.bottom - area.top
        except (AttributeError, OSError):
            pass

    try:
        scale = max(1.0, float(root.winfo_fpixels("1i")) / 96.0)
    except (tk.TclError, ValueError):
        scale = 1.0

    width = min(round(1320 * scale), max(900, work_width - 48))
    height = min(round(860 * scale), max(620, work_height - 72))
    x = left + max(0, (work_width - width) // 2)
    y = top + max(0, (work_height - height) // 2)
    return width, height, x, y


class AwsProfileApp(ProfileMixin, TokenMixin, ClusterMixin, DiagnosticsMixin, RolloutMixin, LogsMixin, RedeployMixin, SharedUiMixin):
    def __init__(self) -> None:
        enable_windows_dpi_awareness()
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.app_icon_image: tk.PhotoImage | None = None
        try:
            self.app_icon_image = tk.PhotoImage(file=str(APP_ICON_PATH))
            self.root.iconphoto(True, self.app_icon_image)
        except tk.TclError:
            self.app_icon_image = None
        width, height, x, y = initial_window_geometry(self.root)
        self.root.geometry(f"{width}x{height}{x:+d}{y:+d}")
        self.root.minsize(min(round(940 * (width / 1120)), width), min(round(620 * (height / 780)), height))
        try:
            dpi_scale = max(1.0, float(self.root.winfo_fpixels("1i")) / 96.0)
        except (tk.TclError, ValueError):
            dpi_scale = 1.0
        self.editor_rows = max(8, min(18, int((height - 310) / (17 * dpi_scale))))
        self.root.configure(bg=PALETTE["canvas"])
        self.root.option_add("*Font", ("Segoe UI", 10))
        self.region_var = tk.StringVar(value=default_region(read_optional(CONFIG_PATH)))
        self.status_var = tk.StringVar(value="Pronto para receber o bloco [default].")
        self.status_kind = "idle"
        self.busy = False
        self.cluster_busy = False
        self.cluster_urls: list[tuple[str, str]] = []
        self.diagnostics_busy = False
        self.diagnostics_rows: list[tuple[str, str, str, str]] = []
        self.deep_terminal: tk.Text | None = None
        self.deep_session_id: str | None = None
        self.deep_process: subprocess.Popen[str] | None = None
        self.deep_running = False
        self.diagnostics_autostart_deep = False
        self.argocd_port_forward: subprocess.Popen | None = None
        self.rollout_busy = False
        self.log_process: subprocess.Popen[str] | None = None
        self.log_service_var = tk.StringVar(value="Auth API")
        self.log_status_var = tk.StringVar(value="Aguardando seleção de um serviço.")
        self.log_status_kind = "idle"
        self.log_line_count = 0
        self.rebuild_busy = False
        self.destroy_plan_path: Path | None = None
        self.destroy_plan_resources: list[str] = []
        self.rebuild_target: dict[str, str] = {}
        self.rebuild_line_count = 0
        self.rebuild_process: subprocess.Popen[str] | None = None
        self.rebuild_destroy_completed = False
        self.token_users: list[dict[str, str]] = []
        self.token_generation_busy = False
        self.token_countdown_job: str | None = None
        self.active_firebase_token = ""
        self.build_styles()
        self.build_ui()
        self.root.bind("<Control-Return>", lambda _event: self.start_update())
    def build_ui(self) -> None:
        shell = tk.Frame(self.root, bg=PALETTE["canvas"])
        shell.pack(fill="both", expand=True)
        self.app_shell = shell
        sidebar = tk.Frame(shell, bg=PALETTE["nav"], width=226)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self.sidebar = sidebar
        brand = tk.Frame(sidebar, bg=PALETTE["nav"], padx=18, pady=22)
        brand.pack(fill="x")
        self.brand = brand
        brand_mark = tk.Canvas(brand, width=38, height=38, bg=PALETTE["nav"], highlightthickness=0)
        brand_mark.pack(side="left", padx=(0, 10))
        self.brand_mark = brand_mark
        brand_mark.create_oval(1, 1, 37, 37, fill=PALETTE["blue"], outline="")
        brand_mark.create_text(19, 19, text="A", fill="#FFFFFF", font=("Segoe UI Semibold", 16))
        brand_copy = tk.Frame(brand, bg=PALETTE["nav"])
        brand_copy.pack(side="left", fill="x", expand=True)
        self.brand_copy = brand_copy
        tk.Label(brand_copy, text="ACTA", bg=PALETTE["nav"], fg=PALETTE["nav_text"], font=("Segoe UI Semibold", 14), anchor="w").pack(anchor="w")
        self.brand_caption = tk.Label(brand_copy, text="Painel de operações", bg=PALETTE["nav"], fg=PALETTE["nav_muted"], font=("Segoe UI", 8), anchor="w")
        self.brand_caption.pack(anchor="w", pady=(1, 0))
        tk.Frame(sidebar, bg="#2B3A4E", height=1).pack(fill="x", padx=16, pady=(0, 13))
        self.nav_section_label = tk.Label(sidebar, text="Navegação", bg=PALETTE["nav"], fg=PALETTE["nav_muted"], font=("Segoe UI Semibold", 8), anchor="w", padx=20)
        self.nav_section_label.pack(fill="x", pady=(0, 7))
        self.nav_items = []
        self.nav_specs = [
            ("profile", "Perfil AWS", "Perfil", "◉"),
            ("clusters", "APIs do cluster", "APIs", "⌕"),
            ("tokens", "Token IDs", "Tokens", "◆"),
            ("diagnostics", "Diagnóstico", "Diag.", "◇"),
            ("rollouts", "Rollout APIs", "Rollout", "↻"),
            ("logs", "Terminal de logs", "Logs", "›_"),
            ("rebuild", "Matar e implantar", "Deploy", "↻"),
        ]
        nav_host = tk.Frame(sidebar, bg=PALETTE["nav"])
        nav_host.pack(fill="x", padx=10)
        for key, label, compact_label, icon in self.nav_specs:
            button = tk.Button(nav_host, text=f"{icon}   {label}", command=lambda name=key: self.show_page(name), anchor="w", padx=12, pady=11,
                               relief="flat", bd=0, bg=PALETTE["nav"], fg=PALETTE["nav_muted"], activebackground=PALETTE["nav_hover"],
                               activeforeground=PALETTE["nav_text"], font=("Segoe UI Semibold", 9), cursor="hand2", takefocus=True)
            button.pack(fill="x", pady=2)
            button.bind("<Enter>", lambda _event, widget=button: widget.configure(bg=PALETTE["nav_hover"]) if widget is not self.active_nav_button else None)
            button.bind("<Leave>", lambda _event, widget=button: widget.configure(bg="#263A56" if widget is self.active_nav_button else PALETTE["nav"]))
            self.nav_items.append((key, label, compact_label, icon, button))
        sidebar_spacer = tk.Frame(sidebar, bg=PALETTE["nav"])
        sidebar_spacer.pack(fill="both", expand=True)
        tk.Frame(sidebar, bg="#2B3A4E", height=1).pack(fill="x", padx=16, pady=(0, 12))
        self.sidebar_status = tk.Label(sidebar, text="●  Ambiente local", bg=PALETTE["nav"], fg="#91D5B2", font=("Segoe UI", 9), anchor="w", padx=20, pady=4)
        self.sidebar_status.pack(fill="x", pady=(0, 16))
        self.active_nav_button = None
        workspace = tk.Frame(shell, bg=PALETTE["canvas"])
        workspace.pack(side="left", fill="both", expand=True)
        topbar = tk.Frame(workspace, bg=PALETTE["surface"], height=54, highlightbackground=PALETTE["line"], highlightthickness=1)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        self.workspace_title = tk.Label(topbar, text="Perfil AWS", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 10), anchor="w")
        self.workspace_title.pack(side="left", padx=24)
        self.workspace_badge = tk.Label(topbar, text="●  Perfil default", bg=PALETTE["green_pale"], fg=PALETTE["green"], font=("Segoe UI Semibold", 8), padx=10, pady=5)
        self.workspace_badge.pack(side="right", padx=22)
        self.content_host = tk.Frame(workspace, bg=PALETTE["canvas"])
        self.content_host.pack(fill="both", expand=True)
        self.content_host.grid_rowconfigure(0, weight=1)
        self.content_host.grid_columnconfigure(0, weight=1)
        self.page_frames = {
            key: ttk.Frame(self.content_host)
            for key, _label, _short, _icon in self.nav_specs
        }
        for page in self.page_frames.values():
            page.grid(row=0, column=0, sticky="nsew")
        profile_page = self.page_frames["profile"]
        cluster_page = self.page_frames["clusters"]
        token_page = self.page_frames["tokens"]
        diagnostics_page = self.page_frames["diagnostics"]
        rollouts_page = self.page_frames["rollouts"]
        logs_page = self.page_frames["logs"]
        rebuild_page = self.page_frames["rebuild"]
        self.build_profile_page(profile_page)
        self.build_clusters_page(cluster_page)
        self.build_token_page(token_page)
        self.build_diagnostics_page(diagnostics_page)
        self.build_rollout_page(rollouts_page)
        self.build_logs_page(logs_page)
        self.build_rebuild_page(rebuild_page)
        self.show_page("profile")
        self.root.bind("<Configure>", self._handle_shell_resize, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)
    def show_page(self, page_key: str) -> None:
        page = self.page_frames.get(page_key)
        if page is None:
            return
        page.tkraise()
        for key, label, _short, _icon, button in self.nav_items:
            active = key == page_key
            button.configure(bg="#263A56" if active else PALETTE["nav"], fg=PALETTE["nav_text"] if active else PALETTE["nav_muted"])
            if active:
                self.active_nav_button = button
        title = next((label for key, label, _short, _icon in self.nav_specs if key == page_key), "ACTA")
        self.workspace_title.configure(text=title)
    def _handle_shell_resize(self, event: tk.Event) -> None:
        if event.widget is not self.root or not hasattr(self, "nav_items"):
            return
        compact = event.width < 1120
        target_width = 76 if compact else 226
        if self.sidebar.winfo_width() != target_width:
            self.sidebar.configure(width=target_width)
        if compact:
            self.brand.configure(padx=19, pady=16)
            self.brand_mark.pack_forget()
            self.brand_mark.pack(anchor="center")
            self.brand_copy.pack_forget()
            self.nav_section_label.configure(text="")
        else:
            self.brand.configure(padx=18, pady=22)
            self.brand_mark.pack_forget()
            self.brand_mark.pack(side="left", padx=(0, 10))
            self.brand_copy.pack(side="left", fill="x", expand=True)
            self.nav_section_label.configure(text="Navegação")
        for _key, label, compact_label, icon, button in self.nav_items:
            if compact:
                button.configure(text=f"{icon}\n{compact_label}", anchor="center", padx=2, pady=10, font=("Segoe UI Semibold", 8))
            else:
                button.configure(text=f"{icon}   {label}", anchor="w", padx=12, pady=11, font=("Segoe UI Semibold", 9))
        self.sidebar_status.configure(text="●\nLocal" if compact else "●  Ambiente local", anchor="center" if compact else "w", padx=8 if compact else 20)
    def close_app(self) -> None:
        if self.rollout_busy:
            messagebox.showwarning("Rollout em andamento", "Mantenha o app aberto até a inspeção ou o rollout da API selecionada terminar.", parent=self.root)
            return
        if self.rebuild_busy:
            messagebox.showwarning("Reconstrução em andamento", "Mantenha o app aberto até a etapa atual terminar.", parent=self.root)
            return
        if self.token_generation_busy:
            messagebox.showwarning("Emissão em andamento", "Mantenha o app aberto até o Firebase terminar a emissão e o registro.", parent=self.root)
            return
        self.stop_logs()
        if self.argocd_port_forward is not None and self.argocd_port_forward.poll() is None:
            self.argocd_port_forward.terminate()
        self.close_deep_analysis()
        if self.destroy_plan_path is not None:
            self.destroy_plan_path.unlink(missing_ok=True)
        self.root.destroy()
    def run(self) -> None:
        self.root.mainloop()
