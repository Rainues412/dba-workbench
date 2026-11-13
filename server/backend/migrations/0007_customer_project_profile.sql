-- NULL means the existing customer fields are still the source of truth.
-- Keep the legacy columns and related records intact for upgrades and imports.
ALTER TABLE customers ADD COLUMN project_profile TEXT
    CHECK (project_profile IS NULL OR (json_valid(project_profile) AND json_type(project_profile) = 'object'));
