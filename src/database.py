# src/database.py

import fdb
from .config import Config

def get_db_connection():
    """
    Cria e retorna uma nova conexão com o banco de dados Firebird.
    """
    try:
        # CORREÇÃO: Usamos os parâmetros separados em vez de um DSN
        conn = fdb.connect(
            host=Config.FIREBIRD_HOST,
            port=Config.FIREBIRD_PORT,
            database=Config.DATABASE_PATH,  # Usamos o caminho do arquivo aqui
            user=Config.FIREBIRD_USER,
            password=Config.FIREBIRD_PASSWORD,
            charset='UTF-8'
        )
        return conn
    except fdb.Error as e:
        print(f"Erro ao conectar ao Firebird: {e}")
        return None