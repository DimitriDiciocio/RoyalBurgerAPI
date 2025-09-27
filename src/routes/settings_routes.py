from flask import Blueprint, request, jsonify, g  
from ..services import settings_service  
from ..services.auth_service import require_role  

settings_bp = Blueprint('settings', __name__)  

@settings_bp.route('/', methods=['GET'])  
@require_role('admin')  
def get_all_settings_route():  
    conn = None  
    try:  
        from ..database import get_db_connection  
        import fdb  
        conn = get_db_connection()  
        cur = conn.cursor()  
        cur.execute("""
            SELECT SETTING_KEY, SETTING_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY
            FROM APP_SETTINGS
            ORDER BY SETTING_KEY
        """)  
        settings = []  
        for row in cur.fetchall():  
            settings.append({  
                "key": row[0],
                "value": row[1],
                "description": row[2],
                "updated_at": row[3].isoformat() if row[3] else None,
                "updated_by": row[4]
            })
        return jsonify({"settings": settings}), 200  
    except Exception as e:  
        print(f"Erro ao buscar configurações: {e}")  
        return jsonify({"error": "Erro interno do servidor"}), 500  
    finally:  
        if conn: conn.close()  

@settings_bp.route('/', methods=['PUT'])  
@require_role('admin')  
def update_settings_route():  
    data = request.get_json()  
    if not data or 'settings' not in data:  
        return jsonify({"error": "Corpo da requisição deve conter uma lista 'settings'"}), 400  
    settings_list = data['settings']  
    if not isinstance(settings_list, list):  
        return jsonify({"error": "O campo 'settings' deve ser uma lista"}), 400  
    user_id = g.current_user_id if hasattr(g, 'current_user_id') else None  
    if not user_id:  
        return jsonify({"error": "Usuário não autenticado"}), 401  
    updated_settings = []  
    errors = []  
    for setting in settings_list:  
        if not isinstance(setting, dict) or 'key' not in setting or 'value' not in setting:  
            errors.append("Cada configuração deve ter 'key' e 'value'")  
            continue  
        key = setting['key']  
        value = setting['value']  
        success = settings_service.update_setting(key, value, user_id)  
        if success:  
            updated_settings.append({"key": key, "value": value})  
        else:  
            errors.append(f"Falha ao atualizar configuração '{key}'")  
    if errors:  
        return jsonify({
            "msg": f"Atualizadas {len(updated_settings)} configurações",
            "updated_settings": updated_settings,
            "errors": errors
        }), 207  
    return jsonify({  
        "msg": f"Todas as {len(updated_settings)} configurações foram atualizadas com sucesso",
        "updated_settings": updated_settings
    }), 200  
