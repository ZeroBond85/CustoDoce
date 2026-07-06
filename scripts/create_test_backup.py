#!/usr/bin/env python3

# Criar um arquivo de backup simulado
import os
import gzip
import shutil

# Criar um arquivo SQL simples para simulação
sql_content = """-- Dump SQL Simulado
CREATE TABLE test_table (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO test_table (name) VALUES ('Teste'), ('Simulado');
"""

with open('test_backup.sql', 'w') as f:
    f.write(sql_content)

# Comprimir o arquivo
with open('test_backup.sql', 'rb') as f_in, gzip.open('test_backup.sql.gz', 'wb') as f_out:
    shutil.copyfileobj(f_in, f_out)

# Verificar se o arquivo foi criado corretamente
if os.path.exists('test_backup.sql.gz'):
    file_size = os.path.getsize('test_backup.sql.gz')
    print('Arquivo de backup simulado criado com sucesso: test_backup.sql.gz')
    print(f'Tamanho: {file_size} bytes')
else:
    print('Erro: Arquivo de backup não foi criado.')