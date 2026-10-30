from __future__ import annotations

from pathlib import Path
import re

APP_ROOT = Path(__file__).resolve().parent.parent

APP_TITLE = "AWS Default Profile"

APP_ICON_PATH = APP_ROOT / "logo-acta.png"

PALETTE = {
    "canvas": "#F3F5F8",
    "surface": "#FFFFFF",
    "ink": "#182638",
    "muted": "#66768A",
    "line": "#DDE4EC",
    "blue": "#315ED6",
    "blue_hover": "#244BB8",
    "blue_pale": "#EAF0FF",
    "nav": "#17263B",
    "nav_hover": "#233650",
    "nav_text": "#F2F6FC",
    "nav_muted": "#9AABC0",
    "green": "#137A55",
    "green_pale": "#E7F6EF",
    "red": "#A93434",
    "red_pale": "#FFF0F0",
    "editor": "#FAFBFD",
}

AWS_DIR = Path.home() / ".aws"

CREDENTIALS_PATH = AWS_DIR / "credentials"

CONFIG_PATH = AWS_DIR / "config"

REQUIRED_KEYS = ("aws_access_key_id", "aws_secret_access_key", "aws_session_token")

REGION_PATTERN = re.compile(r"^[a-z]{2}(?:-[a-z0-9]+)+-\d+$", re.IGNORECASE)

LOG_DEPLOYMENTS = {
    "Auth API": "acta-auth-api",
    "PostgreSQL API": "acta-pg-api",
    "MongoDB API": "acta-mongo-api",
    "Import API": "acta-import-api",
    "FCM API": "acta-fcm-api",
    "AI": "acta-ai",
    "MCP": "acta-mcp",
}

KUBECONFIG_PATH = Path.home() / ".kube" / "acta-aws.yaml"

TOKEN_ID_DIR = Path.home() / "Desktop" / "token-id"

TOKEN_USERS_CSV = TOKEN_ID_DIR / "firebaseuid_validos.csv"

TOKEN_HISTORY_CSV = TOKEN_ID_DIR / "firebase-id-token.csv"

TOKEN_GENERATOR_SCRIPT = TOKEN_ID_DIR / "fb.py"

INFISICAL_ENV_PATH = APP_ROOT / ".env"

PLATFORM_REPO = Path(r"C:\Users\daviramOS-ieg\Desktop\2º ano\Inter\Github\acta-platform")

PLATFORM_TERRAFORM_DIR = PLATFORM_REPO / "infra" / "aws"

PLATFORM_DEPLOY_SCRIPT = PLATFORM_TERRAFORM_DIR / "deploy.ps1"

REBUILD_REQUIRED_STATE = {"aws_vpc.acta", "aws_instance.k3s", "aws_eip.k3s"}

HEALTH_SUCCESS_PATTERN = re.compile(
    r'"\s*(?:GET|HEAD)\s+\S*/(?:healthz?|readyz?|livez?)(?:\?[^\s]*)?\s+HTTP/\d(?:\.\d)?"\s+200(?:\s|$)',
    re.IGNORECASE,
)
