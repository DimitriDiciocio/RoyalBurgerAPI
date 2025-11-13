from flask import Blueprint, request, jsonify
import logging
from ..services import cart_service
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request

cart_bp = Blueprint('cart', __name__)
logger = logging.getLogger(__name__)

def _validate_extras(extras):
    """Valida extras de forma centralizada"""
    if not isinstance(extras, list):
        return False, "extras deve ser uma lista"
    
    for extra in extras:
        if not isinstance(extra, dict):
            return False, "Cada extra deve ser um objeto"
        if not extra.get('ingredient_id'):
            return False, "ingredient_id é obrigatório em cada extra"
        extra_quantity = extra.get('quantity', 1)
        if not isinstance(extra_quantity, int) or extra_quantity <= 0:
            return False, "quantity do extra deve ser um número inteiro positivo"
    
    return True, None

def _validate_guest_cart_id(guest_cart_id):
    """Valida guest_cart_id"""
    if guest_cart_id is not None:
        try:
            int(guest_cart_id)
        except (ValueError, TypeError):
            return False, "guest_cart_id deve ser um número inteiro válido"
    return True, None

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
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao buscar carrinho: {e}", exc_info=True)
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
        # ALTERAÇÃO: Removida duplicação de atribuição de base_modifications
        base_modifications = data.get('base_modifications', [])
        
        # Validações básicas
        if not product_id:
            return jsonify({"error": "product_id é obrigatório"}), 400
        
        if not isinstance(quantity, int) or quantity <= 0:
            return jsonify({"error": "quantity deve ser um número inteiro positivo"}), 400
        
        # Valida extras
        is_valid, error_msg = _validate_extras(extras)
        if not is_valid:
            return jsonify({"error": error_msg}), 400
        
        # Adiciona item ao carrinho
        success, error_code, message = cart_service.add_item_to_cart(user_id, product_id, quantity, extras, notes, base_modifications)
        
        if not success:
            status_code = 404 if error_code == "PRODUCT_NOT_FOUND" else 500
            return jsonify({"error": message}), status_code
        
        # Retorna o estado atualizado do carrinho
        cart_summary = cart_service.get_cart_summary(user_id)
        return jsonify({
            "message": message,
            "cart": cart_summary
        }), 201
        
    except Exception as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao adicionar item ao carrinho: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


# Endpoints com JWT opcional para fluxo "Smart Add" (convidado ou autenticado)
@cart_bp.route('/items', methods=['POST'])
def smart_add_item_route():
    """
    Adiciona item ao carrinho com suporte a convidado.
    Se autenticado: ignora guest_cart_id e adiciona no carrinho do usuário.
    Se não autenticado e guest_cart_id presente: adiciona no carrinho convidado.
    Se não autenticado e sem guest_cart_id: cria carrinho convidado e adiciona.
    
    Resposta sempre inclui cart_id para sincronização com localStorage.
    """
    try:
        data = request.get_json() or {}

        product_id = data.get('product_id')
        quantity = data.get('quantity', 1)
        extras = data.get('extras', [])
        notes = data.get('notes')
        guest_cart_id = data.get('guest_cart_id')
        base_modifications = data.get('base_modifications', [])

        # Validações básicas
        if not product_id:
            return jsonify({"error": "product_id é obrigatório"}), 400
        
        if not isinstance(quantity, int) or quantity <= 0:
            return jsonify({"error": "quantity deve ser um número inteiro positivo"}), 400
        
        # Valida extras
        is_valid, error_msg = _validate_extras(extras)
        if not is_valid:
            return jsonify({"error": error_msg}), 400
        
        # Valida guest_cart_id
        is_valid, error_msg = _validate_guest_cart_id(guest_cart_id)
        if not is_valid:
            return jsonify({"error": error_msg}), 400

        # Tenta validar JWT de forma opcional
        user_id = None
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
        except Exception:
            user_id = None

        if user_id:
            success, error_code, message = cart_service.add_item_to_cart(user_id, product_id, quantity, extras, notes, base_modifications)
            if not success:
                # NOVO: Retorna status_code correto para diferentes tipos de erro
                if error_code == "PRODUCT_NOT_FOUND":
                    status_code = 404
                elif error_code == "INSUFFICIENT_STOCK":
                    status_code = 422  # Unprocessable Entity - erro de validação de estoque
                else:
                    status_code = 500
                return jsonify({"error": message or "Erro ao adicionar item"}), status_code
            
            cart_summary = cart_service.get_cart_summary(user_id)
            return jsonify({
                "message": message, 
                "cart": cart_summary,
                "cart_id": cart_summary["cart"]["id"],
                "is_authenticated": True
            }), 201

        # Convidado com guest_cart_id informado
        if guest_cart_id:
            success, error_code, message = cart_service.add_item_to_cart_by_cart_id(guest_cart_id, product_id, quantity, extras, notes, base_modifications)
            if not success:
                # NOVO: Retorna status_code correto para diferentes tipos de erro
                if error_code in ("PRODUCT_NOT_FOUND", "CART_NOT_FOUND"):
                    status_code = 404
                elif error_code == "INSUFFICIENT_STOCK":
                    status_code = 422  # Unprocessable Entity - erro de validação de estoque
                else:
                    status_code = 500
                return jsonify({"error": message or "Erro ao adicionar item"}), status_code
            
            cart_summary = cart_service.get_cart_summary_by_cart_id(guest_cart_id)
            return jsonify({
                "message": message, 
                "cart": cart_summary,
                "cart_id": guest_cart_id,
                "is_authenticated": False
            }), 201

        # Convidado sem guest_cart_id: cria carrinho e adiciona, retornando o novo ID
        guest_cart = cart_service.create_guest_cart()
        if not guest_cart:
            return jsonify({"error": "Não foi possível criar carrinho"}), 500
        new_cart_id = guest_cart["id"]
        success, error_code, message = cart_service.add_item_to_cart_by_cart_id(new_cart_id, product_id, quantity, extras, notes, base_modifications)
        if not success:
            # NOVO: Retorna status_code correto para diferentes tipos de erro
            if error_code == "INSUFFICIENT_STOCK":
                status_code = 422  # Unprocessable Entity - erro de validação de estoque
            else:
                status_code = 500
            return jsonify({"error": message or "Erro ao adicionar item"}), status_code
        cart_summary = cart_service.get_cart_summary_by_cart_id(new_cart_id)
        return jsonify({
            "message": message, 
            "cart_id": new_cart_id, 
            "cart": cart_summary,
            "is_authenticated": False
        }), 201
    except Exception as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro no smart add: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@cart_bp.route('/items/<int:cart_item_id>', methods=['PUT'])
def smart_update_item_route(cart_item_id):
    """
    Atualiza item do carrinho com suporte a convidado via guest_cart_id.
    """
    try:
        data = request.get_json() or {}
        quantity = data.get('quantity')
        extras = data.get('extras')
        notes = data.get('notes')
        # ALTERAÇÃO: Removida duplicação de atribuição de base_modifications
        base_modifications = data.get('base_modifications')
        guest_cart_id = data.get('guest_cart_id')

        if quantity is not None and (not isinstance(quantity, int) or quantity <= 0):
            return jsonify({"error": "quantity deve ser um número inteiro positivo"}), 400
        if extras is not None and not isinstance(extras, list):
            return jsonify({"error": "extras deve ser uma lista"}), 400
        if quantity is None and extras is None and notes is None and base_modifications is None:
            return jsonify({"error": "Nada para atualizar"}), 400

        user_id = None
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
        except Exception:
            user_id = None

        if user_id:
            success, error_code, message = cart_service.update_cart_item(user_id, cart_item_id, quantity, extras, notes, base_modifications)
            if not success:
                # NOVO: Retorna status_code correto para diferentes tipos de erro
                if error_code == "ITEM_NOT_FOUND":
                    status = 404
                elif error_code == "INVALID_QUANTITY":
                    status = 400
                elif error_code == "INSUFFICIENT_STOCK":
                    status = 422  # Unprocessable Entity - erro de validação de estoque
                else:
                    status = 500
                return jsonify({"error": message}), status
            cart_summary = cart_service.get_cart_summary(user_id)
            return jsonify({
                "message": message, 
                "cart": cart_summary,
                "cart_id": cart_summary["cart"]["id"],
                "is_authenticated": True
            }), 200

        if not guest_cart_id:
            return jsonify({"error": "guest_cart_id é obrigatório para convidados"}), 400
        success, error_code, message = cart_service.update_cart_item_by_cart(guest_cart_id, cart_item_id, quantity, extras, notes, base_modifications)
        if not success:
            # NOVO: Retorna status_code correto para diferentes tipos de erro
            if error_code == "ITEM_NOT_FOUND":
                status = 404
            elif error_code == "INVALID_QUANTITY":
                status = 400
            elif error_code == "INSUFFICIENT_STOCK":
                status = 422  # Unprocessable Entity - erro de validação de estoque
            else:
                status = 500
            return jsonify({"error": message}), status
        cart_summary = cart_service.get_cart_summary_by_cart_id(guest_cart_id)
        return jsonify({
            "message": message, 
            "cart": cart_summary,
            "cart_id": guest_cart_id,
            "is_authenticated": False
        }), 200
    except Exception as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao atualizar item (smart): {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@cart_bp.route('/items/<int:cart_item_id>', methods=['DELETE'])
def smart_remove_item_route(cart_item_id):
    """
    Remove item do carrinho com suporte a convidado via guest_cart_id.
    """
    try:
        data = request.get_json() or {}
        guest_cart_id = data.get('guest_cart_id')

        user_id = None
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
        except Exception:
            user_id = None

        if user_id:
            success, error_code, message = cart_service.remove_cart_item(user_id, cart_item_id)
            if not success:
                status = 404 if error_code == "ITEM_NOT_FOUND" else 500
                return jsonify({"error": message}), status
            cart_summary = cart_service.get_cart_summary(user_id)
            return jsonify({
                "message": message, 
                "cart": cart_summary,
                "cart_id": cart_summary["cart"]["id"],
                "is_authenticated": True
            }), 200

        if not guest_cart_id:
            return jsonify({"error": "guest_cart_id é obrigatório para convidados"}), 400
        success, error_code, message = cart_service.remove_cart_item_by_cart(guest_cart_id, cart_item_id)
        if not success:
            status = 404 if error_code == "ITEM_NOT_FOUND" else 500
            return jsonify({"error": message}), status
        cart_summary = cart_service.get_cart_summary_by_cart_id(guest_cart_id)
        return jsonify({
            "message": message, 
            "cart": cart_summary,
            "cart_id": guest_cart_id,
            "is_authenticated": False
        }), 200
    except Exception as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao remover item (smart): {e}", exc_info=True)
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
        base_modifications = data.get('base_modifications')
        
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
        if quantity is None and extras is None and base_modifications is None and notes is None:
            return jsonify({"error": "Pelo menos um campo (quantity, extras, notes ou base_modifications) deve ser fornecido"}), 400
        
        # Atualiza item do carrinho
        success, error_code, message = cart_service.update_cart_item(user_id, cart_item_id, quantity, extras, notes, base_modifications)
        
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
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao atualizar item do carrinho: {e}", exc_info=True)
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
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao remover item do carrinho: {e}", exc_info=True)
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
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao limpar carrinho: {e}", exc_info=True)
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
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao buscar resumo do carrinho: {e}", exc_info=True)
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
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao validar carrinho: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@cart_bp.route('/guest/<int:cart_id>', methods=['GET'])
def get_guest_cart_route(cart_id):
    """
    Busca carrinho de convidado por ID.
    Útil para sincronizar dados do localStorage com o servidor.
    """
    try:
        cart_summary = cart_service.get_cart_summary_by_cart_id(cart_id)
        if not cart_summary:
            return jsonify({"error": "Carrinho não encontrado"}), 404
        
        return jsonify({
            "cart": cart_summary,
            "cart_id": cart_id,
            "is_authenticated": False
        }), 200
    except Exception as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao buscar carrinho de convidado: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@cart_bp.route('/guest/<int:cart_id>/validate', methods=['GET'])
def validate_guest_cart_route(cart_id):
    """
    Valida carrinho de convidado: disponibilidade e regras básicas.
    """
    try:
        cart_summary = cart_service.get_cart_summary_by_cart_id(cart_id)
        if not cart_summary:
            return jsonify({"error": "Carrinho não encontrado"}), 404
        
        return jsonify({
            "availability_alerts": cart_summary["summary"].get("availability_alerts", [])
        }), 200
    except Exception as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao validar carrinho de convidado: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@cart_bp.route('/guest/<int:cart_id>/validate-for-order', methods=['GET'])
def validate_guest_cart_for_order_route(cart_id):
    """
    Valida se carrinho de convidado pode ser convertido em pedido.
    Verifica disponibilidade completa de produtos e ingredientes.
    """
    try:
        is_valid, alerts, total_amount = cart_service.validate_guest_cart_for_order(cart_id)
        
        return jsonify({
            "is_valid": is_valid,
            "alerts": alerts,
            "total_amount": total_amount,
            "cart_id": cart_id
        }), 200
    except Exception as e:
        # ALTERAÇÃO: Substituído print() por logging estruturado
        logger.error(f"Erro ao validar carrinho para pedido: {e}", exc_info=True)
        return jsonify({"error": "Erro interno do servidor"}), 500


@cart_bp.route('/claim', methods=['POST'])
@jwt_required()
def claim_guest_cart_route():
    """
    Reivindica um carrinho de convidado para o usuário logado.
    Útil quando o usuário faz login e tem itens no localStorage.
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        guest_cart_id = data.get('guest_cart_id')
        
        if not guest_cart_id:
            return jsonify({"error": "guest_cart_id é obrigatório"}), 400
        
        success, error_code, message = cart_service.claim_guest_cart(guest_cart_id, user_id)
        
        if not success:
            if error_code == "CART_NOT_FOUND":
                return jsonify({"error": message}), 404
            elif error_code == "CONFLICT":
                return jsonify({"error": message}), 409
            else:
                return jsonify({"error": message or "Erro ao reivindicar carrinho"}), 500
        
        # Retorna o carrinho atualizado do usuário
        cart_summary = cart_service.get_cart_summary(user_id)
        return jsonify({
            "message": message,
            "cart": cart_summary,
            "cart_id": cart_summary["cart"]["id"],
            "is_authenticated": True
        }), 200
        
    except Exception as e:
        return jsonify({"error": "Erro interno do servidor"}), 500


@cart_bp.route('/sync', methods=['POST'])
@jwt_required()
def sync_cart_route():
    """
    Sincroniza itens do localStorage com o carrinho do usuário logado.
    Útil quando o usuário faz login e quer manter itens do localStorage.
    """
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        local_cart_items = data.get('items', [])
        
        if not local_cart_items:
            return jsonify({"error": "Nenhum item para sincronizar"}), 400
        
        # Adiciona cada item do localStorage ao carrinho do usuário
        synced_items = []
        errors = []
        
        for item in local_cart_items:
            product_id = item.get('product_id')
            quantity = item.get('quantity', 1)
            extras = item.get('extras', [])
            notes = item.get('notes', '')
            
            if not product_id:
                errors.append("Item sem product_id ignorado")
                continue
            
            success, error_code, message = cart_service.add_item_to_cart(
                user_id, product_id, quantity, extras, notes
            )
            
            if success:
                synced_items.append({
                    "product_id": product_id,
                    "quantity": quantity,
                    "extras": extras,
                    "notes": notes
                })
            else:
                errors.append(f"Erro ao adicionar produto {product_id}: {message}")
        
        # Retorna o carrinho atualizado
        cart_summary = cart_service.get_cart_summary(user_id)
        
        return jsonify({
            "message": f"Sincronização concluída. {len(synced_items)} itens adicionados.",
            "synced_items": synced_items,
            "errors": errors,
            "cart": cart_summary,
            "cart_id": cart_summary["cart"]["id"],
            "is_authenticated": True
        }), 200
        
    except Exception as e:
        return jsonify({"error": "Erro interno do servidor"}), 500
