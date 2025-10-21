from flask import Blueprint, request, jsonify
from ..services import cart_service
from ..services.auth_service import require_role
from flask_jwt_extended import jwt_required, get_jwt_identity

cart_bp = Blueprint('cart', __name__)

@cart_bp.route('/me', methods=['GET'])
@jwt_required()
def get_cart_route():
    """
    Fluxo 1: Visualização do Carrinho
    Retorna o estado completo do carrinho do usuário autenticado
    """
    try:
        user_id = get_jwt_identity()
        cart_summary = cart_service.get_cart_summary(user_id)
        
        if not cart_summary:
            return jsonify({"error": "Erro ao acessar carrinho"}), 500
        
        return jsonify(cart_summary), 200
        
    except Exception as e:
        print(f"Erro ao buscar carrinho: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500


@cart_bp.route('/me/items', methods=['POST'])
@jwt_required()
def add_item_to_cart_route():
    """
    Fluxo 2: Adicionar Item ao Carrinho
    Adiciona um produto ao carrinho com opcionais extras
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Dados da requisição são obrigatórios"}), 400
        
        product_id = data.get('product_id')
        quantity = data.get('quantity', 1)
        extras = data.get('extras', [])
        notes = data.get('notes')
        
        # Validações
        if not product_id:
            return jsonify({"error": "product_id é obrigatório"}), 400
        
        if not isinstance(quantity, int) or quantity <= 0:
            return jsonify({"error": "quantity deve ser um número inteiro positivo"}), 400
        
        if not isinstance(extras, list):
            return jsonify({"error": "extras deve ser uma lista"}), 400
        
        # Valida extras
        for extra in extras:
            if not isinstance(extra, dict):
                return jsonify({"error": "Cada extra deve ser um objeto"}), 400
            
            if not extra.get('ingredient_id'):
                return jsonify({"error": "ingredient_id é obrigatório em cada extra"}), 400
            
            extra_quantity = extra.get('quantity', 1)
            if not isinstance(extra_quantity, int) or extra_quantity <= 0:
                return jsonify({"error": "quantity do extra deve ser um número inteiro positivo"}), 400
        
        # Adiciona item ao carrinho
        success, error_code, message = cart_service.add_item_to_cart(user_id, product_id, quantity, extras, notes)
        
        if not success:
            if error_code == "PRODUCT_NOT_FOUND":
                return jsonify({"error": message}), 404
            elif error_code == "CART_ERROR":
                return jsonify({"error": message}), 500
            elif error_code == "DATABASE_ERROR":
                return jsonify({"error": message}), 500
            else:
                return jsonify({"error": "Erro ao adicionar item ao carrinho"}), 500
        
        # Retorna o estado atualizado do carrinho
        cart_summary = cart_service.get_cart_summary(user_id)
        return jsonify({
            "message": message,
            "cart": cart_summary
        }), 201
        
    except Exception as e:
        print(f"Erro ao adicionar item ao carrinho: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500


@cart_bp.route('/me/items/<int:cart_item_id>', methods=['PUT'])
@jwt_required()
def update_cart_item_route(cart_item_id):
    """
    Fluxo 3: Modificar Item do Carrinho
    Atualiza quantidade ou extras de um item específico
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        
        quantity = data.get('quantity')
        extras = data.get('extras')
        notes = data.get('notes')
        
        # Validações
        if quantity is not None and (not isinstance(quantity, int) or quantity <= 0):
            return jsonify({"error": "quantity deve ser um número inteiro positivo"}), 400
        
        if extras is not None:
            if not isinstance(extras, list):
                return jsonify({"error": "extras deve ser uma lista"}), 400
            
            # Valida extras
            for extra in extras:
                if not isinstance(extra, dict):
                    return jsonify({"error": "Cada extra deve ser um objeto"}), 400
                
                if not extra.get('ingredient_id'):
                    return jsonify({"error": "ingredient_id é obrigatório em cada extra"}), 400
                
                extra_quantity = extra.get('quantity', 1)
                if not isinstance(extra_quantity, int) or extra_quantity <= 0:
                    return jsonify({"error": "quantity do extra deve ser um número inteiro positivo"}), 400
        
        # Verifica se pelo menos um campo foi fornecido
        if quantity is None and extras is None:
            return jsonify({"error": "Pelo menos um campo (quantity ou extras) deve ser fornecido"}), 400
        
        # Atualiza item do carrinho
        success, error_code, message = cart_service.update_cart_item(user_id, cart_item_id, quantity, extras, notes)
        
        if not success:
            if error_code == "ITEM_NOT_FOUND":
                return jsonify({"error": message}), 404
            elif error_code == "INVALID_QUANTITY":
                return jsonify({"error": message}), 400
            elif error_code == "DATABASE_ERROR":
                return jsonify({"error": message}), 500
            else:
                return jsonify({"error": "Erro ao atualizar item do carrinho"}), 500
        
        # Retorna o estado atualizado do carrinho
        cart_summary = cart_service.get_cart_summary(user_id)
        return jsonify({
            "message": message,
            "cart": cart_summary
        }), 200
        
    except Exception as e:
        print(f"Erro ao atualizar item do carrinho: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500


@cart_bp.route('/me/items/<int:cart_item_id>', methods=['DELETE'])
@jwt_required()
def remove_cart_item_route(cart_item_id):
    """
    Fluxo 3: Remover Item do Carrinho
    Remove um item específico do carrinho
    """
    try:
        user_id = get_jwt_identity()
        
        # Remove item do carrinho
        success, error_code, message = cart_service.remove_cart_item(user_id, cart_item_id)
        
        if not success:
            if error_code == "ITEM_NOT_FOUND":
                return jsonify({"error": message}), 404
            elif error_code == "DATABASE_ERROR":
                return jsonify({"error": message}), 500
            else:
                return jsonify({"error": "Erro ao remover item do carrinho"}), 500
        
        # Retorna o estado atualizado do carrinho
        cart_summary = cart_service.get_cart_summary(user_id)
        return jsonify({
            "message": message,
            "cart": cart_summary
        }), 200
        
    except Exception as e:
        print(f"Erro ao remover item do carrinho: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500


@cart_bp.route('/me/clear', methods=['DELETE'])
@jwt_required()
def clear_cart_route():
    """
    Limpa todo o carrinho do usuário
    """
    try:
        user_id = get_jwt_identity()
        
        # Limpa carrinho
        success, error_code, message = cart_service.clear_cart(user_id)
        
        if not success:
            if error_code == "DATABASE_ERROR":
                return jsonify({"error": message}), 500
            else:
                return jsonify({"error": "Erro ao limpar carrinho"}), 500
        
        return jsonify({"message": message}), 200
        
    except Exception as e:
        print(f"Erro ao limpar carrinho: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500


@cart_bp.route('/me/summary', methods=['GET'])
@jwt_required()
def get_cart_summary_route():
    """
    Retorna apenas o resumo do carrinho (sem detalhes dos itens)
    Útil para mostrar totais em headers ou componentes pequenos
    """
    try:
        user_id = get_jwt_identity()
        cart_summary = cart_service.get_cart_summary(user_id)
        
        if not cart_summary:
            return jsonify({"error": "Erro ao acessar carrinho"}), 500
        
        # Retorna apenas o resumo
        return jsonify({
            "summary": cart_summary["summary"],
            "cart_id": cart_summary["cart"]["id"]
        }), 200
        
    except Exception as e:
        print(f"Erro ao buscar resumo do carrinho: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500


@cart_bp.route('/me/validate', methods=['GET'])
@jwt_required()
def validate_cart_route():
    """
    Valida o carrinho do usuário: disponibilidade e regras básicas.
    Retorna alerts presentes no summary atual.
    """
    try:
        user_id = get_jwt_identity()
        cart_summary = cart_service.get_cart_summary(user_id)
        if not cart_summary:
            return jsonify({"error": "Erro ao acessar carrinho"}), 500
        return jsonify({
            "availability_alerts": cart_summary["summary"].get("availability_alerts", [])
        }), 200
    except Exception as e:
        print(f"Erro ao validar carrinho: {e}")
        return jsonify({"error": "Erro interno do servidor"}), 500
