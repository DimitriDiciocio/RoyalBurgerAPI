from flask import Blueprint, jsonify
from ..services import settings_service
from flask_jwt_extended import jwt_required

payment_bp = Blueprint('payments', __name__)

@payment_bp.route('/methods', methods=['GET'])
@jwt_required()
def get_payment_methods():
    """Retorna métodos de pagamento disponíveis e taxa de entrega atual"""
    try:
        # Busca configurações atuais do sistema
        settings = settings_service.get_all_settings()
        
        # Extrai taxa de entrega das configurações
        delivery_fee = settings.get('taxa_entrega') if settings else 0
        if delivery_fee is None:
            delivery_fee = 0
        
        return jsonify({
            "delivery_fee": float(delivery_fee),
            "payment_methods": [
                {
                    "id": "credit_card",
                    "name": "Cartão de Crédito",
                    "description": "Visa, Mastercard, Elo, Hipercard",
                    "fee": 0,
                    "available": True
                },
                {
                    "id": "debit_card",
                    "name": "Cartão de Débito",
                    "description": "Visa Débito, Mastercard Débito",
                    "fee": 0,
                    "available": True
                },
                {
                    "id": "pix",
                    "name": "PIX",
                    "description": "Pagamento instantâneo via PIX",
                    "fee": 0,
                    "available": True
                },
                {
                    "id": "cash",
                    "name": "Dinheiro",
                    "description": "Pagamento na entrega",
                    "fee": 0,
                    "available": True
                }
            ]
        }), 200
    except Exception as e:
        print(f"Erro ao buscar métodos de pagamento: {e}")
        return jsonify({
            "delivery_fee": 5.50,  # Valor padrão em caso de erro
            "payment_methods": [
                {
                    "id": "credit_card",
                    "name": "Cartão de Crédito",
                    "description": "Visa, Mastercard, Elo, Hipercard",
                    "fee": 0,
                    "available": True
                },
                {
                    "id": "debit_card",
                    "name": "Cartão de Débito",
                    "description": "Visa Débito, Mastercard Débito",
                    "fee": 0,
                    "available": True
                },
                {
                    "id": "pix",
                    "name": "PIX",
                    "description": "Pagamento instantâneo via PIX",
                    "fee": 0,
                    "available": True
                },
                {
                    "id": "cash",
                    "name": "Dinheiro",
                    "description": "Pagamento na entrega",
                    "fee": 0,
                    "available": True
                }
            ]
        }), 200

