from __future__ import annotations

import base64
import json
import ipaddress
import os
import re
import socket
import subprocess
import threading
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
import tkinter as tk
from tkinter import messagebox, ttk

import boto3
from botocore.config import Config

from ..constants import KUBECONFIG_PATH, PALETTE
from ..ui.markdown_terminal import MarkdownTerminal


ROLLOUT_APIS = {
    "acta-auth-api": ("/api/v1/health", "auth-api"),
    "acta-pg-api": ("/api/v1/health", "pg-api"),
    "acta-fcm-api": ("/health", "fcm-api"),
    "acta-mongo-api": ("/api/v1/health", "mongo-api"),
    "acta-import-api": ("/docs", "import-api"),
    "acta-ai": ("/health", "ai"),
    "acta-mcp": ("/health", "mcp"),
}

ROLLOUT_INFISICAL_RESOURCES = {
    "acta-auth-api": "acta-auth-api-secrets",
    "acta-pg-api": "acta-pg-api-secrets",
    "acta-fcm-api": "acta-fcm-api-secrets",
    "acta-mongo-api": "acta-mongo-api-secrets",
    "acta-import-api": "acta-import-api-secrets",
    "acta-ai": "acta-ai-secrets",
    "acta-mcp": "acta-mcp-secrets",
}


class RolloutMixin:
    def build_rollout_page(self, page: ttk.Frame) -> None:
        outer = ttk.Frame(page, padding=(22, 20, 22, 16))
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 12))
        titles = ttk.Frame(header)
        titles.pack(side="left", fill="x", expand=True)
        ttk.Label(titles, text="Rollout individual das APIs", style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text="Escolha um serviço. O app valida acesso, inspeciona o estado e acompanha somente essa API.", style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        controls = ttk.Frame(header)
        controls.pack(side="right", anchor="n")
        self.rollout_service_var = tk.StringVar(value=next(iter(ROLLOUT_APIS)))
        self.rollout_service_box = ttk.Combobox(controls, textvariable=self.rollout_service_var, values=tuple(ROLLOUT_APIS), state="readonly", width=20)
        self.rollout_service_box.pack(side="left", padx=(0, 7))
        self.rollout_inspect_button = ttk.Button(controls, text="Inspecionar", command=self.start_rollout_inspection)
        self.rollout_inspect_button.pack(side="left", padx=(0, 7))
        self.rollout_follow_button = ttk.Button(controls, text="Acompanhar", command=self.start_rollout_follow)
        self.rollout_follow_button.pack(side="left", padx=(0, 7))
        self.rollout_restart_button = ttk.Button(controls, text="Reiniciar serviço", style="Danger.TButton", command=self.confirm_rollout_restart)
        self.rollout_restart_button.pack(side="left")
        access_row = ttk.Frame(outer)
        access_row.pack(fill="x", pady=(0, 8))
        ttk.Label(access_row, text="A API Kubernetes exige acesso TCP/6443 a partir do IP público atual desta rede.", style="Muted.TLabel").pack(side="left")
        self.rollout_access_button = ttk.Button(access_row, text="Liberar meu IP em 6443", command=self.start_cluster_access_authorization)
        self.rollout_access_button.pack(side="right")
        summary = tk.Frame(outer, bg=PALETTE["blue_pale"], highlightbackground="#D6E3FF", highlightthickness=1, bd=0)
        summary.pack(fill="x", pady=(0, 10))
        self.rollout_summary = tk.Label(summary, text="Valide AWS e Kubernetes antes de consultar ou alterar recursos.", bg=PALETTE["blue_pale"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 9), padx=13, pady=9, anchor="w", justify="left")
        self.rollout_summary.pack(fill="x")

        split = tk.Frame(outer, bg=PALETTE["canvas"])
        split.pack(fill="both", expand=True)
        split.grid_columnconfigure(0, weight=1, uniform="rollout-halves")
        split.grid_columnconfigure(1, weight=1, uniform="rollout-halves")
        split.grid_rowconfigure(0, weight=1)
        info_panel = tk.Frame(split, bg=PALETTE["surface"], highlightbackground=PALETTE["line"], highlightthickness=1, bd=0)
        terminal_panel = tk.Frame(split, bg="#050805", highlightbackground="#26352A", highlightthickness=1, bd=0)
        info_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        terminal_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        info_panel.grid_columnconfigure(0, weight=1)
        info_panel.grid_rowconfigure(1, weight=1)
        info_header = tk.Frame(info_panel, bg=PALETTE["surface"], padx=11, pady=9)
        info_header.grid(row=0, column=0, sticky="ew")
        tk.Label(info_header, text="SERVIÇO SELECIONADO", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 9)).pack(side="left")
        self.rollout_service_status = tk.Label(info_header, text="Aguardando inspeção", bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 8))
        self.rollout_service_status.pack(side="right")
        self.rollout_table = ttk.Treeview(info_panel, columns=("field", "value"), show="headings", height=16)
        self.rollout_table.heading("field", text="Verificação")
        self.rollout_table.heading("value", text="Resultado")
        self.rollout_table.column("field", width=130, minwidth=100, anchor="w", stretch=False)
        self.rollout_table.column("value", width=270, minwidth=160, anchor="w", stretch=True)
        self.rollout_table.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.rollout_table.tag_configure("ok", foreground=PALETTE["green"])
        self.rollout_table.tag_configure("warn", foreground="#A26013")
        self.rollout_table.tag_configure("error", foreground=PALETTE["red"])

        chrome = tk.Frame(terminal_panel, bg="#111A14", padx=12, pady=9)
        chrome.pack(fill="x")
        tk.Label(chrome, text="ACTA  ·  ACOMPANHAMENTO DO ROLLOUT", bg="#111A14", fg="#A7B8A9", font=("Consolas", 9, "bold")).pack(side="left")
        ttk.Button(chrome, text="Copiar tudo", command=self.copy_rollout_terminal).pack(side="right")
        wrap = tk.Frame(terminal_panel, bg="#050805")
        wrap.pack(fill="both", expand=True, padx=8, pady=7)
        self.rollout_terminal = MarkdownTerminal(wrap)
        self.rollout_terminal.pack(fill="both", expand=True)
        self._rollout_append("Selecione uma API e clique em **Inspecionar** para validar o ambiente e conferir imagem, réplicas, pods, eventos, logs, Secrets e health check.\n", "system")
        self._rollout_append("O botão **Reiniciar serviço** atua somente na API selecionada e exige pods saudáveis e Secrets sincronizados.\n", "system")
        ttk.Label(outer, text="Perfil AWS default · kubeconfig ACTA existente · namespace acta-prod · consultas sem leitura de valores de Secrets.", style="Muted.TLabel").pack(anchor="w", pady=(7, 0))

    def _rollout_append(self, text: str, tag: str = "system") -> None:
        terminal = getattr(self, "rollout_terminal", None)
        if terminal is not None and terminal.winfo_exists():
            terminal.append_text(text, tag)

    def copy_rollout_terminal(self) -> None:
        if self.rollout_terminal is not None and self.rollout_terminal.winfo_exists():
            self.rollout_terminal.copy_all()
            self._rollout_append("\nTerminal copiado para a área de transferência.\n")

    def _rollout_selected_service(self) -> str:
        value = self.rollout_service_var.get()
        if value not in ROLLOUT_APIS:
            raise ValueError("Selecione uma API válida da lista.")
        return value

    def _rollout_set_busy(self, busy: bool, message: str) -> None:
        self.rollout_busy = busy
        self.rollout_summary.configure(text=message)
        state = "disabled" if busy else "normal"
        for button in (self.rollout_inspect_button, self.rollout_follow_button, self.rollout_restart_button, self.rollout_access_button):
            button.configure(state=state)
        self.rollout_service_box.configure(state="disabled" if busy else "readonly")

    def _rollout_preflight(self, needs_patch: bool) -> tuple[str, str]:
        self.root.after(0, lambda: self._rollout_append("\nValidando perfil AWS default e sessão temporária…\n"))
        try:
            session = boto3.Session(profile_name="default")
            region = session.region_name
            if not region:
                raise RuntimeError("Região AWS não configurada no perfil default; pare e corrija a sessão.")
            config = Config(connect_timeout=8, read_timeout=12, retries={"total_max_attempts": 1})
            identity = session.client("sts", config=config).get_caller_identity()
            session.client("ec2", region_name=region, config=config).describe_availability_zones(Filters=[{"Name": "state", "Values": ["available"]}])
        except Exception as exc:
            raise RuntimeError(f"AWS bloqueada ou sessão temporária inválida: {self._rollout_safe_text(self._aws_error_code(exc))}. Atualize a sessão AWS Academy/Vocareum; nenhum outro perfil será tentado.") from None
        env = os.environ.copy()
        env["KUBECONFIG"] = str(KUBECONFIG_PATH)
        if not KUBECONFIG_PATH.is_file():
            raise RuntimeError(f"Kubeconfig ACTA ausente: {KUBECONFIG_PATH}")
        try:
            self._rollout_kubectl(["cluster-info", "--request-timeout=8s"], env, timeout=15)
        except Exception as exc:
            detail = self._rollout_safe_text(str(exc))
            network = self._rollout_cluster_connectivity(env)
            raise RuntimeError(f"Falha real ao consultar o Kubernetes: {detail}\nConectividade ao endpoint: {network}\nNenhum rollout foi iniciado. Verifique a rota/rede até o endpoint; não altere regras nem contorne o bloqueio.") from None
        for verb in (("get", "patch") if needs_patch else ("get",)):
            result = self._rollout_kubectl(["auth", "can-i", verb, "deployments", "-n", "acta-prod"], env)
            if result.strip().lower() != "yes":
                raise RuntimeError(f"Kubernetes não autorizou {verb} deployments em acta-prod. Parando sem contornar o bloqueio.")
        return str(identity.get("Account", "desconhecida")), region

    @staticmethod
    def _rollout_safe_text(value: str) -> str:
        value = re.sub(r"(?i)(authorization|password|secret|token|access[_-]?key)\s*[:=]\s*\S+", r"\1=[REDACTED]", value)
        value = re.sub(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "[REDACTED]", value)
        return value[:1800]

    @staticmethod
    def _rollout_kubectl(args: list[str], env: dict[str, str], timeout: int = 30) -> str:
        try:
            completed = subprocess.run(["kubectl", "--kubeconfig", str(KUBECONFIG_PATH), *args], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
        except subprocess.TimeoutExpired as exc:
            output_parts = (exc.stdout, exc.stderr)
            details = "\n".join(part.decode("utf-8", errors="replace") if isinstance(part, bytes) else part for part in output_parts if part)
            details = RolloutMixin._rollout_safe_text(details) if details else "kubectl não forneceu saída antes do timeout"
            raise RuntimeError(f"kubectl excedeu o timeout de {timeout}s. Detalhe: {details}") from None
        if completed.returncode:
            reason = (completed.stderr or completed.stdout or "kubectl falhou").strip()
            raise RuntimeError(RolloutMixin._rollout_safe_text(reason))
        return completed.stdout

    @staticmethod
    def _rollout_cluster_connectivity(env: dict[str, str]) -> str:
        try:
            server = RolloutMixin._rollout_kubectl(["config", "view", "--minify", "-o", "jsonpath={.clusters[0].cluster.server}"], env, timeout=10).strip()
            parsed = urlsplit(server)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            if not host:
                return "não foi possível obter o host do endpoint no kubeconfig"
            try:
                socket.create_connection((host, port), timeout=3).close()
                return f"TCP {host}:{port} acessível; falha ocorre depois da conexão TCP (API, TLS ou autenticação)."
            except socket.timeout:
                return f"timeout TCP ao conectar em {host}:{port}; o endpoint não respondeu na rede."
            except OSError as exc:
                return f"falha TCP ao conectar em {host}:{port}: {type(exc).__name__}: {exc}"
        except Exception as exc:
            return f"diagnóstico TCP não concluído: {RolloutMixin._rollout_safe_text(str(exc))}"

    def start_rollout_inspection(self) -> None:
        self._start_rollout_task("inspect")

    def start_rollout_follow(self) -> None:
        self._start_rollout_task("follow")

    def _start_rollout_task(self, action: str) -> None:
        if self.rollout_busy:
            return
        try:
            service = self._rollout_selected_service()
        except ValueError as exc:
            self.rollout_summary.configure(text=str(exc))
            return
        self._rollout_set_busy(True, f"Validando acesso e preparando inspeção de {service}…")
        self._rollout_append(f"\n=== {service} · {datetime.now().astimezone().strftime('%d/%m/%Y %H:%M:%S')} ===\n", "command")
        threading.Thread(target=self._rollout_task_worker, args=(action, service), daemon=True).start()

    def _rollout_task_worker(self, action: str, service: str) -> None:
        rollout_error = None
        try:
            account, region = self._rollout_preflight(False)
            self.root.after(0, lambda: self._rollout_append(f"Acesso validado · conta {account} · região {region} · kubeconfig ACTA.\n"))
            if action == "follow":
                env = os.environ.copy()
                env["KUBECONFIG"] = str(KUBECONFIG_PATH)
                self.root.after(0, lambda: self._rollout_append(f"$ kubectl rollout status deployment/{service} -n acta-prod --timeout=10m\n", "command"))
                try:
                    result = self._rollout_kubectl(["rollout", "status", f"deployment/{service}", "-n", "acta-prod", "--timeout=10m"], env, timeout=620)
                    self.root.after(0, lambda text=result: self._rollout_append(self._rollout_safe_text(text) + "\n", "system"))
                except Exception as exc:
                    rollout_error = self._rollout_safe_text(str(exc))
                    self.root.after(0, lambda value=rollout_error: self._rollout_append(f"Acompanhamento falhou: {value}\n", "error"))
            report = self._rollout_inspect_service(service)
            self.root.after(0, lambda data=report: self._rollout_render_report(data))
            if rollout_error:
                raise RuntimeError(f"Rollout não concluiu; estado final coletado acima: {rollout_error}")
        except Exception as exc:
            message = self._rollout_safe_text(str(exc))
            self.root.after(0, lambda text=message: self._rollout_append(f"Interrompido: {text}\n", "error"))
            self.root.after(0, lambda text=message: self._rollout_set_busy(False, f"Inspeção/rollout de {service} interrompido: {text}"))
        else:
            self.root.after(0, lambda: self._rollout_set_busy(False, f"Inspeção individual de {service} concluída."))

    def _rollout_inspect_service(self, service: str) -> dict:
        env = os.environ.copy()
        env["KUBECONFIG"] = str(KUBECONFIG_PATH)
        deployment = json.loads(self._rollout_kubectl(["get", "deployment", service, "-n", "acta-prod", "-o", "json"], env))
        spec = deployment.get("spec", {})
        status = deployment.get("status", {})
        template = spec.get("template", {}).get("spec", {})
        containers = template.get("containers", [])
        images = [container.get("image", "desconhecida") for container in containers]
        selector = spec.get("selector", {}).get("matchLabels", {})
        selector_arg = ",".join(f"{key}={value}" for key, value in selector.items())
        pods_doc = json.loads(self._rollout_kubectl(["get", "pods", "-n", "acta-prod", "-l", selector_arg, "-o", "json"], env)) if selector_arg else {"items": []}
        pods = pods_doc.get("items", [])
        pod_names = [pod.get("metadata", {}).get("name", "") for pod in pods]
        pod_report = [f"{pod.get('metadata', {}).get('name', '?')}: {pod.get('status', {}).get('phase', '?')} · Ready {self._pod_ready(pod)} · reinícios {sum(c.get('restartCount', 0) for c in pod.get('status', {}).get('containerStatuses', []))}" for pod in pods]
        secret_names: set[str] = set()
        for container in containers:
            for source in container.get("envFrom", []):
                name = source.get("secretRef", {}).get("name")
                if name:
                    secret_names.add(name)
            for variable in container.get("env", []):
                name = variable.get("valueFrom", {}).get("secretKeyRef", {}).get("name")
                if name:
                    secret_names.add(name)
        for volume in template.get("volumes", []):
            name = volume.get("secret", {}).get("secretName")
            if name:
                secret_names.add(name)
        secret_results: list[str] = []
        for name in sorted(secret_names):
            try:
                self._rollout_kubectl(["get", "secret", name, "-n", "acta-prod", "-o", "name"], env)
                secret_results.append(f"{name}: presente")
            except Exception:
                secret_results.append(f"{name}: ausente/não acessível")
        try:
            infisical_doc = json.loads(self._rollout_kubectl(["get", "infisicalsecrets", "-n", "acta-prod", "-o", "json"], env))
            infisical_by_name = {}
            for resource in infisical_doc.get("items", []):
                name = resource.get("metadata", {}).get("name", "InfisicalSecret")
                conditions = resource.get("status", {}).get("conditions", [])
                infisical_by_name[name] = conditions
            infisical_name = ROLLOUT_INFISICAL_RESOURCES[service]
            infisical_condition = infisical_by_name.get(infisical_name)
            conditions = infisical_condition if isinstance(infisical_condition, list) else []
            normalized = {item.get("type", "").split("/")[-1].lower(): item for item in conditions}
            required_conditions = ("loadedinfisicaltoken", "readytosyncsecrets")
            infisical_ready = all(normalized.get(name, {}).get("status") == "True" for name in required_conditions)
            auto_redeploy = normalized.get("autoredeployready", {})
            auto_message = auto_redeploy.get("message", "")
            deployment_count = re.search(r"\bfound\s+(\d+)\s+deployments?\b", auto_message, re.IGNORECASE)
            if deployment_count and int(deployment_count.group(1)) == 0:
                auto_redeploy_result = "Auto reload: nenhum Deployment configurado; mudança no Secret não reiniciará pods"
            elif deployment_count:
                auto_redeploy_result = f"Auto reload: {deployment_count.group(1)} Deployment(s) elegível(is)"
            elif auto_redeploy.get("status") == "True":
                auto_redeploy_result = "Auto reload: condição do operador OK; nenhum Deployment confirmado"
            else:
                auto_redeploy_result = "Auto reload: não habilitado/confirmado"
            if infisical_ready:
                infisical_results = [f"{infisical_name}: operador autenticado · token carregado · ReadyToSyncSecrets=OK", auto_redeploy_result]
            else:
                if infisical_condition is None:
                    reason = "recurso ausente"
                else:
                    failed = [name for name in required_conditions if normalized.get(name, {}).get("status") != "True"]
                    reason = "condições não confirmadas: " + ", ".join(failed)
                infisical_results = [f"{infisical_name}: NÃO pronto · {reason}", auto_redeploy_result]
        except Exception:
            infisical_ready = False
            infisical_results = [f"{ROLLOUT_INFISICAL_RESOURCES[service]}: estado de sincronização não consultável"]
        config_results: list[str] = []
        has_invalid_config = False
        if service == "acta-mongo-api":
            try:
                secret_doc = json.loads(self._rollout_kubectl(["get", "secret", "acta-mongo-api-env", "-n", "acta-prod", "-o", "json"], env))
                encoded_url = secret_doc.get("data", {}).get("ACTA_PG_API_BASE_URL")
                if not encoded_url:
                    has_invalid_config = True
                    config_results.append("ACTA_PG_API_BASE_URL: chave ausente no Secret")
                else:
                    pg_url = base64.b64decode(encoded_url, validate=True).decode("utf-8").strip()
                    parsed_pg_url = urlsplit(pg_url)
                    try:
                        valid_pg_url = (
                            parsed_pg_url.scheme == "http"
                            and parsed_pg_url.hostname == "acta-pg-api.acta-prod.svc.cluster.local"
                            and parsed_pg_url.port == 8080
                            and parsed_pg_url.path == "/api/v1/"
                            and not parsed_pg_url.username
                            and not parsed_pg_url.password
                            and not parsed_pg_url.query
                            and not parsed_pg_url.fragment
                        )
                    except ValueError:
                        valid_pg_url = False
                    if valid_pg_url:
                        config_results.append("ACTA_PG_API_BASE_URL: endereço interno da PG confirmado (valor oculto)")
                    else:
                        has_invalid_config = True
                        reason = "barra final ausente" if parsed_pg_url.path == "/api/v1" else "host, porta ou caminho inesperado"
                        config_results.append(f"ACTA_PG_API_BASE_URL: {reason}; configuração no Secret ainda não corresponde ao esperado (valor oculto)")
            except Exception:
                has_invalid_config = True
                config_results.append("ACTA_PG_API_BASE_URL: não foi possível validar o Secret sem exibir seu valor")
        events: list[str] = []
        try:
            event_doc = json.loads(self._rollout_kubectl(["get", "events", "-n", "acta-prod", "-o", "json"], env))
            events = [f"{item.get('reason', '')} {item.get('involvedObject', {}).get('name', '')}: {item.get('message', '')}" for item in event_doc.get("items", []) if item.get("type") == "Warning" and (item.get("involvedObject", {}).get("name") in pod_names or item.get("involvedObject", {}).get("name") == service)]
            events = events[-12:]
        except Exception:
            events = ["eventos recentes indisponíveis"]
        error_lines: list[str] = []
        for pod in pods:
            pod_name = pod.get("metadata", {}).get("name", "")
            if not pod_name:
                continue
            try:
                logs = self._rollout_kubectl(["logs", pod_name, "-n", "acta-prod", "--all-containers=true", "--since=30m", "--prefix=true"], env, timeout=45)
                for line in logs.splitlines():
                    if re.search(r"(?i)\b(error|exception|fatal|failed|failure|panic|unauthorized|forbidden)\b", line):
                        line = self._rollout_safe_text(line)
                        line = re.sub(r"(?i)(bearer\s+)\S+", r"\1[REDACTED]", line)
                        error_lines.append(line[:500])
            except Exception:
                continue
        pod_health: list[str] = []
        readiness_probe = (containers[0].get("readinessProbe", {}) if containers else {}).get("httpGet", {})
        if readiness_probe.get("path") and readiness_probe.get("port"):
            probe_port = readiness_probe["port"]
            if isinstance(probe_port, str):
                probe_port = next((port.get("containerPort") for container in containers for port in container.get("ports", []) if port.get("name") == probe_port), None)
            if probe_port:
                for pod in [item for item in pods if self._pod_ready(item) != "sim"][:3]:
                    pod_name = pod.get("metadata", {}).get("name", "")
                    if pod_name:
                        pod_health.append(self._rollout_probe_pod_health(pod_name, int(probe_port), readiness_probe["path"], env))
        health_path, ingress_name = ROLLOUT_APIS[service]
        health_status = "Ingress/host indisponível"
        try:
            ingress_doc = json.loads(self._rollout_kubectl(["get", "ingress", ingress_name, "-n", "acta-prod", "-o", "json"], env))
            host = ingress_doc.get("spec", {}).get("rules", [{}])[0].get("host", "")
            if host:
                url = f"https://{host}{health_path}"
                try:
                    request = Request(url, headers={"User-Agent": "AWS-Default-Profile/1.0"})
                    with urlopen(request, timeout=12) as response:
                        health_status = f"HTTP {response.status} · {url}"
                except HTTPError as exc:
                    health_status = f"HTTP {exc.code} · {url}"
                except (URLError, TimeoutError, OSError) as exc:
                    health_status = f"Falha de conexão ({type(getattr(exc, 'reason', exc)).__name__}) · {url}"
        except Exception:
            pass
        desired = spec.get("replicas", 1)
        ready = status.get("readyReplicas", 0)
        updated = status.get("updatedReplicas", 0)
        available = status.get("availableReplicas", 0)
        rollout = "Concluído" if updated == desired and ready == desired and available == desired else "Em andamento/falhou"
        rollout_complete = bool(desired) and ready >= desired and available >= desired and updated >= desired
        healthy_capacity = bool(desired) and ready >= desired and available >= desired
        return {"service": service, "images": images, "desired": desired, "ready": ready, "updated": updated, "available": available, "rollout": rollout, "rollout_complete": rollout_complete, "healthy_capacity": healthy_capacity, "pods": pod_report, "pod_health": pod_health, "secrets": secret_results, "infisical": infisical_results, "config": config_results, "has_invalid_config": has_invalid_config, "events": events, "errors": error_lines[-20:], "health": health_status, "infisical_ready": infisical_ready, "has_missing_secret": any("ausente" in item or "não consultável" in item for item in secret_results) or not infisical_ready}

    @staticmethod
    def _rollout_probe_pod_health(pod_name: str, container_port: int, path: str, env: dict[str, str]) -> str:
        try:
            with socket.socket() as local_socket:
                local_socket.bind(("127.0.0.1", 0))
                local_port = local_socket.getsockname()[1]
            command = ["kubectl", "--kubeconfig", str(KUBECONFIG_PATH), "-n", "acta-prod", "port-forward", "--address", "127.0.0.1", f"pod/{pod_name}", f"{local_port}:{container_port}"]
            process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
        except Exception as exc:
            return f"{pod_name}: consulta direta indisponível ({type(exc).__name__})"
        try:
            deadline = time.monotonic() + 6
            response_status = None
            response_body = b""
            url = f"http://127.0.0.1:{local_port}{path}"
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    with urlopen(Request(url, headers={"User-Agent": "AWS-Default-Profile/1.0"}), timeout=1) as response:
                        response_status = response.status
                        response_body = response.read(8192)
                        break
                except HTTPError as exc:
                    response_status = exc.code
                    response_body = exc.read(8192)
                    break
                except (URLError, TimeoutError, OSError):
                    time.sleep(0.2)
            if response_status is None:
                return f"{pod_name}: consulta direta indisponível (port-forward sem resposta)"
            details = []
            try:
                document = json.loads(response_body.decode("utf-8", errors="replace"))
                for field in ("status", "banco", "pg", "auth", "fcm"):
                    value = document.get(field)
                    if isinstance(value, str) and value.upper() in ("UP", "DOWN", "UNKNOWN"):
                        details.append(f"{field}={value.upper()}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
            detail_text = " · " + ", ".join(details) if details else ""
            return f"{pod_name}: HTTP {response_status}{detail_text}"
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()

    @staticmethod
    def _pod_ready(pod: dict) -> str:
        conditions = pod.get("status", {}).get("conditions", [])
        return "sim" if any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions) else "não"

    def _rollout_render_report(self, report: dict) -> None:
        self.rollout_table.delete(*self.rollout_table.get_children())
        entries = [
            ("Imagem", ", ".join(report["images"])),
            ("Réplicas", f"{report['ready']}/{report['desired']} prontas · {report['updated']} atualizadas · {report['available']} disponíveis"),
            ("Rollout", report["rollout"]),
            ("Health check", report["health"]),
            ("Health do pod não pronto", "\n".join(report["pod_health"]) or "todos os pods prontos ou sem probe HTTP"),
            ("Configuração validada", "\n".join(report["config"]) or "nenhuma validação específica"),
            ("Pods", "\n".join(report["pods"]) or "nenhum pod encontrado"),
            ("Secrets K8s", "\n".join(report["secrets"]) or "nenhuma referência a Secret no pod template"),
            ("Infisical sync", "\n".join(report["infisical"])),
            ("Eventos", "\n".join(self._rollout_safe_text(e) for e in report["events"]) or "nenhum Warning recente para este serviço"),
            ("Erros recentes", "\n".join(report["errors"]) or "nenhum erro encontrado nos logs recentes"),
        ]
        for key, value in entries:
            tag = "error" if key == "Rollout" and report["rollout"] != "Concluído" else ("warn" if key in ("Health check", "Health do pod não pronto", "Configuração validada", "Secrets K8s", "Infisical sync") and ("ausente" in value.lower() or "falha" in value.lower() or "500" in value or "não confirmado" in value.lower() or "não consultável" in value.lower() or "=down" in value.lower() or "barra final ausente" in value.lower() or "inesperado" in value.lower()) else "ok")
            self.rollout_table.insert("", "end", values=(key, value), tags=(tag,))
        self.rollout_service_status.configure(text=report["rollout"], fg=PALETTE["green"] if report["rollout"] == "Concluído" else "#A26013")
        self._rollout_append(f"Imagem: {', '.join(report['images'])}\nRéplicas: {report['ready']}/{report['desired']} prontas; {report['updated']} atualizadas; {report['available']} disponíveis.\nRollout: {report['rollout']}\nHealth: {report['health']}\n", "system")
        for section in ("pods", "pod_health", "config", "secrets", "infisical", "events", "errors"):
            title = {"pods": "Pods", "pod_health": "Health direto dos pods não prontos", "config": "Configuração (valor oculto)", "secrets": "Secrets Kubernetes (sem valores)", "infisical": "Sincronização Infisical", "events": "Eventos relevantes", "errors": "Erros recentes filtrados"}[section]
            self._rollout_append(f"\n{title}:\n", "command")
            values = report[section] or ["nenhum item"]
            for item in values:
                self._rollout_append(self._rollout_safe_text(item) + "\n", "error" if section == "errors" else "system")

    def start_cluster_access_authorization(self) -> None:
        if self.rollout_busy:
            return
        self._rollout_set_busy(True, "Validando perfil default e descobrindo o IP atual e o security group ACTA…")
        self._rollout_append("\n=== Solicitação de acesso à API Kubernetes TCP/6443 ===\n", "command")
        threading.Thread(target=self._prepare_cluster_access_authorization, daemon=True).start()

    def _prepare_cluster_access_authorization(self) -> None:
        try:
            session = boto3.Session(profile_name="default")
            region = session.region_name
            if not region:
                raise RuntimeError("A região do perfil AWS default não está configurada.")
            config = Config(connect_timeout=8, read_timeout=15, retries={"total_max_attempts": 1})
            identity = session.client("sts", config=config).get_caller_identity()
            ec2 = session.client("ec2", region_name=region, config=config)
            response = ec2.describe_instances(Filters=[{"Name": "tag:Name", "Values": ["acta-prod-k3s"]}, {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}])
            instances = [instance for reservation in response.get("Reservations", []) for instance in reservation.get("Instances", [])]
            if len(instances) != 1:
                raise RuntimeError(f"Esperava uma instância ACTA com tag Name=acta-prod-k3s; encontrei {len(instances)}. Nenhuma regra foi alterada.")
            group_ids = [group.get("GroupId") for group in instances[0].get("SecurityGroups", []) if group.get("GroupId")]
            groups = ec2.describe_security_groups(GroupIds=group_ids).get("SecurityGroups", []) if group_ids else []
            matches = [group for group in groups if group.get("GroupName") == "acta-prod-k3s"]
            if len(matches) != 1:
                raise RuntimeError(f"Não foi possível identificar exatamente um security group acta-prod-k3s associado à instância. Nenhuma regra foi alterada.")
            ip_response = urlopen(Request("https://checkip.amazonaws.com", headers={"User-Agent": "AWS-Default-Profile/1.0"}), timeout=8)
            with ip_response:
                source_ip = ip_response.read(64).decode("ascii", errors="replace").strip()
            if ipaddress.ip_address(source_ip).version != 4:
                raise RuntimeError("O serviço de consulta retornou um endereço que não é IPv4; nenhuma regra foi alterada.")
            target = {"account": identity.get("Account", "desconhecida"), "region": region, "group_id": matches[0]["GroupId"], "group_name": matches[0]["GroupName"], "ip": source_ip, "already_allowed": self._source_ip_allowed(matches[0], source_ip)}
            self.root.after(0, lambda data=target: self._confirm_cluster_access_authorization(data))
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            message = self._rollout_safe_text(str(exc)) if isinstance(exc, RuntimeError) else (f"AWS/credencial: {code}" if code else f"Falha ao preparar a regra: {type(exc).__name__}")
            self.root.after(0, lambda text=message: self._rollout_append(f"Nenhuma regra foi alterada. {text}\n", "error"))
            self.root.after(0, lambda text=message: self._rollout_set_busy(False, text))

    @staticmethod
    def _source_ip_allowed(security_group: dict, source_ip: str) -> bool:
        address = ipaddress.ip_address(source_ip)
        for permission in security_group.get("IpPermissions", []):
            if permission.get("IpProtocol") == "tcp" and permission.get("FromPort") == 6443 and permission.get("ToPort") == 6443:
                for item in permission.get("IpRanges", []):
                    try:
                        if address in ipaddress.ip_network(item.get("CidrIp", ""), strict=False):
                            return True
                    except ValueError:
                        continue
        return False

    def _confirm_cluster_access_authorization(self, target: dict) -> None:
        if target["already_allowed"]:
            message = f"O IP {target['ip']}/32 já tem acesso TCP/6443 em {target['group_name']} ({target['group_id']}); nenhuma regra foi alterada."
            self._rollout_append(message + "\n")
            self._rollout_set_busy(False, message)
            return
        accepted = messagebox.askyesno("Autorizar acesso ao Kubernetes", f"Adicionar apenas este IP público ao security group ACTA?\n\nIP: {target['ip']}/32\nPorta: TCP/6443\nSecurity group: {target['group_name']} ({target['group_id']})\nConta/região: {target['account']} · {target['region']}\n\nA regra antiga será preservada. Esta ação altera o security group da instância ACTA.", parent=self.root)
        if not accepted:
            self._rollout_append("Alteração cancelada; nenhuma regra foi modificada.\n")
            self._rollout_set_busy(False, "Alteração de rede cancelada; nenhuma regra foi modificada.")
            return
        self._rollout_append(f"Autorização confirmada para {target['ip']}/32 · TCP/6443. Aplicando uma regra restrita…\n", "command")
        threading.Thread(target=self._apply_cluster_access_authorization, args=(target,), daemon=True).start()

    def _apply_cluster_access_authorization(self, target: dict) -> None:
        try:
            session = boto3.Session(profile_name="default")
            identity = session.client("sts", config=Config(connect_timeout=8, read_timeout=12, retries={"total_max_attempts": 1})).get_caller_identity()
            if identity.get("Account") != target["account"]:
                raise RuntimeError("A identidade AWS mudou desde a confirmação; regra não aplicada. Valide a sessão e tente novamente.")
            ec2 = session.client("ec2", region_name=target["region"], config=Config(connect_timeout=8, read_timeout=15, retries={"total_max_attempts": 1}))
            ec2.authorize_security_group_ingress(GroupId=target["group_id"], IpPermissions=[{"IpProtocol": "tcp", "FromPort": 6443, "ToPort": 6443, "IpRanges": [{"CidrIp": f"{target['ip']}/32", "Description": "ACTA Kubernetes API from current client"}]}])
            current = ec2.describe_security_groups(GroupIds=[target["group_id"]]).get("SecurityGroups", [])
            verified = bool(current) and self._source_ip_allowed(current[0], target["ip"])
            if not verified:
                raise RuntimeError("A AWS aceitou a solicitação, mas a regra ainda não aparece na leitura de verificação. Confira o security group antes de tentar novamente.")
            message = f"Regra confirmada: {target['ip']}/32 → TCP/6443 em {target['group_name']}. A regra anterior foi preservada. Aguarde a propagação e use Inspecionar para testar o cluster."
            self.root.after(0, lambda: self._rollout_append(message + "\n", "system"))
            self.root.after(0, lambda: self._rollout_set_busy(False, message))
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            message = self._rollout_safe_text(str(exc)) if isinstance(exc, RuntimeError) else (f"AWS rejeitou a alteração ({code})." if code else f"Falha ao aplicar/verificar a regra: {type(exc).__name__}. Confira o estado do security group antes de repetir.")
            self.root.after(0, lambda text=message: self._rollout_append(f"Não foi possível confirmar a alteração. {text}\n", "error"))
            self.root.after(0, lambda text=message: self._rollout_set_busy(False, text))

    def confirm_rollout_restart(self) -> None:
        if self.rollout_busy:
            return
        try:
            service = self._rollout_selected_service()
        except ValueError as exc:
            self.rollout_summary.configure(text=str(exc))
            return
        if not messagebox.askyesno("Reiniciar uma API", f"Confirma reiniciar somente {service} em acta-prod?\n\nO app fará novas verificações antes da ação e bloqueará se não puder preservar as réplicas saudáveis ou confirmar os Secrets.", parent=self.root):
            return
        self._rollout_set_busy(True, f"Validando pré-condições antes do reinício individual de {service}…")
        self._rollout_append(f"\n=== Reinício solicitado: {service} ===\n", "command")
        threading.Thread(target=self._rollout_restart_worker, args=(service,), daemon=True).start()

    def _rollout_restart_worker(self, service: str) -> None:
        restart_started = False
        try:
            account, region = self._rollout_preflight(True)
            self.root.after(0, lambda: self._rollout_append(f"Acesso validado · conta {account} · região {region}. Inspecionando estado antes do reinício…\n"))
            before = self._rollout_inspect_service(service)
            self.root.after(0, lambda data=before: self._rollout_render_report(data))
            if not before["healthy_capacity"]:
                raise RuntimeError(f"Reinício bloqueado: capacidade saudável insuficiente antes do rollout ({before['ready']}/{before['desired']} prontas; {before['available']}/{before['desired']} disponíveis). É necessário manter as réplicas desejadas prontas e disponíveis; não é necessário que já estejam atualizadas.")
            if before["has_missing_secret"]:
                raise RuntimeError("Reinício bloqueado: há referência a Secret ausente ou o operador Infisical não confirmou suas condições de prontidão. Não reinicie até confirmar o estado.")
            if before["has_invalid_config"]:
                raise RuntimeError("Reinício bloqueado: a configuração da integração PG no Secret da Mongo ainda não corresponde ao endpoint interno esperado. Aguarde a sincronização do Infisical; nenhum Secret foi exibido.")
            env = os.environ.copy()
            env["KUBECONFIG"] = str(KUBECONFIG_PATH)
            self.root.after(0, lambda: self._rollout_append(f"\n$ kubectl rollout restart deployment/{service} -n acta-prod\n", "command"))
            output = self._rollout_kubectl(["rollout", "restart", f"deployment/{service}", "-n", "acta-prod"], env)
            restart_started = True
            self.root.after(0, lambda text=output: self._rollout_append(self._rollout_safe_text(text) + "\n", "system"))
            self.root.after(0, lambda: self._rollout_append(f"$ kubectl rollout status deployment/{service} -n acta-prod --timeout=10m\n", "command"))
            try:
                output = self._rollout_kubectl(["rollout", "status", f"deployment/{service}", "-n", "acta-prod", "--timeout=10m"], env, timeout=620)
                self.root.after(0, lambda text=output: self._rollout_append(self._rollout_safe_text(text) + "\n", "system"))
            except Exception as exc:
                rollout_error = self._rollout_safe_text(str(exc))
                self.root.after(0, lambda value=rollout_error: self._rollout_append(f"Acompanhamento falhou: {value}\n", "error"))
            report = self._rollout_inspect_service(service)
            self.root.after(0, lambda data=report: self._rollout_render_report(data))
            if "rollout_error" in locals():
                raise RuntimeError(f"Reinício executado, mas rollout não concluiu; estado final coletado acima: {rollout_error}")
            if not report["rollout_complete"]:
                raise RuntimeError("kubectl encerrou o acompanhamento, mas a inspeção final não confirma todas as réplicas prontas.")
        except Exception as exc:
            message = self._rollout_safe_text(str(exc))
            if restart_started and "report" not in locals():
                try:
                    report = self._rollout_inspect_service(service)
                    self.root.after(0, lambda data=report: self._rollout_render_report(data))
                except Exception as inspect_exc:
                    self.root.after(0, lambda value=self._rollout_safe_text(str(inspect_exc)): self._rollout_append(f"Inspeção final também falhou: {value}\n", "error"))
            self.root.after(0, lambda text=message: self._rollout_append(f"Resultado: falhou/interrompido · {text}\n", "error"))
            self.root.after(0, lambda text=message: self._rollout_set_busy(False, f"Rollout de {service} não confirmado: {text}"))
        else:
            self.root.after(0, lambda: self._rollout_set_busy(False, f"Rollout individual de {service} concluído e réplicas verificadas."))
