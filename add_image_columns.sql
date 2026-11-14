-- Migration script to add image_data and mime_type columns to tour_images table
-- Run this with: sqlite3 kajak_kenu.db < add_image_columns.sql

-- Add image_data column
ALTER TABLE tour_images ADD COLUMN image_data TEXT;

-- Add mime_type column  
ALTER TABLE tour_images ADD COLUMN mime_type TEXT;

-- Verify changes
.schema tour_images
