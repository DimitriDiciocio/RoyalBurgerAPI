-- =====================================================
-- MIGRATION: Adicionar campo CREATED_AT na tabela PRODUCTS
-- Data: 2024
-- Descrição: Adiciona campo de data de criação para permitir filtro preciso de novidades
-- =====================================================

-- Adicionar campo CREATED_AT na tabela PRODUCTS
ALTER TABLE PRODUCTS ADD CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Atualizar registros existentes com data de criação baseada no ID (aproximação)
-- Produtos com ID menor recebem data mais antiga (30 dias atrás - ID*1 minuto)
UPDATE PRODUCTS 
SET CREATED_AT = DATEADD(MINUTE, -ID, CURRENT_TIMESTAMP - 30)
WHERE CREATED_AT IS NULL;

-- Criar índice para melhorar performance da query de novidades
-- ALTERAÇÃO: Firebird não suporta DESC no CREATE INDEX; o índice pode ser usado em ambas direções
CREATE INDEX IDX_PRODUCTS_CREATED_AT ON PRODUCTS (CREATED_AT);

COMMIT;
