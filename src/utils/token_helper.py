import secrets  # importa biblioteca para geração de tokens seguros
import datetime  # importa classes de data e tempo
from ..database import get_db_connection  # importa função de conexão com banco
import fdb  # importa driver do Firebird

def generate_secure_token(length=32):  # função para gerar token seguro
    return secrets.token_urlsafe(length)  # retorna token URL-safe com tamanho especificado