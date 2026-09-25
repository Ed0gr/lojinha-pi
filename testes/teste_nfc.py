import time
from mfrc522 import SimpleMFRC522
import RPi.GPIO as GPIO

# Desabilita alertas de pinos já em uso
GPIO.setwarnings(False)

leitor = SimpleMFRC522()

print("Módulo RC522 inicializado (SPI). Monitorando NFC...")

try:
    while True:
        # A função read() é bloqueante; aguarda até detectar um cartão
        uid, texto = leitor.read()
        
        # O mfrc522 retorna o UID como um inteiro longo, convertemos para string
        print(f"UID lido: {uid}")
        time.sleep(1)
        
except KeyboardInterrupt:
    print("\nTeste encerrado.")
except Exception as e:
    print(f"Falha de execução. Erro: {e}")
finally:
    GPIO.cleanup()