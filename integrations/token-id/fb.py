"""Emite um Firebase ID token para um UID configurado no ambiente local."""

import os
import sys
from pathlib import Path

import firebase_admin
import requests
from dotenv import load_dotenv
from firebase_admin import auth, credentials


TOKEN_DIR = Path(__file__).resolve().parent
load_dotenv(TOKEN_DIR / ".env")


def obter_token(firebase_uid: str) -> str:
    credential_value = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "firebase-service-account.json")
    credential_path = Path(credential_value)
    if not credential_path.is_absolute():
        credential_path = TOKEN_DIR / credential_path
    api_key = os.getenv("FIREBASE_WEB_API_KEY")
    if not api_key:
        raise RuntimeError("FIREBASE_WEB_API_KEY não foi configurada em integrations/token-id/.env.")

    firebase_admin.initialize_app(credentials.Certificate(str(credential_path)))
    custom_token = auth.create_custom_token(firebase_uid).decode("utf-8")
    response = requests.post(
        "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken",
        params={"key": api_key},
        json={"token": custom_token, "returnSecureToken": True},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["idToken"]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python fb.py <firebase_uid>")
    print(obter_token(sys.argv[1]))
