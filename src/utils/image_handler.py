import os
import uuid
from werkzeug.utils import secure_filename
from PIL import Image
import io

# Configurações de upload
UPLOAD_FOLDER = 'uploads'
PRODUCTS_FOLDER = 'products'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_IMAGE_DIMENSIONS = (1920, 1080)  # Máximo 1920x1080

def allowed_file(filename):
    """Verifica se o arquivo tem uma extensão permitida"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_image_file(file):
    """
    Valida o arquivo de imagem
    Retorna: (is_valid: bool, error_message: str)
    """
    if not file or not file.filename:
        return False, "Nenhum arquivo foi enviado"
    
    if not allowed_file(file.filename):
        return False, f"Tipo de arquivo não permitido. Tipos aceitos: {', '.join(ALLOWED_EXTENSIONS)}"
    
    # Verifica o tamanho do arquivo
    file.seek(0, 2)  # Move para o final do arquivo
    file_size = file.tell()
    file.seek(0)  # Volta para o início
    
    if file_size > MAX_FILE_SIZE:
        return False, f"Arquivo muito grande. Tamanho máximo: {MAX_FILE_SIZE // (1024*1024)}MB"
    
    # Verifica se é uma imagem válida
    try:
        with Image.open(file) as img:
            # Verifica as dimensões
            if img.size[0] > MAX_IMAGE_DIMENSIONS[0] or img.size[1] > MAX_IMAGE_DIMENSIONS[1]:
                return False, f"Imagem muito grande. Dimensões máximas: {MAX_IMAGE_DIMENSIONS[0]}x{MAX_IMAGE_DIMENSIONS[1]}"
            
            # Verifica se é uma imagem válida
            img.verify()
        
        file.seek(0)  # Volta para o início após verificação
        return True, "Arquivo válido"
        
    except Exception as e:
        return False, "Arquivo não é uma imagem válida"

def save_product_image(file, product_id):
    """
    Salva a imagem do produto
    Retorna: (success: bool, file_path: str, error_message: str)
    """
    try:
        # Valida o arquivo
        is_valid, error_msg = validate_image_file(file)
        if not is_valid:
            return False, None, error_msg
        
        # Cria o diretório se não existir
        upload_dir = os.path.join(UPLOAD_FOLDER, PRODUCTS_FOLDER)
        os.makedirs(upload_dir, exist_ok=True)
        
        # Gera nome do arquivo: {product_id}.jpeg
        filename = f"{product_id}.jpeg"
        file_path = os.path.join(upload_dir, filename)
        
        # Processa e salva a imagem
        with Image.open(file) as img:
            # Converte para RGB se necessário (para JPEG)
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            # Redimensiona se necessário (mantém proporção)
            img.thumbnail(MAX_IMAGE_DIMENSIONS, Image.Resampling.LANCZOS)
            
            # Salva como JPEG
            img.save(file_path, 'JPEG', quality=85, optimize=True)
        
        return True, file_path, "Imagem salva com sucesso"
        
    except Exception as e:
        return False, None, f"Erro ao salvar imagem: {str(e)}"

def delete_product_image(product_id):
    """
    Remove a imagem do produto
    Retorna: (success: bool, error_message: str)
    """
    try:
        file_path = os.path.join(UPLOAD_FOLDER, PRODUCTS_FOLDER, f"{product_id}.jpeg")
        
        if os.path.exists(file_path):
            os.remove(file_path)
            return True, "Imagem removida com sucesso"
        else:
            return True, "Imagem não encontrada (já removida)"
            
    except Exception as e:
        return False, f"Erro ao remover imagem: {str(e)}"

def get_product_image_path(product_id):
    """
    Retorna o caminho da imagem do produto se existir
    """
    file_path = os.path.join(UPLOAD_FOLDER, PRODUCTS_FOLDER, f"{product_id}.jpeg")
    if os.path.exists(file_path):
        return file_path
    return None

def get_product_image_url(product_id):
    """
    Retorna a URL da imagem do produto se existir
    """
    file_path = get_product_image_path(product_id)
    if file_path:
        return f"/uploads/products/{product_id}.jpeg"
    return None
