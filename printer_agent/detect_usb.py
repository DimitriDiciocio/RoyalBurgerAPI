#!/usr/bin/env python3
"""
Script simples para detectar dispositivos USB no Windows
"""
import subprocess
import sys

def detect_usb_devices():
    """Detecta dispositivos USB no Windows"""
    print("Detectando dispositivos USB...")
    
    try:
        # Usa wmic para listar dispositivos USB
        cmd = ["wmic", "path", "Win32_USBHub", "get", "DeviceID,Description"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("Dispositivos USB encontrados:")
            lines = result.stdout.split('\n')
            for line in lines:
                if line.strip() and 'DeviceID' not in line and 'Description' not in line:
                    print(f"  {line.strip()}")
        else:
            print("Erro ao detectar dispositivos USB")
            
    except Exception as e:
        print(f"Erro: {e}")

def detect_printers():
    """Detecta impressoras instaladas"""
    print("\nDetectando impressoras...")
    
    try:
        cmd = ["wmic", "printer", "get", "Name,PortName,DriverName"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("Impressoras encontradas:")
            lines = result.stdout.split('\n')
            for line in lines:
                if line.strip() and 'Name' not in line and 'PortName' not in line and 'DriverName' not in line:
                    print(f"  {line.strip()}")
        else:
            print("Erro ao detectar impressoras")
            
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    print("DETECTOR DE DISPOSITIVOS USB E IMPRESSORAS")
    print("=" * 50)
    
    detect_usb_devices()
    detect_printers()
    
    print("\nINFORMACOES IMPORTANTES:")
    print("1. Se voce tem uma impressora termica USB, procure por:")
    print("   - Epson TM-T20, TM-T82, TM-T88")
    print("   - Star TSP100, TSP650")
    print("   - Citizen CT-S310")
    print("   - Bixolon SRP-350")
    print("   - Zebra ZD220")
    print("\n2. Para impressoras de rede, anote o IP da impressora")
    print("\n3. Edite o arquivo config.ini com os dados encontrados")
