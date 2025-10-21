-- Migration: Add NOTES column to CART_ITEMS
-- Date: 2025-10-21

-- Safety check: only add if not exists (Firebird lacks IF NOT EXISTS for columns; attempt and ignore error)
ALTER TABLE CART_ITEMS ADD NOTES BLOB SUB_TYPE TEXT;

-- Optional: create index if you plan to filter by notes (usually not needed)
-- CREATE INDEX IDX_CART_ITEMS_NOTES ON CART_ITEMS COMPUTED BY (CAST(NOTES AS VARCHAR(80)));


