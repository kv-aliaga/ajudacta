from __future__ import annotations

import base64
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import boto3
from botocore.config import Config

from ..constants import KUBECONFIG_PATH, PALETTE, PLATFORM_REPO
from ..ui.markdown_terminal import MarkdownTerminal


class DiagnosticsMixin:
    def build_diagnostics_page(self, page: ttk.Frame) -> None:
        outer = ttk.Frame(page, padding=(22, 20, 22, 16))
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 13))
        titles = ttk.Frame(header)
        titles.pack(side="left", fill="x", expand=True)
        ttk.Label(titles, text="Diagnóstico ACTA", style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text="Verifique o cluster e investigue os resultados com o Codex.", style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        header_actions = ttk.Frame(header)
        header_actions.pack(side="right", anchor="n")
        self.argo_gui_button = ttk.Button(header_actions, text="Abrir Argo CD", command=self.open_argocd_gui)
        self.argo_gui_button.pack(side="left", padx=(0, 8))
        self.deep_analysis_button = ttk.Button(header_actions, text="Análise profunda", style="Codex.TButton", command=self.start_deep_analysis)
        self.deep_analysis_button.pack(side="left", padx=(0, 8))
        self.diagnostics_button = ttk.Button(header_actions, text="Executar diagnóstico", style="Primary.TButton", command=self.start_diagnostics)
        self.diagnostics_button.pack(side="left")
        summary = tk.Frame(outer, bg=PALETTE["blue_pale"], highlightbackground="#D6E3FF", highlightthickness=1, bd=0)
        summary.pack(fill="x", pady=(0, 10))
        self.diagnostics_summary = tk.Label(summary, text="Pronto para conferir o estado atual. As consultas são somente de leitura.", bg=PALETTE["blue_pale"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 9), padx=13, pady=9, anchor="w", justify="left")
        self.diagnostics_summary.pack(fill="x")
        split_view = tk.Frame(outer, bg=PALETTE["canvas"])
        split_view.pack(fill="both", expand=True)
        split_view.grid_columnconfigure(0, weight=1, uniform="diagnostic_halves")
        split_view.grid_columnconfigure(1, weight=1, uniform="diagnostic_halves")
        split_view.grid_rowconfigure(0, weight=1)
        table_panel = tk.Frame(split_view, bg=PALETTE["surface"], highlightbackground=PALETTE["line"], highlightthickness=1, bd=0)
        terminal_panel = tk.Frame(split_view, bg="#050805", highlightbackground="#26352A", highlightthickness=1, bd=0)
        table_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        terminal_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        table_panel.grid_rowconfigure(1, weight=1)
        table_panel.grid_columnconfigure(0, weight=1)
        table_header = tk.Frame(table_panel, bg=PALETTE["surface"], padx=11, pady=9)
        table_header.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(table_header, text="RESULTADOS DO DIAGNÓSTICO", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 9)).pack(side="left")
        self.diagnostics_count = tk.Label(table_header, text="0 verificações", bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 8))
        self.diagnostics_count.pack(side="right")
        self.diagnostics_table = ttk.Treeview(table_panel, columns=("area", "item", "status", "detail"), show="headings", height=18)
        self.diagnostics_table.bind("<Double-1>", self.track_selected_rollout)
        for key, label, width in (("area", "Área", 85), ("item", "Verificação", 125), ("status", "Estado", 72), ("detail", "Detalhes", 245)):
            self.diagnostics_table.heading(key, text=label)
            self.diagnostics_table.column(key, width=width, minwidth=54 if key == "status" else 75, anchor="w", stretch=(key == "detail"))
        self.diagnostics_table.tag_configure("ok", foreground=PALETTE["green"])
        self.diagnostics_table.tag_configure("warn", foreground="#A26013")
        self.diagnostics_table.tag_configure("error", foreground=PALETTE["red"])
        self.diagnostics_table.tag_configure("info", foreground=PALETTE["muted"])
        table_scroll = ttk.Scrollbar(table_panel, orient="vertical", command=self.diagnostics_table.yview)
        table_xscroll = ttk.Scrollbar(table_panel, orient="horizontal", command=self.diagnostics_table.xview)
        self.diagnostics_table.configure(yscrollcommand=table_scroll.set, xscrollcommand=table_xscroll.set)
        self.diagnostics_table.grid(row=1, column=0, sticky="nsew", padx=(8, 0))
        table_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 8))
        table_xscroll.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        terminal_chrome = tk.Frame(terminal_panel, bg="#111A14", padx=12, pady=9)
        terminal_chrome.pack(fill="x")
        tk.Label(terminal_chrome, text="CODEX  ·  ANÁLISE EM SESSÃO", bg="#111A14", fg="#A7B8A9", font=("Consolas", 9, "bold")).pack(side="left")
        ttk.Button(terminal_chrome, text="Copiar tudo", command=self.copy_diagnostics_terminal).pack(side="right", padx=(8, 0))
        self.deep_model_badge = tk.Label(terminal_chrome, text="GPT-6 LUNA", bg="#17351E", fg="#7DF58D", font=("Consolas", 9, "bold"), padx=9, pady=4)
        self.deep_model_badge.pack(side="right")
        terminal_wrap = tk.Frame(terminal_panel, bg="#050805")
        terminal_wrap.pack(fill="both", expand=True, padx=8, pady=(7, 5))
        self.deep_terminal = MarkdownTerminal(terminal_wrap)
        self.deep_terminal.pack(side="left", fill="both", expand=True)
        self._deep_append("A análise profunda usa GPT-6 Luna e recebe a tabela completa à esquerda.\n", "system")
        self._deep_append("Clique em Análise profunda para iniciar; se ainda não houver diagnóstico, o app executará as verificações primeiro.\n", "system")
        composer = tk.Frame(terminal_panel, bg="#111A14", padx=8, pady=8)
        composer.pack(fill="x")
        self.deep_input_var = tk.StringVar()
        self.deep_input = ttk.Entry(composer, textvariable=self.deep_input_var)
        self.deep_input.pack(side="left", fill="x", expand=True, padx=(0, 7))
        self.deep_send_button = ttk.Button(composer, text="Enviar", command=self.send_deep_followup, state="disabled")
        self.deep_send_button.pack(side="left")
        self.deep_stop_button = ttk.Button(composer, text="Parar", command=self.stop_deep_analysis, state="disabled")
        self.deep_stop_button.pack(side="left", padx=(6, 0))
        self.deep_input.bind("<Return>", lambda _event: self.send_deep_followup())
        self.diagnostics_footer = ttk.Label(outer, text="Perfil AWS default · kubeconfig ACTA · atualize o diagnóstico antes de investigar novas alterações.", style="Muted.TLabel")
        self.diagnostics_footer.pack(anchor="w", pady=(7, 0))
    def copy_diagnostics_terminal(self) -> None:
        if self.deep_terminal is None or not self.deep_terminal.winfo_exists():
            return
        self.deep_terminal.copy_all()
        self._deep_append("\nTerminal copiado para a área de transferência.\n", "system")
    def start_diagnostics(self) -> None:
        if self.diagnostics_busy:
            return
        self.diagnostics_busy = True
        self.diagnostics_button.configure(state="disabled")
        self.diagnostics_summary.configure(text="Consultando o cluster e as URLs públicas…")
        self.diagnostics_footer.configure(text="Aguarde. Nenhum recurso será alterado.")
        self.diagnostics_table.delete(*self.diagnostics_table.get_children())
        self.diagnostics_rows = []
        self.diagnostics_count.configure(text="coletando…")
        threading.Thread(target=self._diagnostics_work, daemon=True).start()
    def _diagnostics_work(self) -> None:
        rows: list[tuple[str, str, str, str]] = []
        def add(area: str, item: str, status: str, detail: str) -> None:
            rows.append((area, item, status, detail))
        env = os.environ.copy()
        env["KUBECONFIG"] = str(KUBECONFIG_PATH)
        try:
            session = boto3.Session(profile_name="default")
            region = session.region_name or "região não configurada"
            config = Config(connect_timeout=8, read_timeout=12, retries={"total_max_attempts": 1})
            identity = session.client("sts", config=config).get_caller_identity()
            add("AWS", "Perfil default", "OK", f"Conta {identity.get('Account', '?')} · {region}")
            try:
                addresses = session.client("ec2", region_name=region, config=config).describe_addresses(Filters=[{"Name": "tag:Name", "Values": ["acta-prod-k3s"]}])["Addresses"]
                address = addresses[0] if len(addresses) == 1 else {}
                public_ip = address.get("PublicIp", "")
                if not public_ip or not address.get("AssociationId"):
                    raise ValueError(f"Elastic IP esperado ausente ou não associado; encontrados {len(addresses)}.")
                host = f"{public_ip.replace('.', '-')}.sslip.io"
                add("AWS", "Elastic IP ACTA", "OK", public_ip)
                endpoints = [
                    ("Auth API", f"https://acta-auth-api.{host}/api/v1/health"),
                    ("PostgreSQL API", f"https://acta-pg-api.{host}/api/v1/health"),
                    ("MongoDB API", f"https://acta-mongo-api.{host}/api/v1/health"),
                    ("Import API", f"https://acta-import-api.{host}/docs"),
                    ("FCM API", f"https://acta-fcm-api.{host}/health"),
                    ("AI", f"https://acta-ai.{host}/health"),
                    ("MCP", f"https://acta-mcp.{host}/health"),
                ]
                def check_endpoint(endpoint: tuple[str, str]) -> tuple[str, str, str]:
                    name, url = endpoint
                    try:
                        request = Request(url, headers={"User-Agent": "AWS-Default-Profile/1.0"})
                        with urlopen(request, timeout=12) as response:
                            code = response.status
                    except HTTPError as exc:
                        code = exc.code
                    except (URLError, TimeoutError, OSError) as exc:
                        reason = getattr(exc, "reason", exc)
                        return name, "Falha", type(reason).__name__
                    return name, ("OK" if code == 200 else "Erro"), f"HTTP {code} · {url}"
                with ThreadPoolExecutor(max_workers=len(endpoints)) as pool:
                    for name, status, detail in pool.map(check_endpoint, endpoints):
                        add("API pública", name, status, detail)
            except Exception as exc:
                add("AWS", "Elastic IP / APIs", "Erro", str(exc) if isinstance(exc, ValueError) else self.aws_error_code(exc))
        except Exception as exc:
            add("AWS", "Perfil default", "Erro", self.aws_error_code(exc))
        def kubectl_json(args: list[str]) -> dict | None:
            try:
                completed = subprocess.run(["kubectl", *args], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=35, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
                if completed.returncode:
                    return None
                parsed = json.loads(completed.stdout)
                return parsed if isinstance(parsed, dict) else None
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
                return None
        deployments = kubectl_json(["get", "deployments", "-n", "acta-prod", "-o", "json"])
        if deployments is None:
            add("Kubernetes", "Deployments acta-prod", "Erro", "kubectl indisponível, kubeconfig inacessível ou namespace sem resposta.")
        else:
            found = {item.get("metadata", {}).get("name"): item for item in deployments.get("items", [])}
            expected = ("acta-auth-api", "acta-pg-api", "acta-mongo-api", "acta-import-api", "acta-import-worker", "acta-ai", "acta-mcp", "acta-fcm-api")
            for name in expected:
                item = found.get(name)
                if item is None:
                    add("Kubernetes", name, "Ausente", "Deployment não encontrado em acta-prod.")
                    continue
                spec = item.get("spec", {})
                state = item.get("status", {})
                desired = spec.get("replicas", 1)
                ready = state.get("readyReplicas", 0)
                updated = state.get("updatedReplicas", 0)
                status = "OK" if ready >= desired and updated >= desired else "Atenção"
                add("Kubernetes", name, status, f"Réplicas prontas {ready}/{desired} · atualizadas {updated}/{desired}")
        try:
            secret_check = subprocess.run(["kubectl", "get", "secret", "infisical-universal-auth", "-n", "acta-prod", "-o", "name"], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
            secret_exists = secret_check.returncode == 0 and bool(secret_check.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            secret_exists = False
        if secret_exists:
            add("Infisical", "Credencial Universal Auth", "OK", "Secret do Kubernetes presente; nenhum valor foi lido ou exibido.")
        else:
            add("Infisical", "Credencial Universal Auth", "Erro", "Secret infisical-universal-auth ausente ou cluster inacessível.")
        infisical = kubectl_json(["get", "infisicalsecrets", "-n", "acta-prod", "-o", "json"])
        if infisical is None:
            add("Infisical", "Sincronização de secrets", "Atenção", "Não foi possível consultar o status dos recursos InfisicalSecret.")
        else:
            items = infisical.get("items", [])
            if not items:
                add("Infisical", "Sincronização de secrets", "Atenção", "Nenhum InfisicalSecret encontrado em acta-prod.")
            for item in items:
                name = item.get("metadata", {}).get("name", "InfisicalSecret")
                conditions = item.get("status", {}).get("conditions", [])
                ready_condition = next((condition for condition in conditions if condition.get("type", "").lower() in ("ready", "synced")), None)
                if ready_condition and ready_condition.get("status") == "True":
                    add("Infisical", name, "OK", "Sincronização confirmada.")
                elif ready_condition:
                    add("Infisical", name, "Atenção", ready_condition.get("message") or ready_condition.get("reason") or "Aguardando sincronização.")
                else:
                    add("Infisical", name, "Atenção", "Ainda sem condição Ready/Synced publicada pelo operador.")
        argo = kubectl_json(["get", "application", "acta-prod", "-n", "argocd", "-o", "json"])
        if argo is None:
            add("Argo CD", "Aplicação acta-prod", "Erro", "Aplicação ausente ou cluster inacessível.")
        else:
            sync = argo.get("status", {}).get("sync", {}).get("status", "Desconhecido")
            health = argo.get("status", {}).get("health", {}).get("status", "Desconhecido")
            status = "OK" if sync == "Synced" and health == "Healthy" else "Atenção"
            add("Argo CD", "Aplicação acta-prod", status, f"Sincronização {sync} · saúde {health}")
        certificates = kubectl_json(["get", "certificates", "-n", "acta-prod", "-o", "json"])
        if certificates is None:
            add("TLS", "Certificados", "Atenção", "Não foi possível consultar os certificados do namespace acta-prod.")
        else:
            items = certificates.get("items", [])
            if not items:
                add("TLS", "Certificados", "Atenção", "Nenhum certificado encontrado.")
            for item in items:
                name = item.get("metadata", {}).get("name", "Certificate")
                ready = any(condition.get("type") == "Ready" and condition.get("status") == "True" for condition in item.get("status", {}).get("conditions", []))
                add("TLS", name, "OK" if ready else "Atenção", "Certificado pronto." if ready else "Aguardando emissão ou renovação.")
        self.root.after(0, lambda result=rows: self.finish_diagnostics(result))
    def finish_diagnostics(self, rows: list[tuple[str, str, str, str]]) -> None:
        self.diagnostics_busy = False
        self.diagnostics_rows = list(rows)
        self.diagnostics_count.configure(text=f"{len(rows)} verificações")
        self.diagnostics_button.configure(state="normal")
        colors = {"OK": "ok", "Atenção": "warn", "Erro": "error", "Falha": "error", "Ausente": "error"}
        for area, item, status, detail in rows:
            self.diagnostics_table.insert("", "end", values=(area, item, status, detail), tags=(colors.get(status, "info"),))
        failures = sum(status in ("Erro", "Falha", "Ausente") for _, _, status, _ in rows)
        warnings = sum(status == "Atenção" for _, _, status, _ in rows)
        okay = sum(status == "OK" for _, _, status, _ in rows)
        result = "Tudo certo" if failures == 0 and warnings == 0 else ("Há itens para revisar" if failures or warnings else "Diagnóstico concluído")
        self.diagnostics_summary.configure(text=f"{result} · {okay} verificações OK · {warnings} atenção · {failures} falhas")
        self.diagnostics_footer.configure(text=f"Atualizado em {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')} · consulta somente leitura")
        if self.diagnostics_autostart_deep:
            self.diagnostics_autostart_deep = False
            self.root.after(150, self._launch_deep_analysis)
    def track_selected_rollout(self, _event: tk.Event | None = None) -> None:
        selection = self.diagnostics_table.selection()
        if not selection:
            return
        values = self.diagnostics_table.item(selection[0], "values")
        if len(values) >= 2 and values[0] == "Argo CD" and values[1] == "Aplicação acta-prod":
            self.open_argocd_gui()
            return
        if len(values) < 2 or values[0] != "Kubernetes":
            return
        deployment = str(values[1])
        if not re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", deployment):
            return
        self._deep_append(f"\n$ kubectl rollout status deployment/{deployment} -n acta-prod --watch\n", "command")
        self._deep_append(f"Acompanhando rollout de {deployment}…\n", "system")
        self.root.after(0, lambda: self.deep_terminal.see("end") if self.deep_terminal else None)
        threading.Thread(target=self._track_rollout_worker, args=(deployment,), daemon=True).start()
    def open_argocd_gui(self) -> None:
        process = self.argocd_port_forward
        if process is not None and process.poll() is None:
            webbrowser.open("https://127.0.0.1:18080")
            self.diagnostics_footer.configure(text="Argo CD aberto em https://127.0.0.1:18080 · túnel local ativo enquanto o app estiver aberto.")
            return
        self.argo_gui_button.configure(state="disabled")
        self.diagnostics_footer.configure(text="Abrindo conexão segura local para o Argo CD…")
        threading.Thread(target=self._start_argocd_port_forward, daemon=True).start()
    def _start_argocd_port_forward(self) -> None:
        env = os.environ.copy()
        env["KUBECONFIG"] = str(KUBECONFIG_PATH)
        process = None
        try:
            with socket.create_connection(("127.0.0.1", 18080), timeout=0.3):
                raise RuntimeError("A porta local 18080 já está em uso. Feche o serviço que a utiliza e tente novamente.")
        except OSError:
            pass
        except RuntimeError as exc:
            self.root.after(0, lambda message=str(exc): self._finish_argocd_open(None, message))
            return
        try:
            process = subprocess.Popen(
                ["kubectl", "--kubeconfig", str(KUBECONFIG_PATH), "port-forward", "--address", "127.0.0.1", "svc/argocd-server", "18080:443", "-n", "argocd"],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            for _ in range(50):
                if process.poll() is not None:
                    raise RuntimeError("kubectl encerrou a conexão. Confira o kubeconfig e o acesso ao cluster.")
                try:
                    with socket.create_connection(("127.0.0.1", 18080), timeout=0.2):
                        self.argocd_port_forward = process
                        self.root.after(0, lambda: self._finish_argocd_open(process, None))
                        return
                except OSError:
                    threading.Event().wait(0.2)
            raise RuntimeError("O túnel para o Argo CD não ficou pronto no tempo esperado.")
        except (OSError, RuntimeError) as exc:
            if process is not None and process.poll() is None:
                process.terminate()
            self.root.after(0, lambda message=str(exc): self._finish_argocd_open(None, message))
    def _finish_argocd_open(self, process: subprocess.Popen | None, error: str | None) -> None:
        self.argo_gui_button.configure(state="normal")
        if error:
            self.diagnostics_footer.configure(text=f"Não foi possível abrir o Argo CD: {error}")
            return
        self.argocd_port_forward = process
        webbrowser.open("https://127.0.0.1:18080")
        self.diagnostics_footer.configure(text="Argo CD aberto em https://127.0.0.1:18080 · túnel local ativo enquanto o app estiver aberto.")
        self._deep_append("\nArgo CD aberto no navegador. Consultando a credencial inicial…\n", "system")
        threading.Thread(target=self._load_argocd_login, daemon=True).start()
    def _load_argocd_login(self) -> None:
        env = os.environ.copy()
        env["KUBECONFIG"] = str(KUBECONFIG_PATH)
        try:
            completed = subprocess.run(
                ["kubectl", "get", "secret", "argocd-initial-admin-secret", "-n", "argocd", "-o", "jsonpath={.data.password}"],
                env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
            if completed.returncode or not completed.stdout.strip():
                message = "Usuário: admin\nSenha inicial indisponível: o segredo pode ter sido removido ou a senha já pode ter sido trocada."
                self.root.after(0, lambda value=message: self._deep_append(value + "\n", "system"))
                return
            password = base64.b64decode(completed.stdout.strip()).decode("utf-8")
            self.root.after(0, lambda value=password: self._deep_append(f"Usuário: admin\nSenha inicial: {value}\n", "system"))
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            self.root.after(0, lambda error=str(exc): self._deep_append(f"Não foi possível consultar a senha inicial do Argo CD: {error}\n", "error"))
    def _track_rollout_worker(self, deployment: str) -> None:
        env = os.environ.copy()
        env["KUBECONFIG"] = str(KUBECONFIG_PATH)
        try:
            process = subprocess.Popen(["kubectl", "rollout", "status", f"deployment/{deployment}", "-n", "acta-prod", "--watch"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
            assert process.stdout is not None
            for line in process.stdout:
                self.root.after(0, lambda text=line: self._deep_append(text, "system"))
            code = process.wait()
            self.root.after(0, lambda: self._deep_append("Acompanhamento concluído.\n" if code == 0 else f"kubectl encerrou com código {code}.\n", "system" if code == 0 else "error"))
            if code != 0:
                self._collect_rollout_diagnostics(deployment, env)
        except OSError as exc:
            self.root.after(0, lambda: self._deep_append(f"Não foi possível iniciar kubectl: {exc}\n", "error"))
    def _collect_rollout_diagnostics(self, deployment: str, env: dict[str, str]) -> None:
        commands = [
            ("Deployment", ["get", "deployment", deployment, "-n", "acta-prod", "-o", "wide"]),
            ("Descrição do deployment", ["describe", "deployment", deployment, "-n", "acta-prod"]),
            ("Pods relacionados", ["get", "pods", "-n", "acta-prod", "-l", f"app.kubernetes.io/name={deployment}", "-o", "wide"]),
            ("Eventos recentes", ["get", "events", "-n", "acta-prod", "--field-selector", "type=Warning", "--sort-by=.lastTimestamp"]),
        ]
        self.root.after(0, lambda: self._deep_append(f"\nColetando diagnóstico somente de leitura para {deployment}…\n", "system"))
        for title, args in commands:
            command_text = " ".join(args)
            self.root.after(0, lambda text=command_text: self._deep_append(f"\n$ kubectl {text}\n", "command"))
            try:
                process = subprocess.Popen(["kubectl", *args], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
                assert process.stdout is not None
                for line in process.stdout:
                    self.root.after(0, lambda text=line: self._deep_append(text, "system"))
                code = process.wait()
                if code:
                    self.root.after(0, lambda label=title, status=code: self._deep_append(f"Comando '{label}' encerrou com código {status}.\n", "error"))
            except OSError as exc:
                self.root.after(0, lambda error=str(exc): self._deep_append(f"Falha ao coletar diagnóstico: {error}\n", "error"))
        self.root.after(0, lambda: self._deep_append("\nDiagnóstico concluído.\n", "system"))
    def _deep_append(self, message: str, tag: str = "codex") -> None:
        terminal = self.deep_terminal
        if terminal is None or not terminal.winfo_exists():
            return
        terminal.append_text(message, tag)
    def _deep_append_markdown(self, markdown: str, base_tag: str = "codex") -> None:
        terminal = self.deep_terminal
        if terminal is not None and terminal.winfo_exists():
            terminal.append_markdown(markdown, base_tag)
    def _start_deep_stream(self, mark_name: str) -> None:
        terminal = self.deep_terminal
        if terminal is None or not terminal.winfo_exists():
            return
        terminal.begin_stream()
    def _finish_deep_stream(self, mark_name: str, markdown: str) -> None:
        terminal = self.deep_terminal
        if terminal is None or not terminal.winfo_exists():
            return
        terminal.finish_stream(markdown)
        terminal.append_text("\n")
    def start_deep_analysis(self) -> None:
        if self.deep_running:
            self._deep_append("A análise atual ainda está em andamento.\n", "system")
            return
        if self.diagnostics_busy:
            self.diagnostics_autostart_deep = True
            self.diagnostics_summary.configure(text="O diagnóstico está em andamento; a análise profunda começará assim que a tabela ficar pronta.")
            return
        if not self.diagnostics_rows:
            self.diagnostics_autostart_deep = True
            self._deep_append("Executando diagnóstico antes de iniciar a análise…\n", "system")
            self.start_diagnostics()
            return
        self._launch_deep_analysis()
    def _launch_deep_analysis(self) -> None:
        if self.deep_running or not self.diagnostics_rows:
            return
        prompt = self._build_deep_prompt()
        self._deep_append("\n$ codex exec --model gpt-6-luna --sandbox read-only\n", "command")
        self._deep_append("=== PROMPT ENVIADO · CONTEXTO + TABELA COMPLETA ===\n", "system")
        self._deep_append_markdown(prompt, base_tag="human")
        self._deep_append("\n=== RESPOSTA DO CODEX ===\n\n", "system")
        self.deep_analysis_button.configure(state="disabled")
        self.deep_send_button.configure(state="disabled")
        threading.Thread(target=self._run_deep_analysis, args=(prompt, self.deep_session_id), daemon=True).start()
    def _build_deep_prompt(self) -> str:
        table = ["| Área | Verificação | Estado | Detalhes |", "|---|---|---|---|"]
        for area, item, status, detail in self.diagnostics_rows:
            cells = (area, item, status, detail)
            table.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ") for value in cells) + " |")
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        summary = self.diagnostics_summary.cget("text")
        return f"""Faça uma análise profunda do estado atual das APIs ACTA. Responda em português brasileiro, com diagnóstico claro, evidências da tabela, hipóteses ordenadas por probabilidade e próximos passos seguros. Separe o que a tabela prova do que ainda precisa ser confirmado. Se faltarem evidências, diga exatamente quais verificações de leitura ajudam a confirmar.
## CONTEXTO DO APP
- Horário da coleta: {timestamp}.
- Resumo mostrado pelo app: {summary}.
- Repositório de infraestrutura e implantação: {PLATFORM_REPO}.
- Namespace das APIs: acta-prod; namespace do Argo CD: argocd.
- O app consulta o perfil AWS default, o Elastic IP marcado acta-prod-k3s, as réplicas Kubernetes, os recursos InfisicalSecret, o Secret infisical-universal-auth sem ler seus valores, a aplicação Argo CD acta-prod, os certificados e URLs públicas /health (ou /docs para Import API).
- As URLs são verificações HTTP externas. Estado HTTP e estado de readiness dos pods são evidências diferentes.
- O fluxo de reimplantação documentado está em {Path(r'C:\Users\daviramOS-ieg\Desktop\ultima-dancacta\agents\Handshake.md')}; consulte o documento apenas como contexto operacional e não execute seus passos.
## TABELA COMPLETA DO DIAGNÓSTICO
{chr(10).join(table)}
## LIMITES DE SEGURANÇA
- Esta sessão é somente para análise. Não altere recursos, arquivos ou configurações; não execute deploy, Terraform apply/destroy, comandos AWS mutáveis, kubectl apply/delete/patch/scale, Helm, SSH ou Git que altere o checkout.
- Não leia .env, arquivos de state Terraform, kubeconfig, credenciais AWS, chaves privadas nem conteúdo de Secrets. Não solicite nem reproduza valores de segredo.
- Use a tabela como evidência inicial e, se necessário, consulte apenas documentação e manifests versionados do repositório para explicar dependências e nomes. Não conclua que um secret está correto apenas porque o objeto existe.
- Não invente resultados de comandos que não foram executados. Termine com uma lista curta de próximos passos seguros, sem executar mudanças."""
    def _codex_command_prefix(self) -> list[str]:
        appdata = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        npm_dir = appdata / "npm"
        executable = npm_dir / "node_modules" / "@openai" / "codex" / "node_modules" / "@openai" / "codex-win32-x64" / "vendor" / "x86_64-pc-windows-msvc" / "bin" / "codex.exe"
        if executable.is_file():
            return [str(executable)]
        powershell = shutil.which("pwsh.exe") or shutil.which("pwsh") or shutil.which("powershell.exe") or shutil.which("powershell")
        script = npm_dir / "codex.ps1"
        if powershell and script.is_file():
            return [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        raise FileNotFoundError("Não encontrei o Codex CLI instalado neste computador.")
    def send_deep_followup(self) -> None:
        prompt = self.deep_input_var.get().strip()
        if not prompt or self.deep_running or not self.deep_session_id:
            return
        self.deep_input_var.set("")
        self.deep_send_button.configure(state="disabled")
        self._deep_append(f"\n> {prompt}\n\n", "human")
        threading.Thread(target=self._run_deep_analysis, args=(prompt, self.deep_session_id), daemon=True).start()
    def _run_deep_analysis(self, prompt: str, session_id: str | None) -> None:
        self.deep_running = True
        self.root.after(0, lambda: self.deep_stop_button.configure(state="normal"))
        try:
            command = self._codex_command_prefix()
            if session_id:
                command += ["exec", "resume", "--json", "--model", "gpt-6-luna", session_id, "-"]
            else:
                command += ["exec", "--json", "--model", "gpt-6-luna", "--sandbox", "read-only", "-C", str(PLATFORM_REPO), "-"]
            process = subprocess.Popen(command, cwd=str(PLATFORM_REPO), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
            self.deep_process = process
            if process.stdin is None or process.stdout is None:
                raise RuntimeError("Não foi possível abrir o canal da sessão Codex.")
            process.stdin.write(prompt)
            process.stdin.close()
            item_types: dict[str, str] = {}
            streamed_items: set[str] = set()
            response_markers: dict[str, str] = {}
            response_buffers: dict[str, str] = {}
            for raw_line in process.stdout:
                line = raw_line.rstrip("\r\n")
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    self.root.after(0, lambda text=line: self._deep_append(text + "\n", "system"))
                    continue
                event_type = event.get("type", "")
                if event_type == "thread.started":
                    thread_id = event.get("thread_id")
                    if thread_id:
                        self.deep_session_id = str(thread_id)
                        self.root.after(0, lambda: self._deep_append("Sessão Codex pronta · GPT-6 Luna\n\n", "system"))
                elif event_type == "item.started":
                    item = event.get("item", {})
                    item_id = str(item.get("id", ""))
                    item_type = str(item.get("type", ""))
                    item_types[item_id] = item_type
                    if item_type == "agent_message":
                        marker = "deep_response_" + re.sub(r"[^A-Za-z0-9_]", "_", item_id)
                        response_markers[item_id] = marker
                        response_buffers[item_id] = ""
                        self.root.after(0, lambda mark_name=marker: self._start_deep_stream(mark_name))
                    elif item_type == "command_execution":
                        command_text = str(item.get("command", "comando de leitura"))
                        self.root.after(0, lambda text=command_text: self._deep_append("$ " + text + "\n", "command"))
                elif event_type == "item.delta":
                    item_id = str(event.get("item_id", ""))
                    delta = event.get("delta")
                    if item_types.get(item_id) == "agent_message" and isinstance(delta, str):
                        streamed_items.add(item_id)
                        response_buffers[item_id] = response_buffers.get(item_id, "") + delta
                        self.root.after(0, lambda text=delta: self._deep_append(text))
                elif event_type == "item.completed":
                    item = event.get("item", {})
                    item_id = str(item.get("id", ""))
                    if item.get("type") == "agent_message":
                        text = str(item.get("text", "") or response_buffers.get(item_id, ""))
                        if item_id in streamed_items and item_id in response_markers:
                            marker = response_markers[item_id]
                            self.root.after(0, lambda output=text, mark_name=marker: self._finish_deep_stream(mark_name, output))
                        elif text:
                            self.root.after(0, lambda output=text: self._deep_append_markdown(output + "\n"))
                    elif item.get("type") == "command_execution":
                        exit_code = item.get("exit_code")
                        message = "   leitura concluída\n" if exit_code == 0 else f"   comando terminou com código {exit_code}\n"
                        self.root.after(0, lambda text=message: self._deep_append(text, "system" if exit_code == 0 else "error"))
                elif event_type == "turn.completed":
                    self.root.after(0, lambda: self._deep_append("\n\nAnálise concluída. Você pode enviar outra pergunta nesta mesma sessão.\n", "system"))
                elif event_type == "error":
                    message = str(event.get("message", "Falha reportada pelo Codex."))
                    self.root.after(0, lambda text=message: self._deep_append("\nCodex: " + text + "\n", "error"))
            return_code = process.wait()
            if return_code != 0:
                self.root.after(0, lambda code=return_code: self._deep_append(f"\nA sessão encerrou com código {code}. Confira o login e a instalação do Codex CLI.\n", "error"))
        except Exception as exc:
            self.root.after(0, lambda error=str(exc): self._deep_append(f"\nFalha ao iniciar/continuar o Codex: {error}\n", "error"))
        finally:
            self.deep_process = None
            self.deep_running = False
            self.root.after(0, self._finish_deep_turn)
    def _finish_deep_turn(self) -> None:
        if self.deep_terminal is None or not self.deep_terminal.winfo_exists():
            return
        self.deep_stop_button.configure(state="disabled")
        self.deep_analysis_button.configure(state="normal")
        self.deep_send_button.configure(state="normal" if self.deep_session_id else "disabled")
        if self.deep_session_id:
            self.deep_input.focus_set()
    def stop_deep_analysis(self) -> None:
        process = self.deep_process
        if process is not None and process.poll() is None:
            process.terminate()
            self._deep_append("\nSessão interrompida pelo usuário.\n", "error")
    def close_deep_analysis(self) -> None:
        if self.deep_running and self.deep_process is not None and self.deep_process.poll() is None:
            self.deep_process.terminate()
