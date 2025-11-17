import fdb
import logging
from ..database import get_db_connection
from datetime import datetime

logger = logging.getLogger(__name__)

# Cache de configurações em memória para melhor performance
_settings_cache = None
_cache_timestamp = None
_cache_ttl_seconds = 300  # 5 minutos de TTL

def _is_cache_valid():
    """Verifica se o cache ainda é válido"""
    global _cache_timestamp
    if _cache_timestamp is None:
        return False
    elapsed = (datetime.now() - _cache_timestamp).total_seconds()
    return elapsed < _cache_ttl_seconds

def _invalidate_cache():
    """Invalida o cache forçando refresh na próxima chamada"""
    global _settings_cache, _cache_timestamp
    _settings_cache = None
    _cache_timestamp = None

def get_all_settings(use_cache=True):
    """
    Retorna as configurações atuais (última versão)
    
    Args:
        use_cache: Se True, usa cache em memória. Se False, força busca no banco.
                   Padrão True para melhor performance.
    """
    global _settings_cache, _cache_timestamp
    
    # Verifica cache se estiver habilitado
    if use_cache and _is_cache_valid() and _settings_cache is not None:
        return _settings_cache
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca a última versão completa das configurações
        # ALTERAÇÃO FASE 3: Incluir campos de taxas de pagamento
        cur.execute("""
            SELECT 
                ID,
                META_RECEITA_MENSAL, META_PEDIDOS_MENSAIS,
                PRAZO_INICIACAO, PRAZO_PREPARO, PRAZO_ENVIO, PRAZO_ENTREGA,
                TAXA_ENTREGA, TAXA_CONVERSAO_GANHO_CLUBE, TAXA_CONVERSAO_RESGATE_CLUBE, TAXA_EXPIRACAO_PONTOS_CLUBE,
                TAXA_CARTAO_CREDITO, TAXA_CARTAO_DEBITO, TAXA_PIX, TAXA_IFOOD, TAXA_UBER_EATS,
                NOME_FANTASIA, RAZAO_SOCIAL, CNPJ, ENDERECO, TELEFONE, EMAIL,
                UPDATED_AT, UPDATED_BY
            FROM APP_SETTINGS
            WHERE ID = (SELECT MAX(ID) FROM APP_SETTINGS)
        """)
        
        row = cur.fetchone()
        if not row:
            # Retorna configurações vazias se não houver nenhuma
            # ALTERAÇÃO FASE 3: Incluir campos de taxas de pagamento
            settings = {
                "id": None,
                "meta_receita_mensal": None,
                "meta_pedidos_mensais": None,
                "prazo_iniciacao": None,
                "prazo_preparo": None,
                "prazo_envio": None,
                "prazo_entrega": None,
                "taxa_entrega": None,
                "taxa_conversao_ganho_clube": None,
                "taxa_conversao_resgate_clube": None,
                "taxa_expiracao_pontos_clube": None,
                "taxa_cartao_credito": None,
                "taxa_cartao_debito": None,
                "taxa_pix": None,
                "taxa_ifood": None,
                "taxa_uber_eats": None,
                "nome_fantasia": None,
                "razao_social": None,
                "cnpj": None,
                "endereco": None,
                "telefone": None,
                "email": None,
                "updated_at": None,
                "updated_by": None,
                "updated_by_name": None
            }
        else:
            # Busca o nome do usuário que atualizou
            # ALTERAÇÃO FASE 3: Ajustar índice do UPDATED_BY (agora é row[23] ao invés de row[18])
            cur.execute("SELECT FULL_NAME FROM USERS WHERE ID = ?", (row[23],))
            user_row = cur.fetchone()
            updated_by_name = user_row[0] if user_row else None
            
            settings = {
                "id": row[0],
                "meta_receita_mensal": float(row[1]) if row[1] else None,
                "meta_pedidos_mensais": row[2],
                "prazo_iniciacao": row[3],
                "prazo_preparo": row[4],
                "prazo_envio": row[5],
                "prazo_entrega": row[6],
                "taxa_entrega": float(row[7]) if row[7] else None,
                "taxa_conversao_ganho_clube": float(row[8]) if row[8] else None,
                "taxa_conversao_resgate_clube": float(row[9]) if row[9] else None,
                "taxa_expiracao_pontos_clube": row[10],
                # ALTERAÇÃO FASE 3: Incluir campos de taxas de pagamento
                "taxa_cartao_credito": float(row[11]) if row[11] else None,
                "taxa_cartao_debito": float(row[12]) if row[12] else None,
                "taxa_pix": float(row[13]) if row[13] else None,
                "taxa_ifood": float(row[14]) if row[14] else None,
                "taxa_uber_eats": float(row[15]) if row[15] else None,
                "nome_fantasia": row[16],
                "razao_social": row[17],
                "cnpj": row[18],
                "endereco": row[19],
                "telefone": row[20],
                "email": row[21],
                "updated_at": row[22].isoformat() if row[22] else None,
                "updated_by": row[23],
                "updated_by_name": updated_by_name
            }
        
        # Atualiza cache
        _settings_cache = settings
        _cache_timestamp = datetime.now()
        
        return settings
    except fdb.Error as e:
        # ALTERAÇÃO: Usar logger ao invés de print() em código de produção
        logger.error(f"Erro ao buscar configurações (fdb.Error): {e}", exc_info=True)
        raise  # Re-lança para tratamento na rota
    except Exception as e:
        # ALTERAÇÃO: Usar logger ao invés de print() e capturar outras exceções não esperadas
        logger.error(f"Erro inesperado ao buscar configurações: {e}", exc_info=True)
        raise  # Re-lança para tratamento na rota
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                # ALTERAÇÃO: Usar logger ao invés de print() para erros ao fechar conexão
                logger.warning(f"Erro ao fechar conexão ao buscar configurações: {e}", exc_info=True)

def update_settings(settings_data, user_id):
    """
    Atualiza configurações no registro existente ou cria se não existir.
    Mantém histórico através das funções get_settings_history e rollback_setting.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        field_mapping = {
            'meta_receita_mensal': 'META_RECEITA_MENSAL',
            'meta_pedidos_mensais': 'META_PEDIDOS_MENSAIS',
            'prazo_iniciacao': 'PRAZO_INICIACAO',
            'prazo_preparo': 'PRAZO_PREPARO',
            'prazo_envio': 'PRAZO_ENVIO',
            'prazo_entrega': 'PRAZO_ENTREGA',
            'taxa_entrega': 'TAXA_ENTREGA',
            'taxa_conversao_ganho_clube': 'TAXA_CONVERSAO_GANHO_CLUBE',
            'taxa_conversao_resgate_clube': 'TAXA_CONVERSAO_RESGATE_CLUBE',
            'taxa_expiracao_pontos_clube': 'TAXA_EXPIRACAO_PONTOS_CLUBE',
            'nome_fantasia': 'NOME_FANTASIA',
            'razao_social': 'RAZAO_SOCIAL',
            'cnpj': 'CNPJ',
            'endereco': 'ENDERECO',
            'telefone': 'TELEFONE',
            'email': 'EMAIL'
        }
        
        # Busca o registro mais recente (se existir) para atualizar
        cur.execute("SELECT MAX(ID) FROM APP_SETTINGS")
        max_id_result = cur.fetchone()
        settings_id = max_id_result[0] if max_id_result else None
        
        if settings_id:
            # ATUALIZA o registro existente
            # Monta SET clause para UPDATE
            set_clauses = []
            update_values = []
            
            for key, column in field_mapping.items():
                if key in settings_data:
                    set_clauses.append(f"{column} = ?")
                    update_values.append(settings_data[key])
            
            # Sempre atualiza UPDATED_BY e UPDATED_AT
            set_clauses.append("UPDATED_BY = ?")
            set_clauses.append("UPDATED_AT = CURRENT_TIMESTAMP")
            update_values.append(user_id)
            
            if not set_clauses:
                return False
            
            # Adiciona o ID no final para o WHERE
            update_values.append(settings_id)
            
            # Monta o SQL de atualização
            sql = f"""
                UPDATE APP_SETTINGS
                SET {', '.join(set_clauses)}
                WHERE ID = ?
            """
            
            cur.execute(sql, update_values)
            conn.commit()
            
            # Invalida cache após atualização bem-sucedida
            _invalidate_cache()
            
            return True
        else:
            # Não existe registro: CRIA o primeiro (INSERT)
            fields = []
            values = []
            placeholders = []
            
            # Adiciona campos que estão no payload
            for key, column in field_mapping.items():
                if key in settings_data:
                    fields.append(column)
                    values.append(settings_data[key])
                    placeholders.append('?')
            
            # Sempre adiciona UPDATED_BY e UPDATED_AT
            fields.append('UPDATED_BY')
            fields.append('UPDATED_AT')
            values.append(user_id)
            placeholders.append('?')
            placeholders.append('CURRENT_TIMESTAMP')
            
            if not fields:
                return False
            
            # Monta o SQL de inserção
            sql = f"""
                INSERT INTO APP_SETTINGS ({', '.join(fields)})
                VALUES ({', '.join(placeholders)})
            """
            
            cur.execute(sql, values)
            conn.commit()
            
            # Invalida cache após inserção bem-sucedida
            _invalidate_cache()
            
            return True
            
    except fdb.Error as e:
        # ALTERAÇÃO: Usar logger ao invés de print() em código de produção
        logger.error(f"Erro ao atualizar configurações: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_settings_history():
    """Retorna o histórico completo de configurações"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT 
                s.ID,
                s.META_RECEITA_MENSAL, s.META_PEDIDOS_MENSAIS,
                s.PRAZO_INICIACAO, s.PRAZO_PREPARO, s.PRAZO_ENVIO, s.PRAZO_ENTREGA,
                s.TAXA_ENTREGA, s.TAXA_CONVERSAO_GANHO_CLUBE, s.TAXA_CONVERSAO_RESGATE_CLUBE, s.TAXA_EXPIRACAO_PONTOS_CLUBE,
                s.NOME_FANTASIA, s.RAZAO_SOCIAL, s.CNPJ, s.ENDERECO, s.TELEFONE, s.EMAIL,
                s.UPDATED_AT, s.UPDATED_BY, u.FULL_NAME
            FROM APP_SETTINGS s
            LEFT JOIN USERS u ON s.UPDATED_BY = u.ID
            ORDER BY s.ID DESC
        """)
        
        history = []
        for row in cur.fetchall():
            history.append({
                "id": row[0],
                "meta_receita_mensal": float(row[1]) if row[1] else None,
                "meta_pedidos_mensais": row[2],
                "prazo_iniciacao": row[3],
                "prazo_preparo": row[4],
                "prazo_envio": row[5],
                "prazo_entrega": row[6],
                "taxa_entrega": float(row[7]) if row[7] else None,
                "taxa_conversao_ganho_clube": float(row[8]) if row[8] else None,
                "taxa_conversao_resgate_clube": float(row[9]) if row[9] else None,
                "taxa_expiracao_pontos_clube": row[10],
                "nome_fantasia": row[11],
                "razao_social": row[12],
                "cnpj": row[13],
                "endereco": row[14],
                "telefone": row[15],
                "email": row[16],
                "updated_at": row[17].isoformat() if row[17] else None,
                "updated_by": row[18],
                "updated_by_name": row[19]
            })
        
        return history
    except fdb.Error as e:
        # ALTERAÇÃO: Usar logger ao invés de print() em código de produção
        logger.error(f"Erro ao buscar histórico de configurações: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()

def rollback_setting(history_id, user_id):
    """Faz rollback para uma versão anterior, atualizando o registro existente"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca a configuração do histórico
        cur.execute("""
            SELECT 
                META_RECEITA_MENSAL, META_PEDIDOS_MENSAIS,
                PRAZO_INICIACAO, PRAZO_PREPARO, PRAZO_ENVIO, PRAZO_ENTREGA,
                TAXA_ENTREGA, TAXA_CONVERSAO_GANHO_CLUBE, TAXA_CONVERSAO_RESGATE_CLUBE, TAXA_EXPIRACAO_PONTOS_CLUBE,
                NOME_FANTASIA, RAZAO_SOCIAL, CNPJ, ENDERECO, TELEFONE, EMAIL
            FROM APP_SETTINGS
            WHERE ID = ?
        """, (history_id,))
        
        row = cur.fetchone()
        if not row:
            return False
        
        # Busca o ID do registro atual para atualizar
        cur.execute("SELECT MAX(ID) FROM APP_SETTINGS")
        max_id_result = cur.fetchone()
        current_settings_id = max_id_result[0] if max_id_result else None
        
        if not current_settings_id:
            return False
        
        # Atualiza o registro atual com os valores do histórico selecionado
        cur.execute("""
            UPDATE APP_SETTINGS SET
                META_RECEITA_MENSAL = ?,
                META_PEDIDOS_MENSAIS = ?,
                PRAZO_INICIACAO = ?,
                PRAZO_PREPARO = ?,
                PRAZO_ENVIO = ?,
                PRAZO_ENTREGA = ?,
                TAXA_ENTREGA = ?,
                TAXA_CONVERSAO_GANHO_CLUBE = ?,
                TAXA_CONVERSAO_RESGATE_CLUBE = ?,
                TAXA_EXPIRACAO_PONTOS_CLUBE = ?,
                NOME_FANTASIA = ?,
                RAZAO_SOCIAL = ?,
                CNPJ = ?,
                ENDERECO = ?,
                TELEFONE = ?,
                EMAIL = ?,
                UPDATED_BY = ?,
                UPDATED_AT = CURRENT_TIMESTAMP
            WHERE ID = ?
        """, row + (user_id, current_settings_id))
        
        conn.commit()
        
        # Invalida cache após rollback bem-sucedido
        _invalidate_cache()
        
        return True
    except fdb.Error as e:
        # ALTERAÇÃO: Usar logger ao invés de print() em código de produção
        logger.error(f"Erro ao fazer rollback de configurações (history_id={history_id}): {e}", exc_info=True)
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()
