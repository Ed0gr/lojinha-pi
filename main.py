import eventlet
eventlet.monkey_patch()
import os
import sqlite3
import time
import select
import threading
from flask import Flask, render_template
from flask_socketio import SocketIO
from evdev import InputDevice, categorize, ecodes, list_devices
from mfrc522 import SimpleMFRC522
import RPi.GPIO as GPIO

DB_PATH = '/home/financeiro_avant/sistema_vendas/sistema_vendas.db'

app = Flask(__name__)
socketio = SocketIO(app, async_mode='eventlet')

GPIO.setwarnings(False)

def encontrar_leitor_barras():
    for path in list_devices():
        dev = InputDevice(path)
        if dev.name == "HID 28e9:0380":
            return path
    return None

caminho_barras = encontrar_leitor_barras()
if not caminho_barras:
    print("ERRO: Leitor de código de barras não encontrado automaticamente.")
    exit(1)

leitor_barras = InputDevice(caminho_barras)
leitor_barras.grab() 
print(f"Leitor de barras conectado em: {caminho_barras} (Modo Exclusivo)")

leitor_nfc = SimpleMFRC522()

scancodes = {
    2: '1', 3: '2', 4: '3', 5: '4', 6: '5',
    7: '6', 8: '7', 9: '8', 10: '9', 11: '0',
    12: '-', 13: '=', 14: 'BKSP', 15: 'TAB',
    16: 'q', 17: 'w', 18: 'e', 19: 'r', 20: 't', 21: 'y', 22: 'u', 23: 'i', 24: 'o', 25: 'p',
    30: 'a', 31: 's', 32: 'd', 33: 'f', 34: 'g', 35: 'h', 36: 'j', 37: 'k', 38: 'l',
    44: 'z', 45: 'x', 46: 'c', 47: 'v', 48: 'b', 49: 'n', 50: 'm'
}

estado_global = {
    'estado_atual': 'OCIOSO',
    'carrinho': [],
    'subtotal': 0.0
}

def buscar_produto(codigo):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, preco FROM produtos WHERE codigo_barras = ?", (codigo,))
    produto = cursor.fetchone()
    conn.close()
    return produto

def validar_membro(uid):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT nome FROM membros WHERE id_nfc = ?", (uid,))
    membro = cursor.fetchone()
    conn.close()
    return membro

def registrar_transacao(uid, itens, total):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    data_hora = time.strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        itens_str = ", ".join(itens)
        cursor.execute("""
            INSERT INTO vendas (id_usuario, data_hora, itens_comprados, valor_total)
            VALUES (?, ?, ?, ?)
        """, (uid, data_hora, itens_str, total))
        conn.commit()
    except sqlite3.Error as e:
        print(f"ERRO SQL: {e}")
    finally:
        conn.close()

@app.route('/')
def index():
    global estado_global
    # Renderiza o template correspondente ao estado atual do sistema
    if estado_global['estado_atual'] == 'CARRINHO':
        return render_template('carrinho.html', itens=estado_global['carrinho'], total=estado_global['subtotal'])
    elif estado_global['estado_atual'] == 'SUCESSO':
        return render_template('finalizado.html')
    else:
        return render_template('ocioso.html')

@socketio.on('remover_item')
def remover_item_carrinho(dados):
    global estado_global
    codigo_alvo = dados.get('codigo')
    
    for i, item in enumerate(estado_global['carrinho']):
        if item['codigo'] == codigo_alvo:
            estado_global['subtotal'] -= item['preco_unitario']
            item['quantidade'] -= 1
            item['preco_total'] -= item['preco_unitario']
            
            if item['quantidade'] <= 0:
                del estado_global['carrinho'][i]
            break
            
    if len(estado_global['carrinho']) == 0:
        estado_global['estado_atual'] = 'OCIOSO'
        estado_global['subtotal'] = 0.0
        
    socketio.emit('atualizacao_tela', estado_global)

def loop_leitor_barras():
    global estado_global
    
    buffer_barras = ""
    ultimo_evento = time.time()
    TIMEOUT_SEGUNDOS = 60
    
    print("SISTEMA PRONTO. Aguardando interações de hardware.")

    try:
        while True:
            tempo_atual = time.time()
            
            if estado_global['estado_atual'] == 'CARRINHO' and (tempo_atual - ultimo_evento > TIMEOUT_SEGUNDOS):
                print("TIMEOUT: Limpando carrinho.")
                estado_global['estado_atual'] = 'OCIOSO'
                estado_global['carrinho'].clear()
                estado_global['subtotal'] = 0.0
                buffer_barras = ""
                socketio.emit('atualizacao_tela', estado_global)
                continue

            r, w, x = select.select([leitor_barras.fd], [], [], 0.05)
            if r:
                codigos_lidos = []
                try:
                    for event in leitor_barras.read():
                        if event.type == ecodes.EV_KEY and event.value == 1:
                            if event.code == 28: 
                                codigo_limpo = buffer_barras.strip()
                                buffer_barras = "" 
                                if len(codigo_limpo) >= 3:
                                    codigos_lidos.append(codigo_limpo)
                            elif event.code in scancodes:
                                buffer_barras += scancodes[event.code]
                except BlockingIOError:
                    pass

                for codigo in codigos_lidos:
                    produto_db = buscar_produto(codigo)
                    
                    if produto_db:
                        nome, preco = produto_db
                        estado_global['subtotal'] += preco
                        estado_global['estado_atual'] = 'CARRINHO'
                        
                        encontrado = False
                        for item in estado_global['carrinho']:
                            if item['codigo'] == codigo:
                                item['quantidade'] += 1
                                item['preco_total'] += preco
                                encontrado = True
                                break
                        
                        if not encontrado:
                            estado_global['carrinho'].append({
                                'codigo': codigo, 
                                'nome': nome, 
                                'preco_unitario': preco,
                                'quantidade': 1,
                                'preco_total': preco
                            })
                        
                        print(f"CARRINHO ATUALIZADO: R$ {estado_global['subtotal']:.2f}")
                        socketio.emit('atualizacao_tela', estado_global)
                    else:
                        print(f"PRODUTO DESCONHECIDO: {codigo}")
                    
                    ultimo_evento = tempo_atual

            eventlet.sleep(0.01)

    except KeyboardInterrupt:
        pass

def loop_leitor_nfc():
    global estado_global
    try:
        while True:
            if estado_global['estado_atual'] == 'CARRINHO':
                uid, texto = leitor_nfc.read_no_block()
                
                if uid is not None:
                    uid_str = str(uid)
                    membro = validar_membro(uid_str)
                    
                    if membro:
                        nome_membro = membro[0]
                        print(f"COMPRA AUTORIZADA: {nome_membro}")
                        
                        lista_codigos = []
                        for item in estado_global['carrinho']:
                            for _ in range(item['quantidade']):
                                lista_codigos.append(item['codigo'])
                                
                        registrar_transacao(uid_str, lista_codigos, estado_global['subtotal'])
                        
                        estado_global['estado_atual'] = 'SUCESSO'
                        socketio.emit('atualizacao_tela', estado_global)
                        
                        time.sleep(6)
                        
                        estado_global['estado_atual'] = 'OCIOSO'
                        estado_global['carrinho'].clear()
                        estado_global['subtotal'] = 0.0
                        socketio.emit('atualizacao_tela', estado_global)
                    else:
                        print("CARTÃO NÃO CADASTRADO NO BANCO DE DADOS.")
            
            eventlet.sleep(0.5)
    except KeyboardInterrupt:
        pass

@socketio.on('desligar')
def desligar_sistema():
    print("Comando de desligamento recebido.")
    os.system('sudo shutdown -h now')

if __name__ == '__main__':
    # Inicializa as duas threads de hardware de forma independente
    thread_barras = threading.Thread(target=loop_leitor_barras, daemon=True)
    thread_barras.start()
    
    thread_nfc = threading.Thread(target=loop_leitor_nfc, daemon=True)
    thread_nfc.start()
    
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    finally:
        GPIO.cleanup()