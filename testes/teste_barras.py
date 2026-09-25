import sys
from evdev import InputDevice, categorize, ecodes

# Substitua 'eventX' pelo identificador correspondente ao leitor
caminho_dispositivo = '/dev/input/event5'

try:
    dispositivo = InputDevice(caminho_dispositivo)
    print(f"Monitorando dispositivo: {dispositivo.name}")
except FileNotFoundError:
    print(f"Erro: Dispositivo {caminho_dispositivo} não encontrado.")
    sys.exit(1)
except PermissionError:
    print("Erro de permissão: Execute com 'sudo' ou adicione o usuário ao grupo 'input'.")
    sys.exit(1)

# Mapeamento do padrão USB HID (scancodes para numerais)
scancodes = {
    2: '1', 3: '2', 4: '3', 5: '4', 6: '5',
    7: '6', 8: '7', 9: '8', 10: '9', 11: '0'
}

codigo_acumulado = ""

# Captura em loop bloqueante para o teste
for event in dispositivo.read_loop():
    if event.type == ecodes.EV_KEY:
        key_event = categorize(event)
        
        # Estado 1 indica tecla pressionada (Key Down)
        if key_event.keystate == 1:
            if key_event.scancode in scancodes:
                codigo_acumulado += scancodes[key_event.scancode]
            # O código 28 representa a tecla ENTER, que o leitor envia ao final da leitura
            elif key_event.scancode == 28:
                print(f"Código escaneado: {codigo_acumulado}")
                codigo_acumulado = ""