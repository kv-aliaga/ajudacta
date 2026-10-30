from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk

from ..constants import HEALTH_SUCCESS_PATTERN, KUBECONFIG_PATH, LOG_DEPLOYMENTS


class LogsMixin:
    def build_logs_page(self, page: ttk.Frame) -> None:
        self.logs_page = page
        outer = ttk.Frame(page, padding=(30, 24, 30, 22))
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 16))
        titles = ttk.Frame(header)
        titles.pack(side="left", fill="x", expand=True)
        ttk.Label(titles, text="Logs em tempo real", style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text="Acompanhe a saída dos pods diretamente neste app.", style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        toolbar = tk.Frame(outer, bg="#111A14", padx=14, pady=11)
        toolbar.pack(fill="x", pady=(0, 10))
        tk.Label(toolbar, text="SERVIÇO", bg="#111A14", fg="#8A9B8D", font=("Consolas", 9, "bold")).pack(side="left", padx=(0, 9))
        self.log_service_menu = ttk.Combobox(toolbar, textvariable=self.log_service_var, values=tuple(LOG_DEPLOYMENTS), state="readonly", width=20)
        self.log_service_menu.pack(side="left", padx=(0, 12))
        self.log_start_button = ttk.Button(toolbar, text="▶  Iniciar logs", command=lambda: self.start_logs(self.log_service_var.get()))
        self.log_start_button.pack(side="left", padx=(0, 7))
        self.log_stop_button = ttk.Button(toolbar, text="■  Parar", command=self.stop_logs, state="disabled")
        self.log_stop_button.pack(side="left", padx=(0, 7))
        ttk.Button(toolbar, text="Limpar", command=self.clear_log_terminal).pack(side="left")
        terminal = tk.Frame(outer, bg="#050805", highlightbackground="#26352A", highlightthickness=1)
        terminal.pack(fill="both", expand=True)
        chrome = tk.Frame(terminal, bg="#111A14", padx=14, pady=9)
        chrome.pack(fill="x")
        lights = tk.Canvas(chrome, width=45, height=12, bg="#111A14", highlightthickness=0)
        lights.pack(side="left", padx=(0, 10))
        for x, color in ((6, "#FF5F57"), (22, "#FEBC2E"), (38, "#28C840")):
            lights.create_oval(x - 4, 2, x + 4, 10, fill=color, outline="")
        tk.Label(chrome, text="kubectl  ·  acta-prod", bg="#111A14", fg="#A7B8A9", font=("Consolas", 9)).pack(side="left")
        self.log_count_label = tk.Label(chrome, text="0 linhas", bg="#111A14", fg="#728276", font=("Consolas", 9))
        self.log_count_label.pack(side="right")
        text_wrap = tk.Frame(terminal, bg="#050805")
        text_wrap.pack(fill="both", expand=True, padx=13, pady=(10, 6))
        self.log_text = tk.Text(text_wrap, wrap="none", state="disabled", relief="flat", bd=0,
                                bg="#050805", fg="#55E86B", insertbackground="#55E86B",
                                selectbackground="#1D4725", selectforeground="#D4FFD9",
                                font=("Consolas", 10), padx=8, pady=7, spacing1=1)
        log_scroll = ttk.Scrollbar(text_wrap, orient="vertical", command=self.log_text.yview)
        log_scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.tag_configure("system", foreground="#9FB3A2")
        self.log_text.tag_configure("error", foreground="#FF7777")
        self.log_text.tag_configure("output", foreground="#55E86B")
        status = tk.Frame(outer, bg="#111A14", padx=13, pady=9)
        status.pack(fill="x", pady=(10, 0))
        self.log_status_dot = tk.Canvas(status, width=12, height=12, bg="#111A14", highlightthickness=0)
        self.log_status_dot.pack(side="left", padx=(0, 8))
        self.log_status_dot_id = self.log_status_dot.create_oval(2, 2, 10, 10, fill="#849187", outline="")
        tk.Label(status, textvariable=self.log_status_var, bg="#111A14", fg="#B5C2B7", font=("Consolas", 9)).pack(side="left")
        tk.Label(status, text="Duplo clique em um serviço na lista para acompanhar.", bg="#111A14", fg="#728276", font=("Consolas", 9)).pack(side="right")
        self._append_log("Pronto. Selecione um serviço na aba APIs dos clusters ou use o menu acima.", "system")
    def set_log_status(self, message: str, kind: str = "idle") -> None:
        colors = {"idle": "#849187", "busy": "#55E86B", "error": "#FF7777"}
        self.log_status_var.set(message)
        self.log_status_dot.itemconfigure(self.log_status_dot_id, fill=colors[kind])
    def _append_log(self, message: str, tag: str = "output") -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message.rstrip("\r\n") + "\n", tag)
        self.log_line_count += 1
        if self.log_line_count > 2500:
            self.log_text.delete("1.0", "101.0")
            self.log_line_count -= 100
        self.log_count_label.configure(text=f"{self.log_line_count} linhas")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
    def clear_log_terminal(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.log_line_count = 0
        self.log_count_label.configure(text="0 linhas")
    def start_logs(self, service: str) -> None:
        deployment = LOG_DEPLOYMENTS.get(service)
        if not deployment:
            return
        self.stop_logs()
        self.log_service_var.set(service)
        self.show_page("logs")
        self.clear_log_terminal()
        self._append_log(f"$ kubectl logs --follow deployment/{deployment} -n acta-prod --all-pods=true --prefix=true", "system")
        self._append_log(f"KUBECONFIG={KUBECONFIG_PATH}", "system")
        self._append_log("Filtro ativo: probes /health, /healthz, /ready e /live com HTTP 200 ficam ocultos.", "system")
        environment = os.environ.copy()
        environment["KUBECONFIG"] = str(KUBECONFIG_PATH)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        try:
            self.log_process = subprocess.Popen(
                ["kubectl", "logs", "--follow", f"deployment/{deployment}", "-n", "acta-prod", "--all-pods=true", "--prefix=true"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                bufsize=1, env=environment, creationflags=creationflags,
            )
        except OSError as exc:
            self.log_process = None
            self._append_log(f"Não foi possível iniciar kubectl: {exc}", "error")
            self.set_log_status("kubectl não iniciou.", "error")
            self.log_start_button.configure(state="normal")
            self.log_stop_button.configure(state="disabled")
            return
        process = self.log_process
        self.set_log_status(f"Conectando a {service}…", "busy")
        self.log_start_button.configure(state="disabled")
        self.log_stop_button.configure(state="normal")
        threading.Thread(target=self._read_log_output, args=(process, service), daemon=True).start()
    def _read_log_output(self, process: subprocess.Popen[str], service: str) -> None:
        if process.stdout is not None:
            for line in process.stdout:
                if HEALTH_SUCCESS_PATTERN.search(line):
                    continue
                self.root.after(0, lambda value=line: self._append_log(value) if self.log_process is process else None)
        return_code = process.wait()
        self.root.after(0, lambda: self._logs_finished(process, service, return_code))
    def _logs_finished(self, process: subprocess.Popen[str], service: str, return_code: int) -> None:
        if self.log_process is not process:
            return
        self.log_process = None
        self.log_start_button.configure(state="normal")
        self.log_stop_button.configure(state="disabled")
        if return_code:
            self.set_log_status(f"kubectl encerrou com código {return_code}.", "error")
        else:
            self.set_log_status(f"Acompanhamento de {service} encerrado.")
    def stop_logs(self) -> None:
        process = self.log_process
        if process is None:
            return
        self.log_process = None
        if process.poll() is None:
            process.terminate()
        self.log_start_button.configure(state="normal")
        self.log_stop_button.configure(state="disabled")
        self.set_log_status("Acompanhamento interrompido.")
