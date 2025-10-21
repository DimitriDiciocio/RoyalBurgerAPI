# Royal Burger - Agente de Impressão da Cozinha

Script Python que roda 24/7 na rede local e ouve eventos da API (Socket.IO) para imprimir tickets de cozinha em impressoras térmicas.

## Requisitos

- Python 3.8+
- Impressora térmica compatível com ESC/POS (USB/Ethernet)

## Instalação

```bash
cd printer_agent
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

## Configuração

Edite o arquivo `config.ini`:

```
[api]
url = http://localhost:5000  # ou https://api.royalburger.com

[printer]
type = usb         # usb | network
vendor_id = 0x04b8 # Exemplo Epson
product_id = 0x0e15
host = 192.168.0.50  # se type=network
port = 9100          # se type=network
```

## Execução

```bash
python printer_agent.py
```

O agente mantém reconexão automática ao servidor Socket.IO e à impressora.
