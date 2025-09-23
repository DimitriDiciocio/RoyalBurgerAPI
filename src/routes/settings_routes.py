from flask import Blueprint, request, jsonify, g  # importa Blueprint, request, jsonify e g
from ..services import settings_service  # importa o serviço de configurações
from ..services.auth_service import require_role  # importa decorator de autorização por papel

settings_bp = Blueprint('settings', __name__)  # cria o blueprint de configurações

@settings_bp.route('/', methods=['GET'])  # lista todas as configurações
@require_role('admin')  # restringe a administradores
def get_all_settings_route():  # função handler da listagem
    conn = None  # inicializa conexão
    try:  # bloco try para acessar o banco
        from ..database import get_db_connection  # função de conexão
        import fdb  # driver Firebird
        conn = get_db_connection()  # abre conexão
        cur = conn.cursor()  # cria cursor
        cur.execute("""
            SELECT SETTING_KEY, SETTING_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY
            FROM APP_SETTINGS
            ORDER BY SETTING_KEY
        """)  # consulta configurações
        settings = []  # lista de resultados
        for row in cur.fetchall():  # itera resultados
            settings.append({  # monta dicionário por linha
                "key": row[0],
                "value": row[1],
                "description": row[2],
                "updated_at": row[3].isoformat() if row[3] else None,
                "updated_by": row[4]
            })
        return jsonify({"settings": settings}), 200  # retorna lista com status 200
    except Exception as e:  # captura erros
        print(f"Erro ao buscar configurações: {e}")  # log simples
        return jsonify({"error": "Erro interno do servidor"}), 500  # retorna 500
    finally:  # fecha conexão se aberta
        if conn: conn.close()  # encerra conexão

@settings_bp.route('/', methods=['PUT'])  # atualiza configurações
@require_role('admin')  # restringe a administradores
def update_settings_route():  # função handler de atualização
    data = request.get_json()  # captura corpo JSON
    if not data or 'settings' not in data:  # valida presença da lista
        return jsonify({"error": "Corpo da requisição deve conter uma lista 'settings'"}), 400  # retorna 400
    settings_list = data['settings']  # extrai lista
    if not isinstance(settings_list, list):  # valida tipo lista
        return jsonify({"error": "O campo 'settings' deve ser uma lista"}), 400  # retorna 400
    user_id = g.current_user_id if hasattr(g, 'current_user_id') else None  # obtém ID do usuário
    if not user_id:  # valida autenticação
        return jsonify({"error": "Usuário não autenticado"}), 401  # retorna 401
    updated_settings = []  # acumula atualizadas
    errors = []  # acumula erros
    for setting in settings_list:  # itera configurações
        if not isinstance(setting, dict) or 'key' not in setting or 'value' not in setting:  # valida item
            errors.append("Cada configuração deve ter 'key' e 'value'")  # adiciona erro
            continue  # próximo item
        key = setting['key']  # extrai chave
        value = setting['value']  # extrai valor
        success = settings_service.update_setting(key, value, user_id)  # atualiza via serviço
        if success:  # sucesso
            updated_settings.append({"key": key, "value": value})  # adiciona aos atualizados
        else:  # falha
            errors.append(f"Falha ao atualizar configuração '{key}'")  # registra erro
    if errors:  # se houve erros
        return jsonify({
            "msg": f"Atualizadas {len(updated_settings)} configurações",
            "updated_settings": updated_settings,
            "errors": errors
        }), 207  # Multi-Status
    return jsonify({  # sucesso total
        "msg": f"Todas as {len(updated_settings)} configurações foram atualizadas com sucesso",
        "updated_settings": updated_settings
    }), 200  # retorna 200
