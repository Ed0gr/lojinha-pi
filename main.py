import eventlet
eventlet.monkey_patch()

import os
import sqlite3
import time
import select
import threading
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO
from evdev import InputDevice, categorize, ecodes, list_devices
from mfrc522 import SimpleMFRC522
import RPi.GPIO as GPIO

load_dotenv()

DB_PATH = '/home/financeiro_avant/sistema_vendas/sistema_vendas.db'

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'chave_secreta_totem_avant_2026')
socketio = SocketIO(app, async_mode='eventlet')

ADMIN_USER = os.getenv('ADMIN_USER', 'admin')
ADMIN_PASS = os.getenv('ADMIN_PASS', 'admin123')

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
    'subtotal': 0.0,
    'admin_ativo': False
}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def buscar_produto(codigo):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, preco FROM produtos WHERE codigo_barras = ?", (codigo,))
    produto = cursor.fetchone()
    conn.close()
    return produto

def buscar_membro(uid):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT nome, email FROM membros WHERE id_nfc = ?", (uid,))
    membro = cursor.fetchone()
    conn.close()
    return membro

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

# --- SOCKETIO EVENTS ---

@socketio.on('entrar_admin')
def ativar_modo_admin():
    estado_global['admin_ativo'] = True
    print("[SISTEMA] Painel Admin conectado. Totem de vendas PAUSADO.")

@socketio.on('sair_admin')
def desativar_modo_admin():
    estado_global['admin_ativo'] = False
    print("[SISTEMA] Painel Admin desconectado. Totem de vendas LIBERADO.")

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

@socketio.on('desligar')
def desligar_sistema():
    print("Comando de desligamento recebido.")
    os.system('sudo shutdown -h now')

# --- ROTAS FLASK ---

@app.route('/')
def index():
    global estado_global
    if estado_global['estado_atual'] == 'CARRINHO':
        return render_template('carrinho.html', itens=estado_global['carrinho'], total=estado_global['subtotal'])
    elif estado_global['estado_atual'] == 'SUCESSO':
        return render_template('finalizado.html')
    else:
        return render_template('ocioso.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    erro = None
    if request.method == 'POST':
        usuario = request.form.get('username')
        senha = request.form.get('password')
        if usuario == ADMIN_USER and senha == ADMIN_PASS:
            session['logged_in'] = True
            return redirect(url_for('admin_panel'))
        else:
            erro = 'Usuário ou senha incorretos.'
    return render_template('login.html', erro=erro)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    estado_global['admin_ativo'] = False
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
def admin_panel():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT codigo_barras, nome, preco FROM produtos")
    produtos = cursor.fetchall()
    cursor.execute("SELECT id_nfc, nome, email FROM membros")
    membros = cursor.fetchall()
    conn.close()
    return render_template('admin.html', produtos=produtos, membros=membros)

@app.route('/api/admin/produto', methods=['POST'])
@login_required
def cadastrar_produto_web():
    data = request.get_json()
    codigo = data.get('codigo')
    nome = data.get('nome', '').strip()
    try:
        preco = float(str(data.get('preco')).replace(',', '.'))
    except ValueError:
        return jsonify({"status": "erro", "mensagem": "Preço inválido."}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO produtos (codigo_barras, nome, preco)
            VALUES (?, ?, ?)
            ON CONFLICT(codigo_barras) DO UPDATE SET
                nome = CASE WHEN excluded.nome != '' THEN excluded.nome ELSE produtos.nome END,
                preco = excluded.preco
        """, (codigo, nome, preco))
        conn.commit()
        return jsonify({"status": "sucesso", "mensagem": "Produto salvo com sucesso!"})
    except sqlite3.Error as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/admin/membro', methods=['POST'])
@login_required
def cadastrar_membro_web():
    data = request.get_json()
    uid = data.get('uid')
    nome = data.get('nome', '').strip()
    email = data.get('email', '').strip()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO membros (id_nfc, nome, email)
            VALUES (?, ?, ?)
            ON CONFLICT(id_nfc) DO UPDATE SET
                nome = CASE WHEN excluded.nome != '' THEN excluded.nome ELSE membros.nome END,
                email = CASE WHEN excluded.email != '' THEN excluded.email ELSE membros.email END
        """, (uid, nome, email))
        conn.commit()
        return jsonify({"status": "sucesso", "mensagem": "Membro salvo com sucesso!"})
    except sqlite3.Error as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 500
    finally:
        conn.close()

# --- THREADS DE HARDWARE ---

def loop_leitor_barras():
    global estado_global
    buffer_barras = ""
    ultimo_evento = time.time()
    TIMEOUT_SEGUNDOS = 60

    print("Thread do Leitor de Barras iniciada.")

    try:
        while True:
            tempo_atual = time.time()
            
            if not estado_global['admin_ativo'] and estado_global['estado_atual'] == 'CARRINHO' and (tempo_atual - ultimo_evento > TIMEOUT_SEGUNDOS):
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

                    if estado_global['admin_ativo']:
                        payload = {'codigo': codigo, 'nome': '', 'preco': ''}
                        if produto_db:
                            payload['nome'] = produto_db[0]
                            payload['preco'] = produto_db[1]
                        socketio.emit('codigo_escaneado', payload)
                        print(f"[ADMIN] Código escaneado: {codigo}")
                    else:
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
                            
                            socketio.emit('atualizacao_tela', estado_global)
                        else:
                            print(f"PRODUTO DESCONHECIDO: {codigo}")
                    
                    ultimo_evento = tempo_atual

            eventlet.sleep(0.01)
    except KeyboardInterrupt:
        pass

def loop_leitor_nfc():
    global estado_global
    print("Thread do Leitor NFC iniciada.")
    while True:
        try:
            uid, texto = leitor_nfc.read_no_block()
            
            if uid is not None:
                uid_str = str(uid)
                print(f"[DEBUG NFC] Cartão detectado: {uid_str}")

                if estado_global['admin_ativo']:
                    membro_db = buscar_membro(uid_str)
                    payload = {'uid': uid_str, 'nome': '', 'email': ''}
                    if membro_db:
                        payload['nome'] = membro_db[0]
                        payload['email'] = membro_db[1] if membro_db[1] else ''
                    socketio.emit('nfc_escaneado', payload)
                    eventlet.sleep(1)
                elif estado_global['estado_atual'] == 'CARRINHO':
                    membro = validar_membro(uid_str)
                    if membro:
                        nome_membro = membro[0]
                        lista_codigos = []
                        for item in estado_global['carrinho']:
                            for _ in range(item['quantidade']):
                                lista_codigos.append(item['codigo'])
                                
                        registrar_transacao(uid_str, lista_codigos, estado_global['subtotal'])
                        estado_global['estado_atual'] = 'SUCESSO'
                        socketio.emit('atualizacao_tela', estado_global)
                        
                        eventlet.sleep(6)
                        
                        estado_global['estado_atual'] = 'OCIOSO'
                        estado_global['carrinho'].clear()
                        estado_global['subtotal'] = 0.0
                        socketio.emit('atualizacao_tela', estado_global)
                    else:
                        print("CARTÃO NÃO CADASTRADO NO BANCO DE DADOS.")
                        eventlet.sleep(2)
        except Exception as e:
            print(f"[ERRO NFC] Falha na leitura: {e}")

        eventlet.sleep(0.5)

if __name__ == '__main__':
    thread_barras = threading.Thread(target=loop_leitor_barras, daemon=True)
    thread_barras.start()
    
    thread_nfc = threading.Thread(target=loop_leitor_nfc, daemon=True)
    thread_nfc.start()
    
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    finally:
        GPIO.cleanup()