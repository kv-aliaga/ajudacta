from __future__ import annotations

import base64
import csv
import getpass
import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from ..constants import PALETTE, TOKEN_GENERATOR_SCRIPT, TOKEN_HISTORY_CSV, TOKEN_ID_DIR, TOKEN_USERS_CSV


class TokenMixin:
    def build_token_page(self, page: ttk.Frame) -> None:
        outer = ttk.Frame(page, padding=(24, 20, 24, 18))
        outer.pack(fill="both", expand=True)
        header = tk.Frame(outer, bg=PALETTE["canvas"])
        header.pack(fill="x", pady=(0, 15))
        title_group = tk.Frame(header, bg=PALETTE["canvas"])
        title_group.pack(side="left", fill="x", expand=True)
        tk.Label(title_group, text="Geração de token ID", bg=PALETTE["canvas"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 22), anchor="w").pack(anchor="w")
        tk.Label(title_group, text="Emita um Firebase ID token para uma conta autorizada e consulte suas claims.", bg=PALETTE["canvas"], fg=PALETTE["muted"], font=("Segoe UI", 9), anchor="w").pack(anchor="w", pady=(3, 0))
        self.token_user_count = tk.Label(header, text="0 contas autorizadas", bg=PALETTE["blue_pale"], fg=PALETTE["blue"], font=("Segoe UI Semibold", 9), padx=12, pady=8)
        self.token_user_count.pack(side="right", anchor="n", padx=(10, 0), pady=(4, 0))
        self.token_refresh_button = ttk.Button(header, text="Atualizar lista", command=self._load_token_users)
        self.token_refresh_button.pack(side="right", anchor="n", padx=(0, 8), pady=(4, 0))
        split = tk.Frame(outer, bg=PALETTE["canvas"])
        split.pack(fill="both", expand=True)
        split.grid_columnconfigure(0, weight=6, uniform="token_panels")
        split.grid_columnconfigure(1, weight=5, uniform="token_panels")
        split.grid_rowconfigure(0, weight=1)
        account_panel = tk.Frame(split, bg=PALETTE["surface"], highlightbackground=PALETTE["line"], highlightthickness=1, bd=0)
        account_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        account_panel.grid_rowconfigure(1, weight=1)
        account_panel.grid_columnconfigure(0, weight=1)
        account_header = tk.Frame(account_panel, bg=PALETTE["surface"], padx=15, pady=13)
        account_header.grid(row=0, column=0, sticky="ew")
        tk.Label(account_header, text="Contas disponíveis", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 11), anchor="w").pack(anchor="w")
        tk.Label(account_header, text="Clique em Gerar token na conta desejada.", bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 8), anchor="w").pack(anchor="w", pady=(3, 0))
        manual_uid_row = tk.Frame(account_header, bg=PALETTE["surface"])
        manual_uid_row.pack(fill="x", pady=(10, 0))
        self.manual_firebase_uid_var = tk.StringVar()
        self.manual_firebase_uid_entry = ttk.Entry(manual_uid_row, textvariable=self.manual_firebase_uid_var)
        self.manual_firebase_uid_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.manual_firebase_uid_entry.bind("<Return>", lambda _event: self.generate_token_for_manual_uid())
        self.manual_firebase_uid_button = ttk.Button(manual_uid_row, text="Gerar por UID", command=self.generate_token_for_manual_uid)
        self.manual_firebase_uid_button.pack(side="right")
        account_list = tk.Frame(account_panel, bg=PALETTE["surface"])
        account_list.grid(row=1, column=0, sticky="nsew", padx=(11, 4), pady=(0, 10))
        account_list.grid_rowconfigure(0, weight=1)
        account_list.grid_columnconfigure(0, weight=1)
        self.token_accounts_canvas = tk.Canvas(account_list, bg=PALETTE["surface"], highlightthickness=0, bd=0)
        accounts_scroll = ttk.Scrollbar(account_list, orient="vertical", command=self.token_accounts_canvas.yview)
        self.token_accounts_canvas.configure(yscrollcommand=accounts_scroll.set)
        self.token_accounts_canvas.grid(row=0, column=0, sticky="nsew")
        accounts_scroll.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        self.token_accounts_frame = tk.Frame(self.token_accounts_canvas, bg=PALETTE["surface"])
        self.token_accounts_window = self.token_accounts_canvas.create_window((0, 0), window=self.token_accounts_frame, anchor="nw")
        self.token_accounts_frame.bind("<Configure>", lambda _event: self.token_accounts_canvas.configure(scrollregion=self.token_accounts_canvas.bbox("all")))
        self.token_accounts_canvas.bind("<Configure>", lambda event: self.token_accounts_canvas.itemconfigure(self.token_accounts_window, width=event.width))
        self.token_account_buttons: list[ttk.Button] = []
        self.token_list_status = tk.Label(account_panel, text="", bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 8), anchor="w", padx=15, pady=6)
        self.token_list_status.grid(row=2, column=0, sticky="ew")
        result_panel = tk.Frame(split, bg=PALETTE["surface"], highlightbackground=PALETTE["line"], highlightthickness=1, bd=0)
        result_panel.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        result_panel.grid_rowconfigure(4, weight=1)
        result_panel.grid_columnconfigure(0, weight=1)
        result_header = tk.Frame(result_panel, bg=PALETTE["surface"], padx=15, pady=12)
        result_header.grid(row=0, column=0, sticky="ew")
        result_title_group = tk.Frame(result_header, bg=PALETTE["surface"])
        result_title_group.pack(side="left", fill="x", expand=True)
        tk.Label(result_title_group, text="Token emitido", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 11), anchor="w").pack(anchor="w")
        self.token_result_status = tk.Label(result_title_group, text="Aguardando uma conta", bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 8), anchor="w")
        self.token_result_status.pack(anchor="w", pady=(3, 0))
        self.token_expiration_badge = tk.Label(result_header, text="Sem token", bg="#EEF2F7", fg=PALETTE["muted"], font=("Segoe UI Semibold", 8), padx=9, pady=6)
        self.token_expiration_badge.pack(side="right", anchor="n", padx=(8, 0))
        token_chrome = tk.Frame(result_panel, bg="#111A14", padx=12, pady=8)
        token_chrome.grid(row=1, column=0, sticky="ew", padx=12)
        tk.Label(token_chrome, text="FIREBASE ID TOKEN", bg="#111A14", fg="#A7B8A9", font=("Consolas", 8, "bold")).pack(side="left")
        self.copy_token_button = ttk.Button(token_chrome, text="Copiar", command=self.copy_generated_token, state="disabled")
        self.copy_token_button.pack(side="right")
        token_wrap = tk.Frame(result_panel, bg="#050805", highlightbackground="#26352A", highlightthickness=1, bd=0)
        token_wrap.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))
        token_wrap.grid_columnconfigure(0, weight=1)
        self.token_value_text = tk.Text(token_wrap, height=5, wrap="char", state="disabled", relief="flat", bd=0, bg="#050805", fg="#74E68B", selectbackground="#1D4725", selectforeground="#D4FFD9", font=("Consolas", 8), padx=10, pady=9)
        self.token_value_text.grid(row=0, column=0, sticky="ew")
        self.token_value_text.configure(state="normal")
        self.token_value_text.insert("1.0", "O token aparecerá aqui após a emissão.\nTrate-o como uma credencial temporária.")
        self.token_value_text.configure(state="disabled")
        metadata_header = tk.Frame(result_panel, bg=PALETTE["surface"], padx=14, pady=5)
        metadata_header.grid(row=3, column=0, sticky="ew")
        tk.Label(metadata_header, text="Metadados disponíveis", bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 9), anchor="w").pack(side="left")
        self.token_metadata_count = tk.Label(metadata_header, text="0 campos", bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 8))
        self.token_metadata_count.pack(side="right")
        metadata_wrap = tk.Frame(result_panel, bg=PALETTE["surface"])
        metadata_wrap.grid(row=4, column=0, sticky="nsew", padx=(10, 5), pady=(0, 10))
        metadata_wrap.grid_rowconfigure(0, weight=1)
        metadata_wrap.grid_columnconfigure(0, weight=1)
        self.token_metadata_table = ttk.Treeview(metadata_wrap, columns=("field", "value"), show="headings", height=10)
        self.token_metadata_table.heading("field", text="Campo")
        self.token_metadata_table.heading("value", text="Valor")
        self.token_metadata_table.column("field", width=155, minwidth=100, anchor="w", stretch=False)
        self.token_metadata_table.column("value", width=245, minwidth=120, anchor="w", stretch=True)
        metadata_y = ttk.Scrollbar(metadata_wrap, orient="vertical", command=self.token_metadata_table.yview)
        metadata_x = ttk.Scrollbar(metadata_wrap, orient="horizontal", command=self.token_metadata_table.xview)
        self.token_metadata_table.configure(yscrollcommand=metadata_y.set, xscrollcommand=metadata_x.set)
        self.token_metadata_table.grid(row=0, column=0, sticky="nsew")
        metadata_y.grid(row=0, column=1, sticky="ns")
        metadata_x.grid(row=1, column=0, sticky="ew")
        self._load_token_users()
    def _load_token_users(self) -> None:
        try:
            with TOKEN_USERS_CSV.open("r", encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source)
                if not reader.fieldnames or "firebase_uid" not in reader.fieldnames:
                    raise ValueError("A coluna firebase_uid não foi encontrada no CSV.")
                users = [
                    {str(key): (value or "").strip() for key, value in row.items() if key}
                    for row in reader
                    if (row.get("firebase_uid") or "").strip()
                ]
            self.token_users = users
            self.token_user_count.configure(text=f"{len(users)} contas autorizadas")
            for child in self.token_accounts_frame.winfo_children():
                child.destroy()
            self.token_account_buttons = []
            for user in users:
                self._create_token_account_row(user)
            message = f"Fonte: {TOKEN_USERS_CSV.name} · você também pode informar um UID fora desta lista."
            color = PALETTE["muted"]
            if not users:
                message = "Nenhuma conta com Firebase UID foi encontrada na lista autorizada."
                color = PALETTE["red"]
            self.token_list_status.configure(text=message, fg=color)
            self.token_accounts_canvas.configure(scrollregion=self.token_accounts_canvas.bbox("all"))
        except (OSError, csv.Error, ValueError) as exc:
            self.token_users = []
            for child in self.token_accounts_frame.winfo_children():
                child.destroy()
            self.token_account_buttons = []
            self.token_accounts_canvas.configure(scrollregion=(0, 0, 0, 0))
            self.token_user_count.configure(text="Lista indisponível")
            self.token_list_status.configure(text=f"Não foi possível carregar a lista autorizada: {exc}", fg=PALETTE["red"])
    def _create_token_account_row(self, user: dict[str, str]) -> None:
        row = tk.Frame(self.token_accounts_frame, bg=PALETTE["surface"], highlightbackground=PALETTE["line"], highlightthickness=1, padx=11, pady=8)
        row.pack(fill="x", pady=(0, 7), padx=(1, 2))
        details = tk.Frame(row, bg=PALETTE["surface"])
        details.pack(side="left", fill="x", expand=True, padx=(0, 8))
        name = user.get("nome") or f"Conta {user.get('id') or 'sem ID'}"
        tk.Label(details, text=name, bg=PALETTE["surface"], fg=PALETTE["ink"], font=("Segoe UI Semibold", 9), anchor="w").pack(anchor="w")
        identity = user.get("email_login") or user.get("firebase_uid", "")
        tk.Label(details, text=identity, bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 8), anchor="w").pack(anchor="w", pady=(2, 0))
        tk.Label(details, text=f"UID  {user.get('firebase_uid', '')}", bg=PALETTE["surface"], fg="#526276", font=("Cascadia Mono", 8), anchor="w").pack(anchor="w", pady=(3, 0))
        role = " · ".join(value for value in (user.get("tipo_usuario", ""), user.get("status", "")) if value)
        tk.Label(details, text=role or "Perfil sem classificação", bg=PALETTE["surface"], fg=PALETTE["blue"], font=("Segoe UI", 8), anchor="w").pack(anchor="w", pady=(2, 0))
        button = ttk.Button(row, text="Gerar token", style="Primary.TButton", command=lambda account=user: self.generate_firebase_token(account), state="disabled" if self.token_generation_busy else "normal")
        button.pack(side="right")
        self.token_account_buttons.append(button)
    def generate_firebase_token(self, user: dict[str, str]) -> None:
        if self.token_generation_busy:
            return
        uid = (user.get("firebase_uid") or "").strip()
        if not uid:
            self._set_token_result("Informe um Firebase UID válido.", "error")
            return
        try:
            with TOKEN_USERS_CSV.open("r", encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source)
                current_users = list(reader)
            authorized_user = next((
                {str(key): (value or "").strip() for key, value in row.items() if key}
                for row in current_users
                if (row.get("firebase_uid") or "").strip() == uid
            ), None)
        except (OSError, csv.Error):
            current_users = []
            authorized_user = None
        if authorized_user is not None:
            user = authorized_user
        else:
            user = {"firebase_uid": uid, "nome": "UID não mapeado no CSV"}
        if not TOKEN_GENERATOR_SCRIPT.is_file() or not TOKEN_ID_DIR.is_dir():
            self._set_token_result(f"O script local de emissão não foi encontrado em {TOKEN_ID_DIR}.", "error")
            return
        self.token_generation_busy = True
        self.active_firebase_token = ""
        if self.token_countdown_job is not None:
            try:
                self.root.after_cancel(self.token_countdown_job)
            except tk.TclError:
                pass
            self.token_countdown_job = None
        self.token_expiration_countdown = None
        self.token_metadata_table.delete(*self.token_metadata_table.get_children())
        self.token_metadata_count.configure(text="0 campos")
        self.token_expiration_badge.configure(text="Emitindo…", bg=PALETTE["blue_pale"], fg=PALETTE["blue"])
        self._set_token_result(f"Gerando token para {user.get('nome') or 'a conta selecionada'}…", "busy")
        self.copy_token_button.configure(state="disabled")
        self.token_value_text.configure(state="normal")
        self.token_value_text.delete("1.0", "end")
        self.token_value_text.insert("1.0", "Aguardando resposta do Firebase…")
        self.token_value_text.configure(state="disabled")
        for button in self.token_account_buttons:
            button.configure(state="disabled")
        self.token_refresh_button.configure(state="disabled")
        self.manual_firebase_uid_entry.configure(state="disabled")
        self.manual_firebase_uid_button.configure(state="disabled")
        threading.Thread(target=self._generate_firebase_token_worker, args=(dict(user), uid), daemon=True).start()

    def generate_token_for_manual_uid(self) -> None:
        uid = self.manual_firebase_uid_var.get().strip()
        if not uid:
            self._set_token_result("Digite o Firebase UID para gerar o token.", "error")
            self.manual_firebase_uid_entry.focus_set()
            return
        user = next((account for account in getattr(self, "token_users", []) if (account.get("firebase_uid") or "").strip() == uid), None)
        if user is None:
            user = {"firebase_uid": uid, "nome": "UID não mapeado no CSV"}
        self.generate_firebase_token(user)
    @staticmethod
    def _decode_jwt_metadata(token: str) -> tuple[dict, dict]:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("O Firebase não retornou um ID token JWT válido.")
        def decode_part(value: str) -> dict:
            padded = value + "=" * (-len(value) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
            parsed = json.loads(decoded.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("Parte do token em formato inesperado.")
            return parsed
        return decode_part(parts[0]), decode_part(parts[1])
    @staticmethod
    def _append_token_history(uid: str, creator: str, created_at: str, expires_at: str, token: str) -> int:
        fieldnames = ["id", "firebase_uid", "criado_por", "criado_em", "expiracao_estimada", "token_id"]
        next_id = 1
        if TOKEN_HISTORY_CSV.exists() and TOKEN_HISTORY_CSV.stat().st_size:
            with TOKEN_HISTORY_CSV.open("r", encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source)
                if reader.fieldnames != fieldnames:
                    raise ValueError("O cabeçalho de firebase-id-token.csv não corresponde ao formato esperado.")
                for row in reader:
                    try:
                        next_id = max(next_id, int(row.get("id", "")) + 1)
                    except (TypeError, ValueError):
                        continue
            mode = "a"
        else:
            mode = "w"
        with TOKEN_HISTORY_CSV.open(mode, encoding="utf-8", newline="") as destination:
            writer = csv.DictWriter(destination, fieldnames=fieldnames, lineterminator="\n")
            if mode == "w":
                writer.writeheader()
            writer.writerow({
                "id": next_id,
                "firebase_uid": uid,
                "criado_por": creator,
                "criado_em": created_at,
                "expiracao_estimada": expires_at,
                "token_id": token,
            })
            destination.flush()
            os.fsync(destination.fileno())
        return next_id
    def _generate_firebase_token_worker(self, user: dict[str, str], uid: str) -> None:
        result: dict = {"user": user}
        try:
            environment = os.environ.copy()
            executable = Path(sys.executable)
            if executable.name.casefold() == "pythonw.exe":
                console_executable = executable.with_name("python.exe")
                if console_executable.is_file():
                    executable = console_executable
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            completed = subprocess.run(
                [str(executable), str(TOKEN_GENERATOR_SCRIPT), uid],
                cwd=TOKEN_ID_DIR,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                creationflags=creationflags,
            )
            if completed.returncode != 0:
                raise RuntimeError("O serviço Firebase recusou a emissão. Confira as configurações locais do projeto.")
            token = completed.stdout.strip()
            if not token:
                raise RuntimeError("O processo de emissão terminou sem retornar um token.")
            header, claims = self._decode_jwt_metadata(token)
            expires_epoch = claims.get("exp")
            if not isinstance(expires_epoch, (int, float)):
                raise RuntimeError("O Firebase retornou um token sem o campo de expiração.")
            expiration = datetime.fromtimestamp(expires_epoch, tz=timezone.utc).astimezone()
            created_at = datetime.now().astimezone()
            creator = getpass.getuser().strip() or "usuário local"
            result.update(
                creator=creator,
                created_at=created_at.isoformat(timespec="seconds"),
                expiration=expiration.isoformat(timespec="seconds"),
            )
            try:
                history_id = self._append_token_history(
                    uid,
                    creator,
                    result["created_at"],
                    result["expiration"],
                    token,
                )
                result["history_id"] = history_id
            except (OSError, csv.Error, ValueError) as exc:
                result["history_error"] = str(exc)
            result.update(token=token, header=header, claims=claims, expires_epoch=int(expires_epoch))
        except subprocess.TimeoutExpired:
            result["error"] = "O Firebase não respondeu em até 60 segundos. Nenhum token foi registrado."
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError, base64.binascii.Error) as exc:
            result["error"] = str(exc)
        except Exception:
            result["error"] = "Não foi possível emitir o token. Confira a configuração local do Firebase."
        try:
            self.root.after(0, lambda value=result: self._finish_firebase_token_generation(value))
        except tk.TclError:
            pass
    def _finish_firebase_token_generation(self, result: dict) -> None:
        self.token_generation_busy = False
        for button in self.token_account_buttons:
            button.configure(state="normal")
        self.token_refresh_button.configure(state="normal")
        self.manual_firebase_uid_entry.configure(state="normal")
        self.manual_firebase_uid_button.configure(state="normal")
        if result.get("error"):
            self.token_expiration_badge.configure(text="Falha na emissão", bg=PALETTE["red_pale"], fg=PALETTE["red"])
            self._set_token_result(result["error"], "error")
            self.token_value_text.configure(state="normal")
            self.token_value_text.delete("1.0", "end")
            self.token_value_text.insert("1.0", "Nenhum token foi disponibilizado.")
            self.token_value_text.configure(state="disabled")
            return
        token = result["token"]
        self.active_firebase_token = token
        self.token_expiration_countdown = result["expires_epoch"]
        self.copy_token_button.configure(state="normal")
        self.token_value_text.configure(state="normal")
        self.token_value_text.delete("1.0", "end")
        self.token_value_text.insert("1.0", token)
        self.token_value_text.configure(state="disabled")
        account = result["user"]
        self._set_token_result(f"Emissão #{result.get('history_id', '—')} · {account.get('nome', '')}", "success")
        emission = {
            "id": result.get("history_id"),
            "criado_por": result.get("creator"),
            "criado_em": result.get("created_at"),
            "expiracao_estimada": result.get("expiration"),
        }
        self._populate_token_metadata(account, result["header"], result["claims"], emission)
        if result.get("history_error"):
            self._set_token_result("Token emitido, mas não foi possível gravar no histórico. Confira permissões e cabeçalho do CSV.", "error")
        self._update_token_expiration_countdown()
    def _populate_token_metadata(self, user: dict[str, str], header: dict, claims: dict, emission: dict | None = None) -> None:
        table = self.token_metadata_table
        table.delete(*table.get_children())
        metadata: list[tuple[str, str]] = []
        for key, value in (emission or {}).items():
            if value not in (None, ""):
                metadata.append((f"emissão.{key}", str(value)))
        for key, value in user.items():
            if value:
                metadata.append((f"conta.{key}", value))
        def flatten(prefix: str, value) -> None:
            if isinstance(value, dict):
                for nested_key, nested_value in value.items():
                    flatten(f"{prefix}.{nested_key}" if prefix else str(nested_key), nested_value)
            elif isinstance(value, list):
                metadata.append((prefix, json.dumps(value, ensure_ascii=False, separators=(",", ":"))))
            elif prefix in {"jwt.claims.iat", "jwt.claims.auth_time", "jwt.claims.exp"} and isinstance(value, (int, float)):
                local_time = datetime.fromtimestamp(value, tz=timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M:%S")
                metadata.append((prefix, local_time))
            else:
                metadata.append((prefix, json.dumps(value, ensure_ascii=False) if value is not None else "null"))
        flatten("jwt.header", header)
        flatten("jwt.claims", claims)
        for key, value in metadata:
            if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value):
                try:
                    parsed_time = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    value = parsed_time.astimezone().strftime("%d/%m/%Y %H:%M:%S")
                except ValueError:
                    pass
            table.insert("", "end", values=(key, value))
        self.token_metadata_count.configure(text=f"{len(metadata)} campos")
    def _set_token_result(self, message: str, kind: str) -> None:
        colors = {"idle": PALETTE["muted"], "busy": PALETTE["blue"], "success": PALETTE["green"], "error": PALETTE["red"]}
        self.token_result_status.configure(text=message, fg=colors.get(kind, PALETTE["muted"]))
    def _update_token_expiration_countdown(self) -> None:
        expiration = getattr(self, "token_expiration_countdown", None)
        if expiration is None or not hasattr(self, "token_expiration_badge"):
            return
        remaining = max(0, int(expiration - datetime.now(timezone.utc).timestamp()))
        minutes, seconds = divmod(remaining, 60)
        if remaining <= 0:
            self.token_expiration_badge.configure(text="Token expirado", bg=PALETTE["red_pale"], fg=PALETTE["red"])
            self.copy_token_button.configure(state="disabled")
            self.token_countdown_job = None
            return
        else:
            self.token_expiration_badge.configure(text=f"Expira em {minutes}m {seconds:02d}s", bg=PALETTE["green_pale"], fg=PALETTE["green"])
        self.token_countdown_job = self.root.after(1000, self._update_token_expiration_countdown)
    def copy_generated_token(self) -> None:
        token = getattr(self, "active_firebase_token", "")
        if not token:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(token)
        self._set_token_result("Token copiado para a área de transferência. Trate-o como uma credencial.", "success")
