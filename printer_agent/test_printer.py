#!/usr/bin/env python3
"""
Simulador de impressora para testes
"""
import socketio
import json
from datetime import datetime

class PrinterSimulator:
    def __init__(self, api_url="http://localhost:5000"):
        self.sio = socketio.Client()
        self.api_url = api_url
        self._bind_events()
    
    def _bind_events(self):
        @self.sio.event
        def connect():
            print("[SIMULADOR] Conectado ao servidor Socket.IO")
        
        @self.sio.event
        def disconnect():
            print("[SIMULADOR] Desconectado")
        
        @self.sio.event
        def new_kitchen_order(data):
            print(f"\n[SIMULADOR] ===== TICKET DE COZINHA =====")
            print(f"Pedido: #{data.get('order_number')}")
            print(f"Tipo: {data.get('order_type')}")
            print(f"Horario: {data.get('timestamp')}")
            print(f"Observacoes: {data.get('notes', 'Nenhuma')}")
            print("\nITENS:")
            
            for item in data.get('items', []):
                qty = item.get('quantity', 1)
                name = item.get('name', 'Item')
                print(f"  {qty}x {name}")
                
                for extra in item.get('extras', []) or []:
                    prefix = "(+)" if extra.get('type') == 'add' else "(-) SEM"
                    ename = extra.get('name', 'Extra')
                    print(f"    {prefix} {ename}")
            
            print("=" * 50)
            print(f"[SIMULADOR] Ticket impresso em {datetime.now().strftime('%H:%M:%S')}")
    
    def run(self):
        try:
            print(f"[SIMULADOR] Conectando ao servidor: {self.api_url}")
            self.sio.connect(self.api_url)
            self.sio.wait()
        except Exception as e:
            print(f"[SIMULADOR] Erro: {e}")

if __name__ == "__main__":
    import sys
    api_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"
    PrinterSimulator(api_url).run()
