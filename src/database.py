import fdb  
from .config import Config  
import threading
import queue
from contextlib import contextmanager

class FirebirdConnectionPool:
    """Pool de conexões Firebird usando apenas bibliotecas padrão Python"""
    def __init__(self, min_connections=5, max_connections=20, timeout=30):
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.timeout = timeout
        self._pool = queue.Queue(maxsize=max_connections)
        self._created = 0
        self._lock = threading.Lock()
        self._connection_params = {
            'host': Config.FIREBIRD_HOST,
            'port': Config.FIREBIRD_PORT,
            'database': Config.DATABASE_PATH,
            'user': Config.FIREBIRD_USER,
            'password': Config.FIREBIRD_PASSWORD,
            'charset': 'UTF-8'
        }
        self._initialize_pool()

    def _create_connection(self):
        """Cria uma nova conexão"""
        try:
            return fdb.connect(**self._connection_params)
        except fdb.Error as e:
            print(f"Erro ao criar conexão: {e}")
            return None

    def _initialize_pool(self):
        """Inicializa o pool com conexões mínimas"""
        for _ in range(self.min_connections):
            conn = self._create_connection()
            if conn:
                try:
                    self._pool.put_nowait(conn)
                    with self._lock:
                        self._created += 1
                except queue.Full:
                    # Pool já cheio (não deveria acontecer na inicialização)
                    try:
                        conn.close()
                    except:
                        pass

    def get_connection(self):
        """Obtém uma conexão do pool"""
        try:
            # Tenta obter conexão do pool com timeout
            conn = self._pool.get(timeout=self.timeout)
            
            # Verifica se conexão ainda está válida
            try:
                # Tenta executar um comando simples para verificar
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM RDB$DATABASE")
                cur.fetchone()
                cur.close()
            except:
                # Se conexão inválida, cria nova
                try:
                    conn.close()
                except:
                    pass
                conn = self._create_connection()
                if not conn:
                    # Se não conseguiu criar nova, tenta obter outra do pool
                    return self.get_connection()
            
            return conn
        except queue.Empty:
            # Pool vazio, verifica se pode criar nova conexão
            with self._lock:
                if self._created < self.max_connections:
                    self._created += 1
                    conn = self._create_connection()
                    if conn:
                        return conn
                    else:
                        # Se falhou ao criar, decrementa contador
                        self._created -= 1
                        return None
                else:
                    # Pool cheio, cria conexão temporária (fora do pool)
                    return self._create_connection()

    def return_connection(self, conn):
        """Retorna conexão ao pool"""
        if conn:
            try:
                # Verifica se conexão ainda está válida antes de retornar
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT 1 FROM RDB$DATABASE")
                    cur.fetchone()
                    cur.close()
                    
                    # Conexão válida, retorna ao pool
                    self._pool.put_nowait(conn)
                except:
                    # Conexão inválida, fecha e decrementa contador
                    try:
                        conn.close()
                    except:
                        pass
                    with self._lock:
                        if self._created > 0:
                            self._created -= 1
            except queue.Full:
                # Pool cheio, fecha a conexão
                try:
                    conn.close()
                except:
                    pass
                with self._lock:
                    if self._created > 0:
                        self._created -= 1

    def close_all(self):
        """Fecha todas as conexões do pool"""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                try:
                    conn.close()
                except:
                    pass
            except queue.Empty:
                break
        with self._lock:
            self._created = 0

# Instância global do pool
_pool = None
_pool_lock = threading.Lock()

def get_pool():
    """Obtém ou cria a instância do pool"""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = FirebirdConnectionPool()
    return _pool

# Wrapper para manter compatibilidade com código existente
# O código atual espera que get_db_connection() retorne uma conexão
# que precisa ser fechada manualmente. Para manter compatibilidade,
# vamos retornar uma conexão wrapper que retorna ao pool quando fechada
class PooledConnection:
    """Wrapper de conexão que retorna ao pool quando fechada"""
    def __init__(self, connection, pool):
        self._conn = connection
        self._pool = pool
        self._closed = False
    
    def __getattr__(self, name):
        """Delega todos os atributos para a conexão real"""
        return getattr(self._conn, name)
    
    def close(self):
        """Fecha a conexão e retorna ao pool"""
        if not self._closed:
            self._closed = True
            self._pool.return_connection(self._conn)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def get_db_connection():  
    """
    Obtém uma conexão do pool.
    Retorna uma conexão wrapper que automaticamente retorna ao pool quando fechada.
    Compatível com código existente que fecha conexões manualmente.
    """
    try:
        pool = get_pool()
        conn = pool.get_connection()
        if conn:
            return PooledConnection(conn, pool)
        return None
    except Exception as e:
        print(f"Erro ao obter conexão do pool: {e}")
        # Fallback: criar conexão direta em caso de erro no pool
        try:
            return fdb.connect(
                host=Config.FIREBIRD_HOST,
                port=Config.FIREBIRD_PORT,
                database=Config.DATABASE_PATH,
                user=Config.FIREBIRD_USER,
                password=Config.FIREBIRD_PASSWORD,
                charset='UTF-8'
            )
        except fdb.Error as e:
            print(f"Erro ao conectar ao Firebird: {e}")
            return None

@contextmanager
def get_db_connection_context():
    """Context manager para obter e retornar conexão automaticamente"""
    pool = get_pool()
    conn = None
    try:
        conn = pool.get_connection()
        if conn:
            yield conn
    finally:
        if conn:
            pool.return_connection(conn)  
