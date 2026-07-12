DROP INDEX messages_person_id_idx;
ALTER TABLE messages DROP COLUMN person_id;
DROP TABLE people;
