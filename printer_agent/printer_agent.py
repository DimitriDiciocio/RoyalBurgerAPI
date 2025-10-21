import time
import socketio
import configparser

try:
    from escpos.printer import Usb, Network
except Exception:
    Usb = None
    Network = None


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
            if Network is None:
                raise RuntimeError('python-escpos (Network) não disponível')
            self.printer = Network(self.host, port=self.port)
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

    def run(self):
        while True:
            try:
                self._ensure_printer()
            except Exception as e:
                print(f'[agent] Impressora indisponível: {e}. Re-tentando em 5s...')
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


