import sqlite3
import sys
import select
from evdev import InputDevice, ecodes, categorize, list_devices
from mfrc522 import SimpleMFRC522
import RPi.GPIO as GPIO

DB_PATH = '/home/financeiro_avant/sistema_vendas/sistema_vendas.db'

scancodes = {
    2: '1', 3: '2', 4: '3', 5: '4', 6: '5',
    7: '6', 8: '7', 9: '8', 10: '9', 11: '0',
    12: '-', 13: '=', 14: 'BKSP', 15: 'TAB',
    16: 'q', 17: 'w', 18: 'e', 19: 'r', 20: 't', 21: 'y', 22: 'u', 23: 'i', 24: 'o', 25: 'p',
    30: 'a', 31: 's', 32: 'd', 33: 'f', 34: 'g', 35: 'h', 36: 'j', 37: 'k', 38: 'l',
    44: 'z', 45: 'x', 46: 'c', 47: 'v', 48: 'b', 49: 'n', 50: 'm'
}

def encontrar_leitor_barras():
    for path in list_devices():
        dev = InputDevice(path)
        if dev.name == "HID 28e9:0380":
            return path
    return None

def ler_codigo_barras_hardware():
    caminho_dispositivo = encontrar_leitor_barras()
    
    if not caminho_dispositivo:
        print("ERRO: Leitor de código de barras não foi encontrado automaticamente.")
        return None

    leitor_barras = InputDevice(caminho_dispositivo)
    print("Aguardando leitura do código de barras...")
    codigo = ""
    
    while True:
        r, w, x = select.select([leitor_barras.fd], [], [], 0.1)
        if r:
            for event in leitor_barras.read():
                if event.type == ecodes.EV_KEY:
                    key_event = categorize(event)
                    if key_event.keystate == 1:
                        if key_event.scancode == 28:
                            return codigo
                        elif key_event.scancode in scancodes:
                            codigo += scancodes[key_event.scancode]

def cadastrar_pessoa():
    nome = input("Nome da pessoa: ")
    email = input("Email: ")
    print("Aproxime a carteirinha do leitor NFC...")
    
    leitor = SimpleMFRC522()
    try:
        uid, texto = leitor.read()
        uid_str = str(uid)
        print(f"UID capturado: {uid_str}")
    except Exception as e:
        print(f"Falha de hardware no leitor NFC: {e}")
        return
    finally:
        GPIO.cleanup()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO membros (id_nfc, nome, email) VALUES (?, ?, ?)", (uid_str, nome, email))
        conn.commit()
        print(f"SUCESSO: Pessoa '{nome}' cadastrada.")
    except sqlite3.IntegrityError:
        print("ERRO: Este cartão (UID) já está vinculado a um membro.")
    finally:
        conn.close()

def cadastrar_produto():
    nome = input("Nome do produto: ")
    
    try:
        preco_input = input("Preço (ex: 5.50): ")
        preco = float(preco_input.replace(',', '.'))
    except ValueError:
        print("ERRO: Formato de preço inválido. Cadastro cancelado.")
        return

    codigo = ler_codigo_barras_hardware()
    if not codigo:
        print("Operação cancelada ou falha na leitura.")
        return
        
    print(f"Código de barras capturado: {codigo}")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO produtos (codigo_barras, nome, preco) VALUES (?, ?, ?)", (codigo, nome, preco))
        conn.commit()
        print(f"SUCESSO: Produto '{nome}' cadastrado.")
    except sqlite3.IntegrityError:
        print("ERRO: Este código de barras já está registrado.")
    finally:
        conn.close()

def atualizar_preco_produto():
    print("Escaneie o código de barras do produto que deseja atualizar:")
    codigo = ler_codigo_barras_hardware()
    if not codigo:
        print("Operação cancelada ou falha na leitura.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Verifica se o produto existe
    cursor.execute("SELECT nome, preco FROM produtos WHERE codigo_barras = ?", (codigo,))
    produto = cursor.fetchone()
    
    if not produto:
        print(f"ERRO: Nenhum produto encontrado com o código de barras '{codigo}'.")
        conn.close()
        return
        
    nome_atual, preco_atual = produto
    print(f"Produto encontrado: {nome_atual} | Preço atual: R$ {preco_atual:.2f}")
    
    try:
        novo_preco_input = input("Digite o novo preço (ex: 6.00): ")
        novo_preco = float(novo_preco_input.replace(',', '.'))
    except ValueError:
        print("ERRO: Formato de preço inválido. Atualização cancelada.")
        conn.close()
        return

    cursor.execute("UPDATE produtos SET preco = ? WHERE codigo_barras = ?", (novo_preco, codigo))
    conn.commit()
    conn.close()
    print(f"SUCESSO: Preço do produto '{nome_atual}' atualizado para R$ {novo_preco:.2f}.")

def main():
    while True:
        print("\nCADASTRO E ADMINISTRAÇÃO")
        print("1. Cadastrar Pessoa")
        print("2. Cadastrar Produto")
        print("3. Atualizar Preço de Produto")
        print("4. Sair")
        
        escolha = input("Selecione a opção: ")
        
        if escolha == '1':
            cadastrar_pessoa()
        elif escolha == '2':
            cadastrar_produto()
        elif escolha == '3':
            atualizar_preco_produto()
        elif escolha == '4':
            sys.exit(0)
        else:
            print("Opção inválida.")

if __name__ == '__main__':
    GPIO.setwarnings(False)
    main()