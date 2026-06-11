-- Migration: add new fields to items table
-- Run once against your existing database.
-- Safe to re-run: each statement uses IF NOT EXISTS / DO NOTHING patterns.

ALTER TABLE items ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'active';
ALTER TABLE items ADD COLUMN IF NOT EXISTS manufactured_date VARCHAR;
ALTER TABLE items ADD COLUMN IF NOT EXISTS condition_notes VARCHAR;
ALTER TABLE items ADD COLUMN IF NOT EXISTS borrowed_by_email VARCHAR;
ALTER TABLE items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();

-- Migrate existing `retired` boolean → status column (if retired column exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='items' AND column_name='retired'
    ) THEN
        UPDATE items SET status = 'retired' WHERE retired = TRUE AND status = 'active';
    END IF;
END $$;

-- tag: widen from integer to varchar to support leading-zero strings like "001"
-- Only runs if tag column is still integer type
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='items' AND column_name='tag'
        AND data_type IN ('integer', 'bigint')
    ) THEN
        ALTER TABLE items ALTER COLUMN tag TYPE VARCHAR USING LPAD(tag::text, 3, '0');
    END IF;
END $$;

-- Migration: add category column to items table
ALTER TABLE items ADD COLUMN IF NOT EXISTS category VARCHAR;
