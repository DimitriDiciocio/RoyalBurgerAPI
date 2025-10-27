import fdb
from ..database import get_db_connection

def get_all_settings():
    """Retorna as configurações atuais (última versão)"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca a última versão completa das configurações
        cur.execute("""
            SELECT 
                ID,
                META_RECEITA_MENSAL, META_PEDIDOS_MENSAIS,
                PRAZO_INICIACAO, PRAZO_PREPARO, PRAZO_ENVIO, PRAZO_ENTREGA,
                TAXA_ENTREGA, TAXA_CONVERSAO_CLUBE, TAXA_EXPIRACAO_PONTOS_CLUBE,
                NOME_FANTASIA, RAZAO_SOCIAL, CNPJ, ENDERECO, TELEFONE, EMAIL,
                UPDATED_AT, UPDATED_BY
            FROM APP_SETTINGS
            WHERE ID = (SELECT MAX(ID) FROM APP_SETTINGS)
        """)
        
        row = cur.fetchone()
        if not row:
            # Retorna configurações vazias se não houver nenhuma
            return {
                "id": None,
                "meta_receita_mensal": None,
                "meta_pedidos_mensais": None,
                "prazo_iniciacao": None,
                "prazo_preparo": None,
                "prazo_envio": None,
                "prazo_entrega": None,
                "taxa_entrega": None,
                "taxa_conversao_clube": None,
                "taxa_expiracao_pontos_clube": None,
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
        
        # Busca o nome do usuário que atualizou
        cur.execute("SELECT FULL_NAME FROM USERS WHERE ID = ?", (row[17],))
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
            "taxa_conversao_clube": float(row[8]) if row[8] else None,
            "taxa_expiracao_pontos_clube": row[9],
            "nome_fantasia": row[10],
            "razao_social": row[11],
            "cnpj": row[12],
            "endereco": row[13],
            "telefone": row[14],
            "email": row[15],
            "updated_at": row[16].isoformat() if row[16] else None,
            "updated_by": row[17],
            "updated_by_name": updated_by_name
        }
        
        return settings
    except fdb.Error as e:
        print(f"Erro ao buscar configurações: {e}")
        return None
    finally:
        if conn:
            conn.close()

def update_settings(settings_data, user_id):
    """Atualiza configurações criando uma nova versão completa"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Monta a lista de campos e valores para inserção
        fields = []
        values = []
        placeholders = []
        
        field_mapping = {
            'meta_receita_mensal': 'META_RECEITA_MENSAL',
            'meta_pedidos_mensais': 'META_PEDIDOS_MENSAIS',
            'prazo_iniciacao': 'PRAZO_INICIACAO',
            'prazo_preparo': 'PRAZO_PREPARO',
            'prazo_envio': 'PRAZO_ENVIO',
            'prazo_entrega': 'PRAZO_ENTREGA',
            'taxa_entrega': 'TAXA_ENTREGA',
            'taxa_conversao_clube': 'TAXA_CONVERSAO_CLUBE',
            'taxa_expiracao_pontos_clube': 'TAXA_EXPIRACAO_PONTOS_CLUBE',
            'nome_fantasia': 'NOME_FANTASIA',
            'razao_social': 'RAZAO_SOCIAL',
            'cnpj': 'CNPJ',
            'endereco': 'ENDERECO',
            'telefone': 'TELEFONE',
            'email': 'EMAIL'
        }
        
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
        values.append('CURRENT_TIMESTAMP')
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
        
        return True
    except fdb.Error as e:
        print(f"Erro ao atualizar configurações: {e}")
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
                s.TAXA_ENTREGA, s.TAXA_CONVERSAO_CLUBE, s.TAXA_EXPIRACAO_PONTOS_CLUBE,
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
                "taxa_conversao_clube": float(row[8]) if row[8] else None,
                "taxa_expiracao_pontos_clube": row[9],
                "nome_fantasia": row[10],
                "razao_social": row[11],
                "cnpj": row[12],
                "endereco": row[13],
                "telefone": row[14],
                "email": row[15],
                "updated_at": row[16].isoformat() if row[16] else None,
                "updated_by": row[17],
                "updated_by_name": row[18]
            })
        
        return history
    except fdb.Error as e:
        print(f"Erro ao buscar histórico: {e}")
        return []
    finally:
        if conn:
            conn.close()

def rollback_setting(history_id, user_id):
    """Faz rollback para uma versão anterior, criando uma nova entrada"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Busca a configuração do histórico
        cur.execute("""
            SELECT 
                META_RECEITA_MENSAL, META_PEDIDOS_MENSAIS,
                PRAZO_INICIACAO, PRAZO_PREPARO, PRAZO_ENVIO, PRAZO_ENTREGA,
                TAXA_ENTREGA, TAXA_CONVERSAO_CLUBE, TAXA_EXPIRACAO_PONTOS_CLUBE,
                NOME_FANTASIA, RAZAO_SOCIAL, CNPJ, ENDERECO, TELEFONE, EMAIL
            FROM APP_SETTINGS
            WHERE ID = ?
        """, (history_id,))
        
        row = cur.fetchone()
        if not row:
            return False
        
        # Cria uma nova entrada com os valores antigos
        cur.execute("""
            INSERT INTO APP_SETTINGS (
                META_RECEITA_MENSAL, META_PEDIDOS_MENSAIS,
                PRAZO_INICIACAO, PRAZO_PREPARO, PRAZO_ENVIO, PRAZO_ENTREGA,
                TAXA_ENTREGA, TAXA_CONVERSAO_CLUBE, TAXA_EXPIRACAO_PONTOS_CLUBE,
                NOME_FANTASIA, RAZAO_SOCIAL, CNPJ, ENDERECO, TELEFONE, EMAIL,
                UPDATED_BY, UPDATED_AT
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, row + (user_id,))
        
        conn.commit()
        return True
    except fdb.Error as e:
        print(f"Erro ao fazer rollback: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()
