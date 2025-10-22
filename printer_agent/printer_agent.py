import time
import socketio
import configparser
import subprocess
import tempfile
import os
import socket

try:
    from escpos.printer import Usb, Network
except Exception:
    Usb = None
    Network = None


class RawNetworkPrinter:
    """Impressão ESC/POS direta via socket TCP (porta 9100)."""
    def __init__(self, host: str, port: int = 9100, timeout: float = 3.0):
        if not host:
            raise ValueError('Host da impressora de rede não configurado')
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None
        self._connect()
        self._initialize()

    def _connect(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect((self.host, self.port))
        self.sock = s

    def _send(self, data: bytes):
        if not self.sock:
            raise RuntimeError('Conexão com a impressora não está ativa')
        self.sock.sendall(data)

    def _initialize(self):
        # ESC @
        self._send(b"\x1b@")

    def set(self, align: str = 'left', bold: bool = False, double_height: bool = False, double_width: bool = False, inverse: bool = False):
        # Alinhamento: ESC a n (0=left,1=center,2=right)
        align_map = {'left': 0, 'center': 1, 'right': 2}
        n = align_map.get(align, 0)
        self._send(b"\x1b" + b"a" + bytes([n]))

        # Negrito: ESC E n (1 on, 0 off)
        self._send(b"\x1b" + b"E" + (b"\x01" if bold else b"\x00"))

        # Inverso: GS B n (1 on, 0 off)
        self._send(b"\x1d" + b"B" + (b"\x01" if inverse else b"\x00"))

        # Tamanho: GS ! n (bit 4 = altura x2, bit 5 = largura x2)
        size = 0
        if double_height:
            size |= 0x10
        if double_width:
            size |= 0x20
        self._send(b"\x1d" + b"!" + bytes([size]))

    def text(self, s: str):
        # Usa CP437 como default para maior compatibilidade
        data = s.encode('cp437', errors='replace')
        self._send(data)

    def ln(self, n: int = 1):
        self._send(b"\n" * max(1, n))

    def cut(self):
        # Full cut: GS V 66 0
        self._send(b"\x1dV\x42\x00")

    def close(self):
        try:
            if self.sock:
                self.sock.close()
        finally:
            self.sock = None


class WindowsSpoolPrinter:
    """Imprime texto via spooler do Windows usando o Notepad (sem dependências).
    Observação: imprime na impressora padrão do Windows.
    """
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('Modo windows disponível apenas no Windows')
        self._buffer = []

    def set(self, align: str = 'left', bold: bool = False, double_height: bool = False, double_width: bool = False, inverse: bool = False):
        # Spooler de texto simples: ignoramos estilos; apenas alinhamento central adiciona cabeçalho simples
        # O alinhamento será aproximado adicionando espaços quando necessário (omitido por simplicidade)
        pass

    def text(self, s: str):
        self._buffer.append(s)

    def ln(self, n: int = 1):
        self._buffer.append("\r\n" * max(1, n))

    def cut(self):
        # Em impressora comum, não há guilhotina; adiciona linhas em branco
        self._buffer.append("\r\n\r\n\r\n")

    def flush_and_print(self):
        content = ''.join(self._buffer)
        # Grava arquivo UTF-8 com BOM para preservar acentos no Notepad
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile('w', delete=False, suffix='.txt', encoding='utf-8-sig') as f:
                f.write(content)
                tmp_path = f.name
            # Imprime silenciosamente com Notepad
            subprocess.run(['notepad.exe', '/p', tmp_path], check=False)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass


class KitchenPrinterAgent:
    def __init__(self, config_path: str = 'config.ini'):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        self.api_url = self.config.get('api', 'url', fallback='http://localhost:5000')
        self.printer_type = self.config.get('printer', 'type', fallback='usb')
        self.vendor_id = int(self.config.get('printer', 'vendor_id', fallback='0'), 16)
        self.product_id = int(self.config.get('printer', 'product_id', fallback='0'), 16)
        self.host = self.config.get('printer', 'host', fallback='')
        self.port = int(self.config.get('printer', 'port', fallback='9100'))

        self.sio = socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=2)
        self.printer = None
        self._bind_events()

    def _bind_events(self):
        @self.sio.event
        def connect():
            print('[agent] Conectado ao servidor Socket.IO')

        @self.sio.event
        def disconnect():
            print('[agent] Desconectado. Tentando reconectar...')

        @self.sio.event
        def new_kitchen_order(data):
            try:
                self._ensure_printer()
                self._print_ticket(data)
            except Exception as e:
                print(f'[agent] ERRO AO IMPRIMIR: {e}')

    def _ensure_printer(self):
        if self.printer is not None:
            return
        if self.printer_type == 'usb':
            if Usb is None:
                raise RuntimeError('python-escpos (Usb) não disponível')
            self.printer = Usb(self.vendor_id, self.product_id)
        elif self.printer_type == 'network':
            # Preferir impressão crua via socket (sem dependências adicionais)
            self.printer = RawNetworkPrinter(self.host, self.port)
        elif self.printer_type == 'windows':
            # Imprime via spooler do Windows (Notepad)
            self.printer = WindowsSpoolPrinter()
        else:
            raise ValueError(f'Tipo de impressora não suportado: {self.printer_type}')

    def _print_ticket(self, data: dict):
        p = self.printer
        if p is None:
            raise RuntimeError('Impressora não inicializada')

        order_number = data.get('order_number')
        order_type = data.get('order_type', 'Delivery')
        timestamp = data.get('timestamp', '')
        notes = data.get('notes')
        items = data.get('items', [])

        # Cabeçalho
        p.set(align='center', double_height=True, double_width=True)
        p.text(f'Pedido #{order_number}\n')
        p.set(align='left', double_height=False, double_width=False)
        p.text(f'{order_type} - {timestamp}\n')
        p.ln(1)

        # Itens
        for item in items:
            qty = item.get('quantity', 1)
            name = item.get('name', 'Item')
            p.set(bold=True)
            p.text(f'{qty}x {name}\n')
            p.set(bold=False)
            for extra in item.get('extras', []) or []:
                prefix = '(+)' if extra.get('type') == 'add' else '(-) SEM'
                ename = extra.get('name')
                p.text(f'   {prefix} {ename}\n')
            p.ln(1)

        if notes:
            p.set(align='center', inverse=True)
            p.text(' \n OBSERVACOES \n ')
            p.set(align='left')
            p.text(f'{notes}\n\n')

        p.cut()

        # No modo Windows, precisamos enviar o arquivo ao spooler
        if hasattr(p, 'flush_and_print'):
            p.flush_and_print()

    def run(self):
        while True:
            try:
                self._ensure_printer()
            except Exception as e:
                print(f'[agent] Impressora indisponível: {e}. Re-tentando em 5s...')
                # Fecha conexão crua, se existir
                try:
                    if hasattr(self.printer, 'close'):
                        self.printer.close()
                except Exception:
                    pass
                self.printer = None
                time.sleep(5)
                continue
            try:
                self.sio.connect(self.api_url)
                self.sio.wait()
            except Exception as e:
                print(f'[agent] Falha na conexão com Socket.IO: {e}. Re-tentando em 5s...')
                time.sleep(5)


if __name__ == '__main__':
    KitchenPrinterAgent().run()


