from flask import Blueprint, request, jsonify
from ..services import promotion_service
from ..services.auth_service import require_role
from flask_jwt_extended import get_jwt_identity

promotion_bp = Blueprint('promotions', __name__)


@promotion_bp.route('/', methods=['POST'])
@require_role('admin', 'manager')
def create_promotion_route():
    """
    Cria uma nova promoção para um produto
    
    Body:
    {
        "product_id": 1,
        "discount_value": 5.00,  // ou discount_percentage: 10.0
        "conversion_method": "reais",  // ou "porcento"
        "expires_at": "2024-12-31T23:59:59"
    }
    """
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        return jsonify({"error": "Erro ao processar JSON"}), 400
    
    product_id = data.get('product_id')
    discount_value = data.get('discount_value')
    discount_percentage = data.get('discount_percentage')
    conversion_method = data.get('conversion_method', 'reais')
    expires_at = data.get('expires_at')
    
    # Validações básicas
    if not product_id:
        return jsonify({"error": "product_id é obrigatório"}), 400
    
    if conversion_method not in ['reais', 'porcento']:
        return jsonify({"error": "conversion_method deve ser 'reais' ou 'porcento'"}), 400
    
    if conversion_method == 'reais' and (discount_value is None or discount_value <= 0):
        return jsonify({"error": "discount_value é obrigatório e deve ser maior que zero quando conversion_method é 'reais'"}), 400
    
    if conversion_method == 'porcento' and (discount_percentage is None or discount_percentage <= 0):
        return jsonify({"error": "discount_percentage é obrigatório e deve ser maior que zero quando conversion_method é 'porcento'"}), 400
    
    if not expires_at:
        return jsonify({"error": "expires_at é obrigatório"}), 400
    
    # Obtém o ID do usuário logado
    try:
        user_id = int(get_jwt_identity()) if get_jwt_identity() else None
    except (ValueError, TypeError):
        user_id = None
    
    # Cria a promoção
    promotion, error_code, error_message = promotion_service.create_promotion(
        product_id=product_id,
        discount_value=discount_value,
        discount_percentage=discount_percentage,
        conversion_method=conversion_method,
        expires_at=expires_at,
        user_id=user_id
    )
    
    if promotion:
        return jsonify(promotion), 201
    
    if error_code == "PRODUCT_NOT_FOUND":
        return jsonify({"error": error_message}), 404
    if error_code == "PROMOTION_EXISTS":
        return jsonify({"error": error_message}), 409
    if error_code in ["INVALID_DISCOUNT", "INVALID_METHOD", "INVALID_DATE"]:
        return jsonify({"error": error_message}), 400
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": error_message}), 500
    
    return jsonify({"error": error_message or "Não foi possível criar a promoção"}), 500


@promotion_bp.route('/', methods=['GET'])
def list_promotions_route():
    """
    Lista todas as promoções ativas com detalhes dos produtos
    """
    # ALTERAÇÃO: Corrigido parsing de boolean - type=bool no Flask converte qualquer string não vazia para True
    # Usar comparação explícita com 'true' para garantir comportamento correto
    include_expired = request.args.get('include_expired', 'false').lower() == 'true'
    
    promotions = promotion_service.get_all_promotions(include_expired=include_expired)
    
    return jsonify({
        "items": promotions,
        "total": len(promotions)
    }), 200


@promotion_bp.route('/<int:promotion_id>', methods=['GET'])
def get_promotion_by_id_route(promotion_id):
    """
    Obtém uma promoção específica por ID
    """
    promotion = promotion_service.get_promotion_by_id(promotion_id)
    
    if promotion:
        return jsonify(promotion), 200
    
    return jsonify({"error": "Promoção não encontrada"}), 404


@promotion_bp.route('/product/<int:product_id>', methods=['GET'])
def get_promotion_by_product_id_route(product_id):
    """
    Obtém a promoção de um produto específico
    Query params:
        include_expired: Se True, inclui promoções expiradas (padrão: False)
    """
    # ALTERAÇÃO: Corrigido parsing de boolean - type=bool no Flask converte qualquer string não vazia para True
    # Usar comparação explícita com 'true' para garantir comportamento correto
    include_expired = request.args.get('include_expired', 'false').lower() == 'true'
    promotion = promotion_service.get_promotion_by_product_id(product_id, include_expired=include_expired)
    
    if promotion:
        return jsonify(promotion), 200
    
    return jsonify({"error": "Nenhuma promoção encontrada para este produto"}), 404


@promotion_bp.route('/<int:promotion_id>', methods=['PUT'])
@require_role('admin', 'manager')
def update_promotion_route(promotion_id):
    """
    Atualiza uma promoção existente
    
    Body (todos os campos são opcionais):
    {
        "discount_value": 10.00,
        "discount_percentage": 15.0,
        "conversion_method": "reais",  // ou "porcento"
        "expires_at": "2024-12-31T23:59:59"
    }
    """
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "JSON inválido ou vazio"}), 400
    except Exception as e:
        return jsonify({"error": "Erro ao processar JSON"}), 400
    
    # Valida conversion_method se fornecido
    conversion_method = data.get('conversion_method')
    if conversion_method and conversion_method not in ['reais', 'porcento']:
        return jsonify({"error": "conversion_method deve ser 'reais' ou 'porcento'"}), 400
    
    # Obtém o ID do usuário logado
    try:
        user_id = int(get_jwt_identity()) if get_jwt_identity() else None
    except (ValueError, TypeError):
        user_id = None
    
    # Atualiza a promoção
    success, error_code, error_message = promotion_service.update_promotion(
        promotion_id=promotion_id,
        update_data=data,
        user_id=user_id
    )
    
    if success:
        # Retorna a promoção atualizada
        promotion = promotion_service.get_promotion_by_id(promotion_id)
        return jsonify(promotion), 200
    
    if error_code == "PROMOTION_NOT_FOUND":
        return jsonify({"error": error_message}), 404
    if error_code == "PRODUCT_NOT_FOUND":
        return jsonify({"error": error_message}), 404
    if error_code in ["NO_VALID_FIELDS", "INVALID_DISCOUNT", "INVALID_DATE"]:
        return jsonify({"error": error_message}), 400
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": error_message}), 500
    
    return jsonify({"error": error_message or "Falha ao atualizar promoção"}), 500


@promotion_bp.route('/<int:promotion_id>', methods=['DELETE'])
@require_role('admin', 'manager')
def delete_promotion_route(promotion_id):
    """
    Remove uma promoção
    """
    success, error_code, error_message = promotion_service.delete_promotion(promotion_id)
    
    if success:
        return jsonify({"msg": error_message}), 200
    
    if error_code == "PROMOTION_NOT_FOUND":
        return jsonify({"error": error_message}), 404
    if error_code == "DATABASE_ERROR":
        return jsonify({"error": error_message}), 500
    
    return jsonify({"error": error_message or "Falha ao remover promoção"}), 500

