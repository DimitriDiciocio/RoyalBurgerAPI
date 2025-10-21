#!/usr/bin/env python3
"""
Script para detectar impressoras térmicas disponíveis
"""
import sys
import subprocess
import socket
import threading
from concurrent.futures import ThreadPoolExecutor

def detect_usb_printers():
    """Detecta impressoras USB usando lsusb (Linux) ou PowerShell (Windows)"""
    print("Detectando impressoras USB...")
    
    try:
        if sys.platform == "win32":
            # Windows - PowerShell
            cmd = [
                "powershell", "-Command",
                "Get-PnpDevice -Class Printer | Select-Object Name, InstanceId | Format-Table -AutoSize"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print("Impressoras encontradas:")
                print(result.stdout)
            else:
                print("Erro ao detectar impressoras USB no Windows")
                
        else:
            # Linux/Mac - lsusb
            result = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print("Dispositivos USB encontrados:")
                lines = result.stdout.split('\n')
                for line in lines:
                    if any(keyword in line.lower() for keyword in ['printer', 'thermal', 'pos', 'receipt']):
                        print(f"  {line}")
            else:
                print("lsusb nao disponivel")
                
    except Exception as e:
        print(f"Erro ao detectar USB: {e}")

def test_network_printer(ip, port=9100):
    """Testa se uma impressora de rede está acessível"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except:
        return False

def detect_network_printers():
    """Detecta impressoras de rede na rede local"""
    print("Detectando impressoras de rede...")
    
    # Pega o IP da máquina atual
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        
        # Pega a rede (ex: 192.168.1.0/24)
        network = '.'.join(local_ip.split('.')[:-1]) + '.0/24'
        print(f"Escaneando rede: {network}")
        
        # Escaneia a rede
        from concurrent.futures import ThreadPoolExecutor
        import ipaddress
        
        network_obj = ipaddress.ip_network(network, strict=False)
        hosts = list(network_obj.hosts())[:254]  # Limita a 254 IPs
        
        def check_host(ip):
            if test_network_printer(str(ip)):
                return str(ip)
            return None
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            results = executor.map(check_host, hosts)
            found_ips = [ip for ip in results if ip is not None]
        
        if found_ips:
            print("Impressoras de rede encontradas:")
            for ip in found_ips:
                print(f"  {ip}:9100 (porta padrao)")
        else:
            print("Nenhuma impressora de rede encontrada")
            
    except Exception as e:
        print(f"Erro ao detectar rede: {e}")

def detect_common_thermal_printers():
    """Lista impressoras térmicas comuns e seus IDs"""
    print("\nImpressoras termicas comuns:")
    
    common_printers = [
        ("Epson TM-T20", "0x04b8", "0x0e15"),
        ("Epson TM-T82", "0x04b8", "0x0e28"),
        ("Epson TM-T88", "0x04b8", "0x0202"),
        ("Star TSP100", "0x0519", "0x0001"),
        ("Star TSP650", "0x0519", "0x0002"),
        ("Citizen CT-S310", "0x1CB0", "0x0004"),
        ("Bixolon SRP-350", "0x04e8", "0x0202"),
        ("Zebra ZD220", "0x0a5f", "0x0001"),
    ]
    
    for name, vendor_id, product_id in common_printers:
        print(f"  {name}: vendor_id={vendor_id}, product_id={product_id}")

def main():
    print("DETECTOR DE IMPRESSORAS TERMICAS")
    print("=" * 50)
    
    # Detecta USB
    detect_usb_printers()
    print()
    
    # Detecta rede
    detect_network_printers()
    print()
    
    # Lista comuns
    detect_common_thermal_printers()
    print()
    
    print("PROXIMOS PASSOS:")
    print("1. Se encontrou uma impressora USB, anote o vendor_id e product_id")
    print("2. Se encontrou uma impressora de rede, anote o IP")
    print("3. Edite o arquivo config.ini com os dados encontrados")
    print("4. Execute: python printer_agent.py")

if __name__ == "__main__":
    main()
