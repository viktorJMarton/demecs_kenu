BEGIN TRANSACTION;

ALTER TABLE tour_locations
    ADD COLUMN description TEXT;

-- Optional: initialize with empty strings for existing rows
UPDATE tour_locations
   SET description = NULL
 WHERE description = '';

COMMIT;
