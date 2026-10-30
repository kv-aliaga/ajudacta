from __future__ import annotations

import configparser
import os
import re
import tempfile
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from botocore.session import Session as BotocoreSession

from .constants import CONFIG_PATH, CREDENTIALS_PATH, REGION_PATTERN, REQUIRED_KEYS


def read_optional(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8-sig")


def default_region(config_text: str | None) -> str:
    if config_text:
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read_string(config_text)
            section = next((name for name in parser.sections() if name.casefold() == "default"), None)
            if section:
                value = parser[section].get("region", "").strip()
                if REGION_PATTERN.fullmatch(value):
                    return value
        except configparser.Error:
            pass
    return "us-east-1"


def parse_ini(raw: str) -> tuple[dict[str, str], str | None]:
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        parser.read_string(raw)
    except configparser.Error as exc:
        raise ValueError("O texto não parece um INI válido. Confira o bloco [default].") from exc

    section_name = next((name for name in parser.sections() if name.casefold() == "default"), None)
    if section_name is None:
        raise ValueError("Não encontrei a seção [default] no texto colado.")

    section = parser[section_name]
    credentials = {key: section.get(key, "").strip() for key in REQUIRED_KEYS}
    missing = [key for key, value in credentials.items() if not value]
    if missing:
        labels = {
            "aws_access_key_id": "aws_access_key_id",
            "aws_secret_access_key": "aws_secret_access_key",
            "aws_session_token": "aws_session_token",
        }
        raise ValueError("Faltou preencher: " + ", ".join(labels[key] for key in missing) + ".")

    region = section.get("region", "").strip() or None
    return credentials, region


def replace_ini_section(text: str | None, section_name: str, values: dict[str, str]) -> str:
    original = text or ""
    newline = "\r\n" if "\r\n" in original else "\n"
    lines = original.splitlines(keepends=True)
    section_re = re.compile(r"^\s*\[([^]]+)\]\s*(?:[#;].*)?(?:\r?\n)?$")
    headers: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = section_re.match(line)
        if match:
            headers.append((index, match.group(1).strip()))

    matching = [index for index, name in headers if name.casefold() == section_name.casefold()]
    if len(matching) > 1:
        raise ValueError(f"O arquivo AWS tem mais de uma seção [{section_name}]. Corrija-a antes de continuar.")

    if not matching:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += newline
        if lines and lines[-1].strip():
            lines.append(newline)
        lines.append(f"[{section_name}]{newline}")
        for key, value in values.items():
            lines.append(f"{key} = {value}{newline}")
        return "".join(lines)

    start = matching[0]
    end = next((index for index, _ in headers if index > start), len(lines))
    body = lines[start + 1:end]
    for key, value in values.items():
        key_re = re.compile(r"^\s*" + re.escape(key) + r"\s*=")
        positions = [index for index, line in enumerate(body) if key_re.match(line)]
        replacement = f"{key} = {value}{newline}"
        if positions:
            body[positions[0]] = replacement
            for duplicate in reversed(positions[1:]):
                del body[duplicate]
        else:
            body.append(replacement)
    return "".join(lines[:start + 1] + body + lines[end:])


def atomic_write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + "-", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(contents)
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def restore(path: Path, original: str | None) -> None:
    if original is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    else:
        atomic_write(path, original)


def update_and_validate(raw: str, region_from_field: str) -> tuple[bool, str, str]:
    credentials, pasted_region = parse_ini(raw)
    region = pasted_region or region_from_field.strip()
    if not REGION_PATTERN.fullmatch(region):
        raise ValueError("Informe uma região AWS válida, como us-east-1.")

    old_credentials = read_optional(CREDENTIALS_PATH)
    old_config = read_optional(CONFIG_PATH)
    new_credentials = replace_ini_section(old_credentials, "default", credentials)
    new_config = replace_ini_section(old_config, "default", {"region": region})

    try:
        atomic_write(CREDENTIALS_PATH, new_credentials)
        atomic_write(CONFIG_PATH, new_config)
        botocore_session = BotocoreSession()
        botocore_session.set_config_variable("profile", "default")
        botocore_session.set_config_variable("config_file", str(CONFIG_PATH))
        botocore_session.set_config_variable("credentials_file", str(CREDENTIALS_PATH))
        botocore_session.set_config_variable("region", region)
        session = boto3.Session(botocore_session=botocore_session)
        sts = session.client(
            "sts",
            config=Config(connect_timeout=8, read_timeout=17, retries={"total_max_attempts": 1}),
        )
        identity = sts.get_caller_identity()
        if not identity.get("Account") or not identity.get("Arn"):
            restore(CREDENTIALS_PATH, old_credentials)
            restore(CONFIG_PATH, old_config)
            return False, "O STS respondeu, mas não foi possível confirmar a identidade. Perfil anterior restaurado.", region

        return True, "Perfil atualizado e validado com STS.", region
    except ClientError as exc:
        restore(CREDENTIALS_PATH, old_credentials)
        restore(CONFIG_PATH, old_config)
        code = exc.response.get("Error", {}).get("Code", "")
        safe_code = code if re.fullmatch(r"[A-Za-z0-9-]+", code) else "AWS error"
        return False, f"AWS retornou {safe_code}. O perfil anterior foi restaurado.", region
    except BotoCoreError as exc:
        restore(CREDENTIALS_PATH, old_credentials)
        restore(CONFIG_PATH, old_config)
        return False, f"Falha na validação do STS ({type(exc).__name__}). O perfil anterior foi restaurado.", region
    except Exception as exc:
        try:
            restore(CREDENTIALS_PATH, old_credentials)
            restore(CONFIG_PATH, old_config)
        except Exception:
            pass
        message = str(exc)
        if isinstance(exc, (OSError, ValueError)):
            return False, message, region
        return False, "Não foi possível atualizar o perfil. O perfil anterior foi restaurado.", region
