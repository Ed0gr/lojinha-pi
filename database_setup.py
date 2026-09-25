import sqlite3

def criar_banco():
    conn = sqlite3.connect('sistema_vendas.db')
    cursor = conn.cursor()
    
    # Tabela de membros com a coluna email definitiva
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS membros (
            id_nfc TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            email TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            codigo_barras TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            preco REAL NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_usuario TEXT,
            data_hora TEXT,
            itens_comprados TEXT,
            valor_total REAL,
            FOREIGN KEY (id_usuario) REFERENCES membros (id_nfc)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Banco de dados configurado com sucesso.")

if __name__ == '__main__':
    criar_banco()