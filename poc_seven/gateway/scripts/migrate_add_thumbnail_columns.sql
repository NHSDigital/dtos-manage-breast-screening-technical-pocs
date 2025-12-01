-- Migration: Add thumbnail tracking columns to stored_instances table
-- This migration is idempotent and can be run multiple times safely

-- Add thumbnail_status column if it doesn't exist
ALTER TABLE stored_instances ADD COLUMN thumbnail_status TEXT DEFAULT 'PENDING' CHECK(thumbnail_status IN ('PENDING', 'GENERATED', 'FAILED', 'SKIP'));

-- Add thumbnail_generated_at column if it doesn't exist
ALTER TABLE stored_instances ADD COLUMN thumbnail_generated_at TEXT;

-- Add thumbnail_error column if it doesn't exist
ALTER TABLE stored_instances ADD COLUMN thumbnail_error TEXT;

-- Create index for thumbnail_status for efficient polling
CREATE INDEX IF NOT EXISTS idx_thumbnail_status ON stored_instances(thumbnail_status);
