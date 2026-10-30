from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import tkinter as tk
from tkinter import ttk

import boto3
from botocore.config import Config

from ..constants import PALETTE


class ClusterMixin:
    def build_clusters_page(self, page: ttk.Frame) -> None:
        outer = ttk.Frame(page, padding=(30, 24, 30, 22))
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 20))
        titles = ttk.Frame(header)
        titles.pack(side="left", fill="x", expand=True)
        ttk.Label(titles, text="APIs do cluster ACTA", style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text="Localiza o Elastic IP na AWS e verifica as URLs públicas dos serviços.", style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        self.scan_button = ttk.Button(header, text="Buscar APIs", style="Primary.TButton", command=self.start_cluster_scan)
        self.scan_button.pack(side="right", anchor="n")
        summary = tk.Frame(outer, bg=PALETTE["blue_pale"], highlightbackground="#D6E3FF", highlightthickness=1, bd=0)
        summary.pack(fill="x", pady=(0, 14))
        self.cluster_summary = tk.Label(summary, text="Nenhuma busca executada.", bg=PALETTE["blue_pale"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 10), padx=16, pady=12, anchor="w")
        self.cluster_summary.pack(fill="x")
        table_wrap = tk.Frame(outer, bg=PALETTE["surface"], highlightbackground=PALETTE["line"], highlightthickness=1, bd=0)
        table_wrap.pack(fill="both", expand=True)
        table_wrap.grid_rowconfigure(0, weight=1)
        table_wrap.grid_columnconfigure(0, weight=1)
        self.cluster_canvas = tk.Canvas(table_wrap, bg=PALETTE["surface"], highlightthickness=0)
        ybar = ttk.Scrollbar(table_wrap, orient="vertical", command=self.cluster_canvas.yview)
        xbar = ttk.Scrollbar(outer, orient="horizontal", command=self.cluster_canvas.xview)
        self.cluster_canvas.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.cluster_canvas.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        ybar.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=10)
        xbar.pack(fill="x")
        self.cluster_rows_frame = tk.Frame(self.cluster_canvas, bg=PALETTE["surface"])
        self.cluster_canvas.create_window((0, 0), window=self.cluster_rows_frame, anchor="nw")
        self.cluster_rows_frame.bind("<Configure>", lambda _event: self.cluster_canvas.configure(scrollregion=self.cluster_canvas.bbox("all")))
        for column, (label, width) in enumerate((("Serviço", 19), ("Região", 14), ("Verificação", 16), ("URL pública", 68), ("", 10))):
            tk.Label(self.cluster_rows_frame, text=label, bg=PALETTE["editor"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 9), anchor="w", padx=8, pady=9, width=width).grid(row=0, column=column, sticky="ew")
        self.cluster_rows_frame.grid_columnconfigure(3, weight=1)
        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(13, 0))
        ttk.Label(footer, text="A busca usa o perfil AWS default e a tag Name=acta-prod-k3s.", style="Muted.TLabel").pack(side="left")
        self.copy_button = ttk.Button(footer, text="Copiar URLs", command=self.copy_cluster_urls)
        self.copy_button.pack(side="right")
        self.cluster_status = ttk.Label(outer, text="", style="Muted.TLabel")
        self.cluster_status.pack(anchor="w", pady=(10, 0))
    def start_cluster_scan(self) -> None:
        if self.cluster_busy:
            return
        self.cluster_busy = True
        self.scan_button.configure(state="disabled")
        self.cluster_summary.configure(text="Consultando o Elastic IP ACTA na AWS…")
        self.cluster_status.configure(text="Depois da descoberta, as URLs públicas serão verificadas por HTTPS.")
        self.cluster_urls = []
        for child in self.cluster_rows_frame.winfo_children():
            if int(child.grid_info().get("row", 0)) > 0:
                child.destroy()
        def work() -> None:
            try:
                session = boto3.Session(profile_name="default")
                region = session.region_name
                if not region:
                    raise ValueError("A região do perfil AWS default não está configurada.")
                config = Config(connect_timeout=8, read_timeout=17, retries={"total_max_attempts": 1})
                identity = session.client("sts", config=config).get_caller_identity()
                ec2 = session.client("ec2", region_name=region, config=config)
                addresses = ec2.describe_addresses(Filters=[{"Name": "tag:Name", "Values": ["acta-prod-k3s"]}])["Addresses"]
                if len(addresses) != 1:
                    raise ValueError(f"Esperava um Elastic IP com a tag Name=acta-prod-k3s na região {region}; encontrei {len(addresses)}.")
                address = addresses[0]
                public_ip = address.get("PublicIp", "")
                if not public_ip or not address.get("AssociationId") or not address.get("InstanceId"):
                    raise ValueError("O Elastic IP ACTA não tem IPv4 público ou não está associado a uma instância.")
                ip_host = public_ip.replace(".", "-")
                host = f"{ip_host}.sslip.io"
                checks = [
                    ("Auth API", f"https://acta-auth-api.{host}", f"https://acta-auth-api.{host}/api/v1/health"),
                    ("PostgreSQL API", f"https://acta-pg-api.{host}", f"https://acta-pg-api.{host}/api/v1/health"),
                    ("MongoDB API", f"https://acta-mongo-api.{host}", f"https://acta-mongo-api.{host}/api/v1/health"),
                    ("Import API", f"https://acta-import-api.{host}", f"https://acta-import-api.{host}/docs"),
                    ("FCM API", f"https://acta-fcm-api.{host}", f"https://acta-fcm-api.{host}/health"),
                    ("AI", f"https://acta-ai.{host}", f"https://acta-ai.{host}/health"),
                    ("MCP", f"https://acta-mcp.{host}/mcp", f"https://acta-mcp.{host}/health"),
                ]
                def check_endpoint(check: tuple[str, str, str]) -> tuple[str, str, str, str]:
                    name, endpoint, health_url = check
                    try:
                        request = Request(health_url, headers={"User-Agent": "AWS-Default-Profile/1.0"})
                        with urlopen(request, timeout=15) as response:
                            status = f"HTTP {response.status}"
                    except HTTPError as exc:
                        status = f"HTTP {exc.code}"
                    except (URLError, TimeoutError, OSError) as exc:
                        reason = getattr(exc, "reason", exc)
                        status = f"Falha: {type(reason).__name__}"
                    return name, region, status, endpoint
                with ThreadPoolExecutor(max_workers=len(checks)) as pool:
                    rows = list(pool.map(check_endpoint, checks))
                failures = [row[0] for row in rows if row[2] != "HTTP 200"]
                summary = f"Conta {identity['Account']} · {region} · IP {public_ip} · {sum(row[2] == 'HTTP 200' for row in rows)}/{len(rows)} endpoints HTTP 200."
                note = "Todas as verificações responderam HTTP 200." if not failures else "Verifique: " + ", ".join(failures) + "."
                self.root.after(0, lambda: self.finish_cluster_scan(rows, summary, note, None))
            except Exception as exc:
                message = str(exc) if isinstance(exc, ValueError) else f"Não foi possível concluir a busca ({self.aws_error_code(exc)}). Confira o perfil default e as permissões EC2."
                self.root.after(0, lambda: self.finish_cluster_scan([], "Busca não concluída.", message, None))
        threading.Thread(target=work, daemon=True).start()
    @staticmethod
    def aws_error_code(exc: Exception) -> str:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", type(exc).__name__)
        return code if re.fullmatch(r"[A-Za-z0-9_.-]+", str(code)) else type(exc).__name__
    def finish_cluster_scan(self, clusters: list[tuple[str, str, str, str]], summary: str, note: str, error: str | None) -> None:
        self.cluster_busy = False
        self.scan_button.configure(state="normal")
        if error:
            self.cluster_summary.configure(text="Busca não concluída.")
            self.cluster_status.configure(text=error)
        else:
            self.cluster_urls = [(row[0], row[3]) for row in clusters]
            for row_number, (name, region, status, endpoint) in enumerate(clusters, start=1):
                background = PALETTE["surface"] if row_number % 2 else PALETTE["editor"]
                for column, (value, width) in enumerate(zip((name, region, status, endpoint), (19, 14, 16, 68))):
                    cell = tk.Label(self.cluster_rows_frame, text=value, bg=background, fg=PALETTE["ink"], font=("Segoe UI", 9), anchor="w", padx=8, pady=8, width=width, cursor="hand2")
                    cell.grid(row=row_number, column=column, sticky="ew")
                    cell.bind("<Double-Button-1>", lambda _event, service=name: self.start_logs(service))
                ttk.Button(self.cluster_rows_frame, text="Copiar", command=lambda url=endpoint, service=name: self.copy_cluster_url(url, service)).grid(row=row_number, column=4, padx=8, pady=4, sticky="e")
            self.cluster_summary.configure(text=summary)
            self.cluster_status.configure(text=note)
    def copy_cluster_url(self, url: str, service: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        self.cluster_status.configure(text=f"URL de {service} copiada para a área de transferência.")
    def copy_cluster_urls(self) -> None:
        urls = [url for _service, url in self.cluster_urls if url]
        if not urls:
            self.cluster_status.configure(text="Nenhuma URL para copiar. Execute uma busca primeiro.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(urls))
        self.cluster_status.configure(text=f"Todas as {len(urls)} URLs foram copiadas para a área de transferência.")
