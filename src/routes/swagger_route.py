from flask import Blueprint, jsonify, current_app  # importa Blueprint, jsonify e current_app do Flask
from flask_swagger_ui import get_swaggerui_blueprint  # importa integrador da Swagger UI
import yaml  # importa parser YAML
import os  # importa utilidades de sistema

swagger_bp = Blueprint('swagger', __name__)  # cria o blueprint do Swagger

SWAGGER_URL = '/api/docs'  # URL onde a UI será servida
API_URL = '/api/docs/swagger.yaml'  # URL do arquivo de especificação

swaggerui_blueprint = get_swaggerui_blueprint(  # configura a Swagger UI
    SWAGGER_URL,
    API_URL,
    config={'app_name': "Royal Burger API Docs"}
)

@swagger_bp.route('/swagger.yaml')  # rota para servir o arquivo swagger.yaml
def serve_swagger_yaml():  # função handler para servir swagger.yaml
    try:  # tenta carregar o arquivo
        root_path = current_app.root_path  # raiz do app
        yaml_path = os.path.join(root_path, 'openapi', 'swagger.yaml')  # caminho do YAML
        with open(yaml_path, 'r', encoding='utf-8') as f:  # abre arquivo
            swagger_spec = yaml.safe_load(f)  # carrega YAML
        return jsonify(swagger_spec)  # retorna JSON da especificação
    except FileNotFoundError:  # arquivo não encontrado
        return jsonify({"error": f"Arquivo swagger.yaml não encontrado: {yaml_path}"}), 404  # retorna 404
    except Exception as e:  # outros erros
        return jsonify({"error": f"Não foi possível carregar o swagger.yaml: {e}"}), 500  # retorna 500