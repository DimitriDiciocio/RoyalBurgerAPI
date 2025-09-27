from flask import Blueprint, jsonify, current_app  
from flask_swagger_ui import get_swaggerui_blueprint  
import yaml  
import os  

swagger_bp = Blueprint('swagger', __name__)  

SWAGGER_URL = '/api/docs'  
API_URL = '/api/docs/swagger.yaml'  

swaggerui_blueprint = get_swaggerui_blueprint(  
    SWAGGER_URL,
    API_URL,
    config={'app_name': "Royal Burger API Docs"}
)

@swagger_bp.route('/swagger.yaml')  
def serve_swagger_yaml():  
    try:  
        root_path = current_app.root_path  
        yaml_path = os.path.join(root_path, 'openapi', 'swagger.yaml')  
        with open(yaml_path, 'r', encoding='utf-8') as f:  
            swagger_spec = yaml.safe_load(f)  
        return jsonify(swagger_spec)  
    except FileNotFoundError:  
        return jsonify({"error": f"Arquivo swagger.yaml não encontrado: {yaml_path}"}), 404  
    except Exception as e:  
        return jsonify({"error": f"Não foi possível carregar o swagger.yaml: {e}"}), 500  
