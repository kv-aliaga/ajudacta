from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import tempfile
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from ..constants import INFISICAL_ENV_PATH, PALETTE, PLATFORM_DEPLOY_SCRIPT, PLATFORM_REPO, PLATFORM_TERRAFORM_DIR, REBUILD_REQUIRED_STATE, REGION_PATTERN


def load_infisical_credentials() -> tuple[str, str]:
    """Read the Infisical Universal Auth pair without exposing it in logs."""
    values: dict[str, str] = {}
    try:
        lines = INFISICAL_ENV_PATH.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return "", ""
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        key, separator, value = stripped.partition("=")
        if not separator:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key in ("CLIENT_ID", "CLIENT_SECRET"):
            values[key] = value
    return values.get("CLIENT_ID", ""), values.get("CLIENT_SECRET", "")


class RedeployMixin:
    def build_rebuild_page(self, page: ttk.Frame) -> None:
        self.rebuild_status_var = tk.StringVar(value="O app ainda não conferiu o ambiente.")
        self.rebuild_target_var = tk.StringVar(value="Conta AWS: aguardando conferência")
        self.rebuild_region_var = tk.StringVar(value="Região: aguardando conferência")
        self.rebuild_branch_var = tk.StringVar(value="Checkout: aguardando conferência")
        self.rebuild_summary_var = tk.StringVar(value="Nenhum plano de destruição foi preparado.")
        outer = ttk.Frame(page, padding=(26, 20, 26, 18))
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 14))
        title_area = ttk.Frame(header)
        title_area.pack(side="left", fill="x", expand=True)
        ttk.Label(title_area, text="Matar e implantar de novo", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_area, text="Reconstrói a infraestrutura ACTA usando o checkout local.", style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        tk.Label(header, text="ACTA  /  PROD", bg="#E9F0FF", fg=PALETTE["blue"], font=("Segoe UI Semibold", 9), padx=13, pady=8).pack(side="right", anchor="n")
        warning = tk.Frame(outer, bg="#FFF2DF", highlightbackground="#F1D1A5", highlightthickness=1, padx=14, pady=10)
        warning.pack(fill="x", pady=(0, 12))
        tk.Label(warning, text="A destruição remove apenas os recursos gerenciados pelo state Terraform deste projeto. O arquivo de state será mantido e atualizado; recursos externos não entram nesse plano.", bg="#FFF2DF", fg="#714318", font=("Segoe UI Semibold", 9), anchor="w", wraplength=1000, justify="left").pack(fill="x")
        phases = tk.Frame(outer, bg=PALETTE["canvas"])
        phases.pack(fill="x", pady=(0, 12))
        for col in range(3):
            phases.grid_columnconfigure(col, weight=1)
        self.rebuild_phase_labels = []
        for column, (label, color) in enumerate((("1  ·  Conferir alvo e plano", "#A26013"), ("2  ·  Remover infraestrutura", "#A26013"), ("3  ·  Implantar novamente", PALETTE["blue"]))):
            card = tk.Frame(phases, bg=PALETTE["surface"], highlightbackground=PALETTE["line"], highlightthickness=1, padx=13, pady=10)
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 5, 0 if column == 2 else 5))
            label_widget = tk.Label(card, text=label, bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI Semibold", 9), anchor="w")
            label_widget.pack(fill="x")
            self.rebuild_phase_labels.append(label_widget)
        body = ttk.Frame(outer)
        body.pack(fill="x", pady=(0, 12))
        body.columnconfigure(0, weight=5)
        body.columnconfigure(1, weight=4)
        target_card = tk.Frame(body, bg=PALETTE["surface"], highlightbackground=PALETTE["line"], highlightthickness=1, padx=17, pady=14)
        target_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(target_card, text="Alvo da operação", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0, 9))
        tk.Label(target_card, textvariable=self.rebuild_target_var, bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 10), anchor="w").pack(fill="x", pady=(0, 4))
        tk.Label(target_card, textvariable=self.rebuild_region_var, bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(0, 4))
        tk.Label(target_card, textvariable=self.rebuild_branch_var, bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 9), anchor="w", wraplength=620, justify="left").pack(fill="x", pady=(0, 8))
        tk.Label(target_card, text=str(PLATFORM_REPO), bg=PALETTE["editor"], fg=PALETTE["muted"], font=("Consolas", 8), padx=8, pady=7, anchor="w", wraplength=680, justify="left").pack(fill="x")
        action_card = tk.Frame(body, bg=PALETTE["surface"], highlightbackground=PALETTE["line"], highlightthickness=1, padx=17, pady=14)
        action_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        tk.Label(action_card, text="Plano de destruição", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(0, 5))
        tk.Label(action_card, textvariable=self.rebuild_summary_var, bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 9), anchor="w", justify="left", wraplength=430).pack(fill="x", pady=(0, 9))
        self.rebuild_prepare_button = ttk.Button(action_card, text="Conferir ambiente e preparar plano", style="Primary.TButton", command=self.prepare_rebuild)
        self.rebuild_prepare_button.pack(fill="x", anchor="w")
        self.rebuild_review_button = ttk.Button(action_card, text="Revisar e iniciar reconstrução", style="Danger.TButton", command=self.show_rebuild_confirmation, state="disabled")
        self.rebuild_review_button.pack(fill="x", anchor="w", pady=(7, 0))
        self.rebuild_resume_button = ttk.Button(action_card, text="Retomar implantação sem apagar de novo", command=self.show_rebuild_resume_dialog, state="disabled")
        self.rebuild_resume_button.pack(fill="x", anchor="w", pady=(7, 0))
        status_frame = tk.Frame(outer, bg="#EAF0F6", padx=12, pady=8)
        status_frame.pack(fill="x", pady=(0, 9))
        self.rebuild_status_dot = tk.Canvas(status_frame, width=12, height=12, bg="#EAF0F6", highlightthickness=0)
        self.rebuild_status_dot.pack(side="left", padx=(0, 7))
        self.rebuild_status_dot_id = self.rebuild_status_dot.create_oval(2, 2, 10, 10, fill=PALETTE["muted"], outline="")
        tk.Label(status_frame, textvariable=self.rebuild_status_var, bg="#EAF0F6", fg=PALETTE["ink"], font=("Segoe UI", 9), anchor="w").pack(side="left", fill="x", expand=True)
        terminal = tk.Frame(outer, bg="#050805", highlightbackground="#26352A", highlightthickness=1)
        terminal.pack(fill="both", expand=True)
        chrome = tk.Frame(terminal, bg="#111A14", padx=13, pady=8)
        chrome.pack(fill="x")
        tk.Label(chrome, text="ACTA  ·  HISTÓRICO DA SESSÃO", bg="#111A14", fg="#A7B8A9", font=("Consolas", 9)).pack(side="left")
        self.rebuild_count_label = tk.Label(chrome, text="0 linhas", bg="#111A14", fg="#728276", font=("Consolas", 9))
        self.rebuild_count_label.pack(side="right")
        log_wrap = tk.Frame(terminal, bg="#050805")
        log_wrap.pack(fill="both", expand=True, padx=11, pady=8)
        self.rebuild_text = tk.Text(log_wrap, wrap="word", state="disabled", relief="flat", bd=0, bg="#050805", fg="#55E86B", selectbackground="#1D4725", selectforeground="#D4FFD9", font=("Consolas", 9), padx=8, pady=5)
        rebuild_scroll = ttk.Scrollbar(log_wrap, orient="vertical", command=self.rebuild_text.yview)
        rebuild_scroll.pack(side="right", fill="y")
        self.rebuild_text.pack(side="left", fill="both", expand=True)
        self.rebuild_text.configure(yscrollcommand=rebuild_scroll.set)
        self.rebuild_text.tag_configure("system", foreground="#9FB3A2")
        self.rebuild_text.tag_configure("error", foreground="#FF7777")
        self.rebuild_text.tag_configure("output", foreground="#55E86B")
        self._append_rebuild_log("A abertura desta aba não executa comandos na AWS.", "system")
        self._append_rebuild_log("Prepare o plano para revisar a conta, a região e cada recurso antes de apagar.", "system")
    def _set_rebuild_status(self, message: str, kind: str = "idle") -> None:
        colors = {"idle": PALETTE["muted"], "busy": PALETTE["blue"], "warning": "#A26013", "success": PALETTE["green"], "error": PALETTE["red"]}
        self.rebuild_status_var.set(message)
        self.rebuild_status_dot.itemconfigure(self.rebuild_status_dot_id, fill=colors[kind])
    def _set_rebuild_phase(self, active: int) -> None:
        for index, widget in enumerate(self.rebuild_phase_labels):
            color = ("#A26013" if index == 0 else PALETTE["blue"]) if index == active else PALETTE["muted"]
            widget.configure(fg=color)
    def _append_rebuild_log(self, message: str, tag: str = "output") -> None:
        self.rebuild_text.configure(state="normal")
        self.rebuild_text.insert("end", message.rstrip("\r\n") + "\n", tag)
        self.rebuild_line_count += 1
        if self.rebuild_line_count > 2500:
            self.rebuild_text.delete("1.0", "101.0")
            self.rebuild_line_count -= 100
        self.rebuild_count_label.configure(text=f"{self.rebuild_line_count} linhas")
        self.rebuild_text.see("end")
        self.rebuild_text.configure(state="disabled")
    @staticmethod
    def _run_preflight_command(command: list[str], cwd: Path, env: dict[str, str], timeout: int = 90) -> str:
        completed = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
        if completed.returncode:
            command_label = " ".join([Path(command[0]).name, *command[1:3]])
            raise RuntimeError(f"Falha ao executar {command_label}; confira as ferramentas, a autorização e a configuração local.")
        return completed.stdout.strip()
    def _preflight_status(self, message: str) -> None:
        self.root.after(0, lambda text=message: self._set_rebuild_status(text, "busy"))
    def prepare_rebuild(self) -> None:
        if self.rebuild_busy:
            return
        if self.rebuild_destroy_completed:
            self._set_rebuild_status("A infraestrutura já foi removida. Use Retomar implantação para continuar sem apagar novamente.", "warning")
            return
        self.rebuild_busy = True
        if self.destroy_plan_path is not None:
            self.destroy_plan_path.unlink(missing_ok=True)
            self.destroy_plan_path = None
        self.destroy_plan_resources = []
        self.rebuild_review_button.configure(state="disabled")
        self.rebuild_prepare_button.configure(state="disabled")
        self.rebuild_summary_var.set("Conferindo ferramentas, identidade AWS e state Terraform…")
        self._set_rebuild_status("Preparando um plano novo; nenhum recurso será alterado nesta etapa.", "busy")
        self._set_rebuild_phase(0)
        self._append_rebuild_log("Iniciando o pré-voo. Esta etapa não altera recursos AWS.", "system")
        threading.Thread(target=self._prepare_rebuild_work, daemon=True).start()
    def _prepare_rebuild_work(self) -> None:
        plan_path: Path | None = None
        try:
            if not PLATFORM_REPO.is_dir() or not PLATFORM_DEPLOY_SCRIPT.is_file():
                raise RuntimeError(f"Não encontrei o checkout esperado em {PLATFORM_REPO}.")
            self._preflight_status("Conferindo state local e chave SSH…")
            state_path = PLATFORM_TERRAFORM_DIR / "terraform.tfstate"
            if not state_path.is_file() or state_path.stat().st_size == 0:
                raise RuntimeError("O state Terraform local está ausente ou vazio. A reconstrução foi bloqueada para evitar duplicar recursos.")
            key_path = Path.home() / ".aws" / "labsuser.pem"
            if not key_path.is_file():
                raise RuntimeError("A chave SSH labsuser.pem não foi encontrada em ~/.aws.")
            tools = {name: shutil.which(name) for name in ("aws", "terraform", "kubectl", "ssh", "gh", "git")}
            missing = [name for name, path in tools.items() if not path]
            powershell = shutil.which("pwsh.exe") or shutil.which("pwsh") or shutil.which("powershell.exe") or shutil.which("powershell")
            if missing or not powershell:
                missing_text = ", ".join(missing + ([] if powershell else ["PowerShell"]))
                raise RuntimeError(f"Ferramenta necessária não encontrada no PATH: {missing_text}.")
            env = os.environ.copy()
            env["AWS_PROFILE"] = "default"
            self._preflight_status("Confirmando a identidade do perfil AWS default…")
            identity_raw = self._run_preflight_command([tools["aws"], "sts", "get-caller-identity", "--output", "json"], PLATFORM_REPO, env, timeout=30)
            identity = json.loads(identity_raw)
            account = str(identity.get("Account", ""))
            if not re.fullmatch(r"\d{12}", account):
                raise RuntimeError("A AWS não retornou um ID de conta válido.")
            tfvars_path = PLATFORM_TERRAFORM_DIR / "terraform.tfvars"
            if not tfvars_path.is_file():
                raise RuntimeError("infra/aws/terraform.tfvars não foi encontrado.")
            tfvars = tfvars_path.read_text(encoding="utf-8-sig")
            region_match = re.search(r'^\s*aws_region\s*=\s*["\']([^"\']+)["\']', tfvars, re.MULTILINE)
            region = region_match.group(1) if region_match else self._run_preflight_command([tools["aws"], "configure", "get", "region"], PLATFORM_REPO, env, timeout=15)
            if not REGION_PATTERN.fullmatch(region):
                raise RuntimeError("Não consegui confirmar a região de destino em terraform.tfvars ou no perfil AWS.")
            branch = self._run_preflight_command(["git", "branch", "--show-current"], PLATFORM_REPO, env, timeout=15)
            changes = self._run_preflight_command(["git", "status", "--porcelain"], PLATFORM_REPO, env, timeout=15)
            dirty_count = len([line for line in changes.splitlines() if line.strip()])
            self._preflight_status("Conferindo acesso ao pacote privado do GitHub…")
            self._run_preflight_command([tools["gh"], "auth", "status"], PLATFORM_REPO, env, timeout=30)
            self._run_preflight_command([tools["gh"], "api", "/orgs/AppActa/packages/container/acta-import-api", "--jq", ".name"], PLATFORM_REPO, env, timeout=30)
            self._preflight_status("Validando Terraform e o state que será usado…")
            self._run_preflight_command([tools["terraform"], "init", "-input=false", "-no-color"], PLATFORM_TERRAFORM_DIR, env, timeout=240)
            self._run_preflight_command([tools["terraform"], "validate", "-no-color"], PLATFORM_TERRAFORM_DIR, env, timeout=90)
            state_resources = set(self._run_preflight_command([tools["terraform"], "state", "list"], PLATFORM_TERRAFORM_DIR, env, timeout=45).splitlines())
            if not REBUILD_REQUIRED_STATE.issubset(state_resources):
                raise RuntimeError("O state não contém a VPC, a instância e o Elastic IP esperados. Não use o plano salvo; reconcilie o state antes de destruir.")
            plan_path = Path(tempfile.gettempdir()) / f"acta-destroy-{uuid.uuid4().hex}.tfplan"
            self._preflight_status("Gerando um plano de destruição novo; ainda sem apagar recursos…")
            self._run_preflight_command([tools["terraform"], "plan", "-destroy", "-input=false", "-no-color", "-lock-timeout=30s", "-out", str(plan_path)], PLATFORM_TERRAFORM_DIR, env, timeout=600)
            self._preflight_status("Lendo somente os nomes e as ações do plano…")
            plan_json = self._run_preflight_command([tools["terraform"], "show", "-json", str(plan_path)], PLATFORM_TERRAFORM_DIR, env, timeout=120)
            plan = json.loads(plan_json)
            resource_changes = plan.get("resource_changes") or []
            destroy_addresses = sorted({change.get("address", "") for change in resource_changes if "delete" in (change.get("change", {}).get("actions") or []) and change.get("address")})
            if not destroy_addresses or not REBUILD_REQUIRED_STATE.issubset(set(destroy_addresses)):
                raise RuntimeError("O plano novo não prevê remover os recursos centrais esperados. Nada foi apagado; confira conta, região e state.")
            unexpected_changes = [change.get("address", "recurso") for change in resource_changes if change.get("mode", "managed") == "managed" and (change.get("change", {}).get("actions") or []) != ["delete"]]
            if unexpected_changes:
                raise RuntimeError("O plano de destruição contém uma ação inesperada. Nada foi apagado; revise o Terraform manualmente.")
            target = {"account": account, "region": region, "branch": branch or "(sem branch)", "dirty": str(dirty_count)}
            self.root.after(0, lambda: self._finish_rebuild_preflight(target, destroy_addresses, plan_path, None))
        except Exception as exc:
            if plan_path is not None:
                plan_path.unlink(missing_ok=True)
            self.root.after(0, lambda message=str(exc): self._finish_rebuild_preflight({}, [], None, message))
    def _finish_rebuild_preflight(self, target: dict[str, str], resources: list[str], plan_path: Path | None, error: str | None) -> None:
        self.rebuild_busy = False
        self.rebuild_prepare_button.configure(state="normal")
        if error:
            self.rebuild_summary_var.set("Plano indisponível. A infraestrutura não foi alterada.")
            self._set_rebuild_status(error, "error")
            self._append_rebuild_log(error, "error")
            return
        self.rebuild_target = target
        self.destroy_plan_resources = resources
        self.destroy_plan_path = plan_path
        dirty = int(target["dirty"])
        self.rebuild_target_var.set(f"Conta AWS: {target['account']}")
        self.rebuild_region_var.set(f"Região do Terraform: {target['region']}")
        checkout_note = f"Branch: {target['branch']}"
        if dirty:
            checkout_note += f"  ·  {dirty} arquivo(s) local(is) modificado(s); serão usados como estão."
        else:
            checkout_note += "  ·  checkout sem alterações locais."
        self.rebuild_branch_var.set(checkout_note)
        self.rebuild_summary_var.set(f"Plano novo: {len(resources)} recurso(s) gerenciado(s) pelo Terraform serão removidos. Veja a lista no histórico abaixo.")
        self._append_rebuild_log(f"Alvo confirmado · conta {target['account']} · {target['region']} · branch {target['branch']}", "system")
        for address in resources:
            self._append_rebuild_log(f"  - {address}", "system")
        self._append_rebuild_log("Plano revisável pronto. Nenhum recurso foi alterado.", "system")
        self.rebuild_review_button.configure(state="normal")
        self._set_rebuild_status("Confira a conta, a região e os recursos listados antes de continuar.", "warning")
    def show_rebuild_confirmation(self) -> None:
        if self.destroy_plan_path is None or not self.destroy_plan_path.is_file() or self.rebuild_busy:
            self._set_rebuild_status("Prepare um plano novo antes de iniciar.", "error")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Confirmar destruição e reconstrução")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        frame = tk.Frame(dialog, bg=PALETTE["surface"], padx=22, pady=20)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Confirmar reconstrução", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 16)).pack(anchor="w")
        tk.Label(frame, text=f"Conta AWS {self.rebuild_target['account']} · {self.rebuild_target['region']}\nSerão removidos {len(self.destroy_plan_resources)} recursos do state mostrado na tela.", bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 9), justify="left", anchor="w").pack(fill="x", pady=(7, 13))
        tk.Label(frame, text="Credenciais Universal Auth do Infisical", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(0, 6))
        saved_client_id, saved_client_secret = load_infisical_credentials()
        credentials_note = "Credenciais carregadas do .env; usadas só nesta execução." if saved_client_id and saved_client_secret else "Preencha CLIENT_ID e CLIENT_SECRET no .env para carregar automaticamente."
        tk.Label(frame, text=credentials_note, bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))
        client_id_var = tk.StringVar(value=saved_client_id)
        client_secret_var = tk.StringVar(value=saved_client_secret)
        confirm_var = tk.StringVar()
        tk.Label(frame, text="Client ID", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI", 9)).pack(anchor="w")
        client_id_entry = ttk.Entry(frame, textvariable=client_id_var, width=58)
        client_id_entry.pack(fill="x", pady=(3, 9))
        tk.Label(frame, text="Client Secret", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI", 9)).pack(anchor="w")
        client_secret_entry = ttk.Entry(frame, textvariable=client_secret_var, show="●", width=58)
        client_secret_entry.pack(fill="x", pady=(3, 9))
        tk.Label(frame, text="Digite DESTRUIR ACTA para autorizar o plano acima", bg=PALETTE["surface"], fg="#A26013", font=("Segoe UI Semibold", 9)).pack(anchor="w")
        confirm_entry = ttk.Entry(frame, textvariable=confirm_var, width=58)
        confirm_entry.pack(fill="x", pady=(3, 11))
        acknowledged = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Conferi a conta e aceito remover esses recursos antes da reimplantação.", variable=acknowledged).pack(anchor="w", pady=(0, 12))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        start_button = ttk.Button(buttons, text="Apagar e implantar de novo", style="Danger.TButton", state="disabled")
        start_button.pack(side="right")
        def cancel() -> None:
            client_id_var.set("")
            client_secret_var.set("")
            confirm_var.set("")
            dialog.grab_release()
            dialog.destroy()
        ttk.Button(buttons, text="Voltar", command=cancel).pack(side="right", padx=(0, 8))
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        def update_button(*_args: object) -> None:
            ready = bool(client_id_var.get().strip() and client_secret_var.get() and confirm_var.get() == "DESTRUIR ACTA" and acknowledged.get())
            start_button.configure(state="normal" if ready else "disabled")
        client_id_var.trace_add("write", update_button)
        client_secret_var.trace_add("write", update_button)
        confirm_var.trace_add("write", update_button)
        acknowledged.trace_add("write", update_button)
        def confirm_and_start() -> None:
            client_id = client_id_var.get().strip()
            client_secret = client_secret_var.get()
            client_secret_var.set("")
            client_id_var.set("")
            confirm_var.set("")
            dialog.grab_release()
            dialog.destroy()
            self.start_rebuild(client_id, client_secret)
            client_id = ""
            client_secret = ""
        start_button.configure(command=confirm_and_start)
        client_id_entry.focus_set()
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - dialog.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
    def show_rebuild_resume_dialog(self) -> None:
        if not self.rebuild_destroy_completed or self.rebuild_busy:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Retomar implantação")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        frame = tk.Frame(dialog, bg=PALETTE["surface"], padx=22, pady=20)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Retomar a implantação", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 16)).pack(anchor="w")
        tk.Label(frame, text="A infraestrutura já foi removida. Esta ação roda o deploy.ps1 sem executar outra destruição.", bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 9), justify="left", wraplength=470).pack(anchor="w", fill="x", pady=(7, 13))
        saved_client_id, saved_client_secret = load_infisical_credentials()
        client_id_var = tk.StringVar(value=saved_client_id)
        client_secret_var = tk.StringVar(value=saved_client_secret)
        acknowledged = tk.BooleanVar(value=False)
        credentials_note = "Credenciais carregadas do .env." if saved_client_id and saved_client_secret else "Preencha CLIENT_ID e CLIENT_SECRET no .env para carregar automaticamente."
        tk.Label(frame, text=credentials_note, bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))
        tk.Label(frame, text="Client ID do Infisical", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI", 9)).pack(anchor="w")
        ttk.Entry(frame, textvariable=client_id_var, width=58).pack(fill="x", pady=(3, 9))
        tk.Label(frame, text="Client Secret do Infisical", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI", 9)).pack(anchor="w")
        ttk.Entry(frame, textvariable=client_secret_var, show="●", width=58).pack(fill="x", pady=(3, 10))
        ttk.Checkbutton(frame, text="Continuar a partir do state atual sem executar Terraform destroy.", variable=acknowledged).pack(anchor="w", pady=(0, 12))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        resume_button = ttk.Button(buttons, text="Continuar implantação", style="Primary.TButton", state="disabled")
        resume_button.pack(side="right")
        def cancel() -> None:
            client_id_var.set("")
            client_secret_var.set("")
            dialog.grab_release()
            dialog.destroy()
        ttk.Button(buttons, text="Voltar", command=cancel).pack(side="right", padx=(0, 8))
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        def update_button(*_args: object) -> None:
            ready = bool(client_id_var.get().strip() and client_secret_var.get() and acknowledged.get())
            resume_button.configure(state="normal" if ready else "disabled")
        client_id_var.trace_add("write", update_button)
        client_secret_var.trace_add("write", update_button)
        acknowledged.trace_add("write", update_button)
        def resume() -> None:
            client_id = client_id_var.get().strip()
            client_secret = client_secret_var.get()
            client_id_var.set("")
            client_secret_var.set("")
            dialog.grab_release()
            dialog.destroy()
            self._start_resume_deploy(client_id, client_secret)
            client_id = ""
            client_secret = ""
        resume_button.configure(command=resume)
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - dialog.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
    def start_rebuild(self, client_id: str, client_secret: str) -> None:
        plan_path = self.destroy_plan_path
        if plan_path is None or not plan_path.is_file():
            self._set_rebuild_status("O plano expirou. Prepare um plano novo antes de continuar.", "error")
            return
        self.rebuild_busy = True
        self.rebuild_destroy_completed = False
        self.rebuild_prepare_button.configure(state="disabled")
        self.rebuild_review_button.configure(state="disabled")
        self._set_rebuild_phase(1)
        self._set_rebuild_status("Removendo os recursos indicados no plano aprovado… mantenha o app aberto.", "busy")
        self._append_rebuild_log("Aplicando exclusivamente o plano de destruição recém-gerado.", "system")
        threading.Thread(target=self._destroy_then_deploy, args=(plan_path, client_id, client_secret), daemon=True).start()
    def _stream_rebuild_command(self, command: list[str], cwd: Path, env: dict[str, str], input_lines: list[str] | None = None) -> int:
        process = subprocess.Popen(
            command, cwd=cwd, env=env, stdin=subprocess.PIPE if input_lines is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        self.rebuild_process = process
        input_names = ("APLICAR", "CLIENT_ID", "CLIENT_SECRET")
        input_index = 0
        try:
            if process.stdout is not None:
                for line in process.stdout:
                    marker = line.strip()
                    if marker.startswith("APP_INPUT:"):
                        requested = marker.partition(":")[2]
                        if input_lines is None or process.stdin is None or input_index >= len(input_names) or requested != input_names[input_index]:
                            if process.stdin is not None:
                                process.stdin.close()
                            input_index = len(input_names)
                            continue
                        value = input_lines[input_index]
                        input_lines[input_index] = ""
                        process.stdin.write(value + "\n")
                        process.stdin.flush()
                        input_index += 1
                        if input_index == len(input_names):
                            process.stdin.close()
                        continue
                    self.root.after(0, lambda value=line: self._append_rebuild_log(value))
            return process.wait()
        finally:
            if input_lines is not None:
                input_lines[:] = [""] * len(input_lines)
            if process.stdin is not None and not process.stdin.closed:
                try:
                    process.stdin.close()
                except OSError:
                    pass
            self.rebuild_process = None
    def _destroy_then_deploy(self, plan_path: Path, client_id: str, client_secret: str) -> None:
        env = os.environ.copy()
        env["AWS_PROFILE"] = "default"
        try:
            terraform = shutil.which("terraform")
            powershell = shutil.which("pwsh.exe") or shutil.which("pwsh") or shutil.which("powershell.exe") or shutil.which("powershell")
            if not terraform or not powershell:
                raise RuntimeError("Terraform ou PowerShell deixou de estar disponível depois da revisão.")
            destroy_code = self._stream_rebuild_command([terraform, "apply", "-input=false", "-no-color", "-auto-approve", str(plan_path)], PLATFORM_TERRAFORM_DIR, env)
            plan_path.unlink(missing_ok=True)
            self.destroy_plan_path = None
            if destroy_code != 0:
                raise RuntimeError(f"A destruição foi interrompida pelo Terraform (código {destroy_code}); a implantação não foi iniciada.")
            self.root.after(0, lambda: (self._set_rebuild_phase(2), self._set_rebuild_status("Infraestrutura removida. Iniciando o deploy.ps1…", "busy"), self._append_rebuild_log("Arquivo de state mantido e atualizado. Iniciando bootstrap, GHCR, Infisical, Argo CD, rollouts e verificações.", "system")))
            self.rebuild_destroy_completed = True
            deploy_code = self._invoke_deploy_script(powershell, env, client_id, client_secret)
            client_id = ""
            client_secret = ""
            if deploy_code != 0:
                raise RuntimeError(f"O deploy.ps1 terminou com código {deploy_code}. A infraestrutura pode estar parcialmente implantada; confira o histórico antes de tentar novamente.")
            self.root.after(0, lambda: self._finish_rebuild_operation(None))
        except Exception as exc:
            if plan_path.exists():
                plan_path.unlink(missing_ok=True)
            self.root.after(0, lambda message=str(exc): self._finish_rebuild_operation(message))
    def _invoke_deploy_script(self, powershell: str, env: dict[str, str], client_id: str, client_secret: str) -> int:
        command = [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(PLATFORM_DEPLOY_SCRIPT), "-AppMode", "-ExpectedAccount", self.rebuild_target["account"]]
        input_lines = ["APLICAR", client_id, client_secret]
        client_id = ""
        client_secret = ""
        return self._stream_rebuild_command(command, PLATFORM_REPO, env, input_lines)
    def _start_resume_deploy(self, client_id: str, client_secret: str) -> None:
        if self.rebuild_busy or not self.rebuild_destroy_completed:
            return
        self.rebuild_busy = True
        self.rebuild_resume_button.configure(state="disabled")
        self._set_rebuild_phase(2)
        self._set_rebuild_status("Retomando o deploy sem nova destruição… mantenha o app aberto.", "busy")
        self._append_rebuild_log("Retomada solicitada; Terraform destroy não será chamado.", "system")
        threading.Thread(target=self._resume_deploy_work, args=(client_id, client_secret), daemon=True).start()
    def _resume_deploy_work(self, client_id: str, client_secret: str) -> None:
        try:
            powershell = shutil.which("pwsh.exe") or shutil.which("pwsh") or shutil.which("powershell.exe") or shutil.which("powershell")
            if not powershell:
                raise RuntimeError("PowerShell deixou de estar disponível.")
            env = os.environ.copy()
            env["AWS_PROFILE"] = "default"
            deploy_code = self._invoke_deploy_script(powershell, env, client_id, client_secret)
            client_id = ""
            client_secret = ""
            if deploy_code != 0:
                raise RuntimeError(f"O deploy.ps1 terminou com código {deploy_code}. Confira o histórico para decidir o próximo passo.")
            self.root.after(0, lambda: self._finish_rebuild_operation(None))
        except Exception as exc:
            self.root.after(0, lambda message=str(exc): self._finish_rebuild_operation(message))
    def _finish_rebuild_operation(self, error: str | None) -> None:
        self.rebuild_busy = False
        self.rebuild_process = None
        self.rebuild_prepare_button.configure(state="normal")
        if error:
            self._set_rebuild_status(error, "error")
            self._append_rebuild_log(error, "error")
            if self.rebuild_destroy_completed:
                self.rebuild_resume_button.configure(state="normal")
            return
        self.rebuild_destroy_completed = False
        self.rebuild_resume_button.configure(state="disabled")
        self._set_rebuild_phase(2)
        self._set_rebuild_status("Reconstrução concluída. Confira o resumo e as URLs no histórico.", "success")
        self._append_rebuild_log("Reconstrução concluída com sucesso.", "system")
