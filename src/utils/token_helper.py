# packages/src/src/utils/token_helper.py

import secrets
import datetime
from ..database import get_db_connection
import fdb

def generate_secure_token(length=32):
    """Gera um token de texto seguro e URL-safe."""
    return secrets.token_urlsafe(length)

# Podemos adicionar outras funções de token aqui no futuro se precisarmos