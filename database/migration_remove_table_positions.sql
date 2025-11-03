-- ==========================================
-- Migração: Remoção de Layout Visual (X/Y Positions)
-- Data: Refatoração do Módulo de Gestão de Salão
-- ==========================================
-- Descrição: Remove as colunas X_POSITION e Y_POSITION da tabela RESTAURANT_TABLES
--            e adiciona constraint UNIQUE na coluna NAME para garantir nomes únicos.

-- Passo 1: Remover a coluna Y_POSITION (Firebird requer remover dependências primeiro)
ALTER TABLE RESTAURANT_TABLES DROP Y_POSITION;

-- Passo 2: Remover a coluna X_POSITION
ALTER TABLE RESTAURANT_TABLES DROP X_POSITION;

-- Passo 3: Remover índices relacionados às posições (se existirem)
-- Nota: O Firebird pode criar índices automaticamente, mas vamos garantir a remoção
-- Se o índice não existir, o comando será ignorado
-- DROP INDEX IDX_RESTAURANT_TABLES_POSITION; -- Execute apenas se o índice existir

-- Passo 4: Adicionar constraint UNIQUE na coluna NAME
-- Primeiro, verifique se já não existe duplicatas
-- Se existir, corrija manualmente antes de executar esta migração
ALTER TABLE RESTAURANT_TABLES ADD CONSTRAINT UK_TABLE_NAME UNIQUE(NAME);

-- ==========================================
-- Verificação pós-migração:
-- ==========================================
-- Execute os seguintes comandos para verificar se a migração foi bem-sucedida:
-- SELECT RDB$RELATION_NAME, RDB$FIELD_NAME FROM RDB$RELATION_FIELDS WHERE RDB$RELATION_NAME = 'RESTAURANT_TABLES';
-- SELECT RDB$CONSTRAINT_NAME, RDB$CONSTRAINT_TYPE FROM RDB$RELATION_CONSTRAINTS WHERE RDB$RELATION_NAME = 'RESTAURANT_TABLES';

