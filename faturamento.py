import sqlite3
import csv
import smtplib
from io import StringIO
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from collections import Counter

DB_PATH = '/home/financeiro_avant/sistema_vendas/sistema_vendas.db'

# Configurações do Servidor SMTP
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USER = os.getenv('EMAIL_REMETENTE')
SMTP_PASSWORD = os.getenv('SENHA_EMAIL')
EMAIL_DIRETOR = os.getenv('EMAIL_DIRETOR')

def processar_faturamento():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    mes_atual = datetime.now().strftime('%Y-%m')
    
    # Carrega o mapeamento de produtos (código -> {nome, preco})
    cursor.execute("SELECT codigo_barras, nome, preco FROM produtos")
    mapa_produtos = {linha[0]: {'nome': linha[1], 'preco': linha[2]} for linha in cursor.fetchall()}
    
    cursor.execute('''
        SELECT m.id_nfc, m.nome, m.email, v.data_hora, v.itens_comprados, v.valor_total
        FROM vendas v
        JOIN membros m ON v.id_usuario = m.id_nfc
        WHERE v.data_hora LIKE ?
        ORDER BY m.nome, v.data_hora
    ''', (f'{mes_atual}%',))
    
    todas_vendas = cursor.fetchall()
    conn.close()
    
    if not todas_vendas:
        print("Nenhuma transação encontrada para o mês atual.")
        return

    dados_membros = {}
    linhas_geral = []

    for id_nfc, nome, email, data_hora, itens_str, valor_transacao in todas_vendas:
        if id_nfc not in dados_membros:
            dados_membros[id_nfc] = {'nome': nome, 'email': email, 'total': 0.0, 'compras': []}
            
        dados_membros[id_nfc]['total'] += valor_transacao
        
        lista_codigos = [codigo.strip() for codigo in itens_str.split(',')]
        contagem_itens = Counter(lista_codigos)
        
        # Cria uma linha separada para cada produto distinto da transação
        for codigo, qtd in contagem_itens.items():
            info_produto = mapa_produtos.get(codigo, {'nome': f"Desconhecido ({codigo})", 'preco': 0.0})
            nome_produto = info_produto['nome']
            subtotal_item = info_produto['preco'] * qtd
            
            dados_membros[id_nfc]['compras'].append([data_hora, nome_produto, qtd, f"R$ {subtotal_item:.2f}"])
            linhas_geral.append([nome, email, data_hora, nome_produto, qtd, f"R$ {subtotal_item:.2f}"])

    enviar_emails(dados_membros, linhas_geral, mes_atual)

def criar_anexo_csv_memoria(cabecalho, linhas):
    arquivo_memoria = StringIO()
    escritor = csv.writer(arquivo_memoria)
    escritor.writerow(cabecalho)
    escritor.writerows(linhas)
    
    parte = MIMEBase('application', 'octet-stream')
    parte.set_payload(arquivo_memoria.getvalue().encode('utf-8'))
    encoders.encode_base64(parte)
    return parte

def enviar_emails(dados_membros, linhas_geral, mes_atual):
    try:
        servidor = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        servidor.starttls()
        servidor.login(SMTP_USER, SMTP_PASSWORD)
    except Exception as e:
        print(f"Falha de conexão SMTP: {e}")
        return

    cabecalho_membro = ['Data/Hora', 'Produto', 'Quantidade', 'Valor Subtotal']
    
    for id_nfc, info in dados_membros.items():
        if not info['email']:
            print(f"Membro {info['nome']} sem e-mail cadastrado. Ignorado.")
            continue

        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = info['email']
        msg['Subject'] = f"Extrato Lojinha AVANT - {mes_atual}"
        
        corpo = f"Olá {info['nome']},\n\nO seu gasto total na lojinha neste mês foi de R$ {info['total']:.2f}.\n\nSegue em anexo o extrato detalhado de suas compras."
        msg.attach(MIMEText(corpo, 'plain'))
        
        anexo = criar_anexo_csv_memoria(cabecalho_membro, info['compras'])
        anexo.add_header('Content-Disposition', f'attachment; filename=extrato_{mes_atual}.csv')
        msg.attach(anexo)

        try:
            servidor.sendmail(SMTP_USER, info['email'], msg.as_string())
            print(f"Extrato enviado para: {info['email']}")
        except Exception as e:
            print(f"Erro ao enviar para {info['email']}: {e}")

    cabecalho_geral = ['Nome', 'Email', 'Data/Hora', 'Produto', 'Quantidade', 'Valor Subtotal']
    
    msg_diretor = MIMEMultipart()
    msg_diretor['From'] = SMTP_USER
    msg_diretor['To'] = EMAIL_DIRETOR
    msg_diretor['Subject'] = f"Relatório Consolidado Lojinha AVANT - {mes_atual}"
    msg_diretor.attach(MIMEText("Segue em anexo o relatório geral com o histórico completo de todas as vendas do mês.", 'plain'))
    
    anexo_geral = criar_anexo_csv_memoria(cabecalho_geral, linhas_geral)
    anexo_geral.add_header('Content-Disposition', f'attachment; filename=relatorio_geral_{mes_atual}.csv')
    msg_diretor.attach(anexo_geral)

    try:
        servidor.sendmail(SMTP_USER, EMAIL_DIRETOR, msg_diretor.as_string())
        print(f"Relatório geral enviado para: {EMAIL_DIRETOR}")
    except Exception as e:
        print(f"Erro ao enviar o relatório geral: {e}")

    servidor.quit()

if __name__ == '__main__':
    processar_faturamento()