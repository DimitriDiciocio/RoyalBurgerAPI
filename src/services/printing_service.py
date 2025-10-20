import os
import tempfile
import subprocess
from datetime import datetime

from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont
try:
    import win32print
    import win32ui
    from PIL import ImageWin
except Exception:
    win32print = None
    win32ui = None
    ImageWin = None

from ..config import Config


class KitchenTicketPDF(FPDF):
    def header(self):
        # Cabeçalho minimalista; conteúdo principal é adicionado pela função geradora
        pass

    def footer(self):
        # Sem rodapé para ticket de cozinha
        pass


def _write_item_block(pdf: FPDF, item, index: int) -> None:
    quantity = item.get('quantity', 1)
    name = item.get('product_name') or item.get('name') or 'Item'
    # Linha do item principal
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, f"{quantity}x  {name}", ln=1)

    # Extras e remoções
    pdf.set_font('Helvetica', '', 12)
    extras = item.get('extras', []) or []
    removals = item.get('removals', []) or []
    for extra in extras:
        extra_name = extra.get('name') or extra.get('ingredient_name') or 'Extra'
        pdf.cell(0, 7, f"   + {extra_name}", ln=1)
    for rem in removals:
        rem_name = rem.get('name') or rem.get('ingredient_name') or 'Remoção'
        pdf.cell(0, 7, f"   - SEM {rem_name}", ln=1)

    # Linha divisória
    pdf.set_draw_color(200, 200, 200)
    y = pdf.get_y()
    pdf.line(10, y, 200, y)
    pdf.ln(2)


def generate_kitchen_ticket_pdf(order_data: dict) -> bytes:
    """
    Gera o PDF do ticket da cozinha em memória.
    order_data esperado:
      {
        "id": int,
        "created_at": "YYYY-MM-DD HH:MM:SS",
        "order_type": "Delivery"|"Local",
        "notes": str,
        "items": [
          {"quantity": int, "product_name": str, "extras": [{name: str}], "removals": [{name: str}]} ...
        ]
      }
    """
    pdf = KitchenTicketPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()

    # Título com número do pedido
    order_id = order_data.get('id') or order_data.get('order_id')
    order_type = order_data.get('order_type', 'Delivery')
    created_at_str = order_data.get('created_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    pdf.set_font('Helvetica', 'B', 28)
    pdf.cell(0, 14, f"PEDIDO #{order_id}", ln=1)

    pdf.set_font('Helvetica', '', 14)
    pdf.cell(0, 8, f"Tipo: {order_type}", ln=1)
    pdf.cell(0, 8, f"Hora: {created_at_str}", ln=1)

    pdf.ln(4)
    pdf.set_draw_color(0, 0, 0)
    y = pdf.get_y()
    pdf.line(10, y, 200, y)
    pdf.ln(4)

    # Itens
    items = order_data.get('items', []) or []
    for idx, item in enumerate(items, start=1):
        _write_item_block(pdf, item, idx)

    # Notas do cliente
    notes = order_data.get('notes') or ''
    if notes.strip():
        pdf.ln(2)
        pdf.set_font('Helvetica', 'B', 14)
        pdf.cell(0, 10, "Observações do Cliente:", ln=1)
        pdf.set_font('Helvetica', '', 12)
        pdf.multi_cell(0, 7, notes.strip())

    # Retorna bytes
    return pdf.output(dest='S').encode('latin1')


def generate_kitchen_ticket_image(order_data: dict, width_px: int = 800) -> Image.Image:
    """
    Gera imagem do ticket (para impressão nativa no Windows sem aplicativos externos).
    """
    # Configuração básica de layout
    padding = 24
    line_gap = 10
    x = padding
    y = padding

    # Fontes
    try:
        title_font = ImageFont.truetype("arial.ttf", 48)
        subtitle_font = ImageFont.truetype("arial.ttf", 28)
        text_bold = ImageFont.truetype("arial.ttf", 32)
        text_font = ImageFont.truetype("arial.ttf", 26)
    except Exception:
        # Fallback para fontes padrão do PIL se TTF não disponível
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
        text_bold = ImageFont.load_default()
        text_font = ImageFont.load_default()

    # Primeiro calcula altura necessária (layout de uma coluna)
    temp_img = Image.new('L', (width_px, 10000), color=255)
    temp_draw = ImageDraw.Draw(temp_img)

    order_id = order_data.get('id') or order_data.get('order_id')
    order_type = order_data.get('order_type', 'Delivery')
    created_at_str = order_data.get('created_at') or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    items = order_data.get('items', []) or []
    notes = (order_data.get('notes') or '').strip()

    def draw_line(d: ImageDraw.ImageDraw, y_pos: int):
        d.line([(padding, y_pos), (width_px - padding, y_pos)], fill=0, width=2)

    # Título
    _, _, w, h = temp_draw.textbbox((x, y), f"PEDIDO #{order_id}", font=title_font)
    y += h + line_gap
    # Subtítulos
    for sub in [f"Tipo: {order_type}", f"Hora: {created_at_str}"]:
        _, _, w, h = temp_draw.textbbox((x, y), sub, font=subtitle_font)
        y += h + line_gap

    y += 6
    y += 2  # linha horizontal

    # Itens
    for item in items:
        quantity = item.get('quantity', 1)
        name = item.get('product_name') or item.get('name') or 'Item'
        # Principal
        _, _, w, h = temp_draw.textbbox((x, y), f"{quantity}x  {name}", font=text_bold)
        y += h + 2
        # Extras
        for extra in (item.get('extras') or []):
            extra_name = extra.get('name') or extra.get('ingredient_name') or 'Extra'
            _, _, w, h = temp_draw.textbbox((x, y), f"   + {extra_name}", font=text_font)
            y += h + 2
        # Remoções
        for rem in (item.get('removals') or []):
            rem_name = rem.get('name') or rem.get('ingredient_name') or 'Remoção'
            _, _, w, h = temp_draw.textbbox((x, y), f"   - SEM {rem_name}", font=text_font)
            y += h + 2
        y += 8
        y += 2  # linha horizontal

    # Observações
    if notes:
        _, _, w, h = temp_draw.textbbox((x, y), "Observações do Cliente:", font=text_bold)
        y += h + 4
        # Wrap simples por quebra automática do PIL via multiline_textbbox
        _, _, w, h = temp_draw.multiline_textbbox((x, y), notes, font=text_font, spacing=4)
        y += h + 6

    height_px = y + padding

    # Render final
    img = Image.new('L', (width_px, height_px), color=255)
    draw = ImageDraw.Draw(img)
    y = padding
    draw.text((x, y), f"PEDIDO #{order_id}", font=title_font, fill=0)
    _, _, _, h = draw.textbbox((x, y), f"PEDIDO #{order_id}", font=title_font)
    y += h + line_gap
    for sub in [f"Tipo: {order_type}", f"Hora: {created_at_str}"]:
        draw.text((x, y), sub, font=subtitle_font, fill=0)
        _, _, _, h = draw.textbbox((x, y), sub, font=subtitle_font)
        y += h + line_gap
    # linha
    draw.line([(padding, y), (width_px - padding, y)], fill=0, width=2)
    y += 8

    for item in items:
        quantity = item.get('quantity', 1)
        name = item.get('product_name') or item.get('name') or 'Item'
        draw.text((x, y), f"{quantity}x  {name}", font=text_bold, fill=0)
        _, _, _, h = draw.textbbox((x, y), f"{quantity}x  {name}", font=text_bold)
        y += h + 2
        for extra in (item.get('extras') or []):
            extra_name = extra.get('name') or extra.get('ingredient_name') or 'Extra'
            draw.text((x, y), f"   + {extra_name}", font=text_font, fill=0)
            _, _, _, h = draw.textbbox((x, y), f"   + {extra_name}", font=text_font)
            y += h + 2
        for rem in (item.get('removals') or []):
            rem_name = rem.get('name') or rem.get('ingredient_name') or 'Remoção'
            draw.text((x, y), f"   - SEM {rem_name}", font=text_font, fill=0)
            _, _, _, h = draw.textbbox((x, y), f"   - SEM {rem_name}", font=text_font)
            y += h + 2
        # linha
        draw.line([(padding, y), (width_px - padding, y)], fill=0, width=1)
        y += 8

    if notes:
        draw.text((x, y), "Observações do Cliente:", font=text_bold, fill=0)
        _, _, _, h = draw.textbbox((x, y), "Observações do Cliente:", font=text_bold)
        y += h + 4
        draw.multiline_text((x, y), notes, font=text_font, fill=0, spacing=4)

    return img


def _print_with_sumatra(pdf_path: str, printer_name: str, timeout_sec: int) -> tuple:
    exe = Config.SUMATRA_PATH
    if not os.path.isfile(exe):
        return (False, None, f"SumatraPDF não encontrado em {exe}")
    # -silent evita diálogos; -print-to especifica impressora
    cmd = [exe, '-print-to', printer_name, '-silent', pdf_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout_sec)
        if proc.returncode == 0:
            return (True, None, 'Impressão enviada com sucesso')
        return (False, None, f"Falha ao imprimir (rc={proc.returncode}): {proc.stderr.decode(errors='ignore')}")
    except subprocess.TimeoutExpired:
        return (False, None, 'Timeout ao enviar impressão para SumatraPDF')
    except Exception as e:
        return (False, None, f"Erro ao chamar SumatraPDF: {e}")


def _print_with_lpr(pdf_path: str, printer_name: str, timeout_sec: int) -> tuple:
    cmd = ['lpr']
    if printer_name:
        cmd += ['-P', printer_name]
    cmd += [pdf_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout_sec)
        if proc.returncode == 0:
            return (True, None, 'Impressão enviada com sucesso')
        return (False, None, f"Falha ao imprimir (rc={proc.returncode}): {proc.stderr.decode(errors='ignore')}")
    except subprocess.TimeoutExpired:
        return (False, None, 'Timeout ao enviar impressão com lpr')
    except Exception as e:
        return (False, None, f"Erro ao chamar lpr: {e}")


def print_pdf_bytes(pdf_bytes: bytes, job_name: str = 'RoyalBurger-Kitchen') -> dict:
    """
    Envia bytes de PDF à impressora conforme backend configurado.
    Retorna dict {status: 'printed'|'error', job_id: None|str, message: str}
    """
    backend = (Config.PRINT_BACKEND or 'windows_sumatra').lower()
    printer_name = Config.PRINTER_NAME
    timeout_sec = Config.PRINT_TIMEOUT_SEC

    # Salva em arquivo temporário
    with tempfile.NamedTemporaryFile(prefix='rb_kitchen_', suffix='.pdf', delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        pdf_path = tmp.name

    try:
        if backend == 'windows_sumatra':
            ok, job_id, msg = _print_with_sumatra(pdf_path, printer_name, timeout_sec)
        elif backend == 'linux_lpr':
            ok, job_id, msg = _print_with_lpr(pdf_path, printer_name, timeout_sec)
        else:
            ok, job_id, msg = (False, None, f"PRINT_BACKEND desconhecido: {backend}")

        return {
            'status': 'printed' if ok else 'error',
            'job_id': job_id,
            'message': msg
        }
    finally:
        try:
            os.remove(pdf_path)
        except Exception:
            pass


def print_image_windows(img: Image.Image, job_name: str = 'RoyalBurger-Kitchen') -> dict:
    if win32print is None or win32ui is None or ImageWin is None:
        return {"status": "error", "job_id": None, "message": "pywin32 indisponível para impressão"}
    printer_name = Config.PRINTER_NAME or win32print.GetDefaultPrinter()
    try:
        hdc = win32ui.CreateDC()
        hdc.CreatePrinterDC(printer_name)
        printable_area = hdc.GetDeviceCaps(8), hdc.GetDeviceCaps(10)  # HORZRES, VERTRES
        # Dimensiona imagem para área imprimível preservando proporção
        img_width, img_height = img.size
        ratio = min(printable_area[0] / img_width, printable_area[1] / img_height)
        target_size = (int(img_width * ratio), int(img_height * ratio))
        img_resized = img.resize(target_size)

        dib = ImageWin.Dib(img_resized.convert('RGB'))
        hdc.StartDoc(job_name)
        hdc.StartPage()
        # Coordenadas destino (canto superior esquerdo)
        dib.draw(hdc.GetHandleOutput(), (0, 0, target_size[0], target_size[1]))
        hdc.EndPage()
        hdc.EndDoc()
        hdc.DeleteDC()
        return {"status": "printed", "job_id": None, "message": "Impressão enviada com sucesso"}
    except Exception as e:
        return {"status": "error", "job_id": None, "message": f"Erro ao imprimir: {e}"}


def print_kitchen_ticket(order_data: dict) -> dict:
    """
    Imprime o ticket de cozinha sem aplicativos externos.
    - Windows: gera imagem e imprime via GDI/pywin32
    - Linux: se necessário, usa lpr para imagem (futuro)
    """
    backend = (Config.PRINT_BACKEND or 'windows_pil').lower()
    if backend in ('windows_pil', 'windows'):
        img = generate_kitchen_ticket_image(order_data)
        return print_image_windows(img, job_name=f"Kitchen-{order_data.get('id') or order_data.get('order_id')}")
    # Fallback: gerar PDF e tentar lpr (sem app externo adicional)
    if backend == 'linux_lpr':
        pdf_bytes = generate_kitchen_ticket_pdf(order_data)
        with tempfile.NamedTemporaryFile(prefix='rb_kitchen_', suffix='.pdf', delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp.flush()
            pdf_path = tmp.name
        try:
            ok, job_id, msg = _print_with_lpr(pdf_path, Config.PRINTER_NAME, Config.PRINT_TIMEOUT_SEC)
            return {"status": "printed" if ok else "error", "job_id": job_id, "message": msg}
        finally:
            try:
                os.remove(pdf_path)
            except Exception:
                pass
    return {"status": "error", "job_id": None, "message": f"PRINT_BACKEND não suportado: {backend}"}

