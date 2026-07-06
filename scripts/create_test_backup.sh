#!/usr/bin/env bash

# Criar um arquivo de backup simulado
FILENAME="test_backup.sql.gz"

# Criar um arquivo SQL simples para simulação
echo "-- Dump SQL Simulado" > test_backup.sql
cat <<EOF >> test_backup.sql
CREATE TABLE test_table (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO test_table (name) VALUES ('Teste'), ('Simulado');
EOF

# Comprimir o arquivo
gzip test_backup.sql

# Verificar se o arquivo foi criado corretamente
if [ -f "$FILENAME" ]; then
    echo "Arquivo de backup simulado criado com sucesso: $FILENAME"
    echo "Tamanho: $(stat -c %s "$FILENAME") bytes"
else
    echo "Erro: Arquivo de backup não foi criado."
fi