CREATE TABLE vault_recovery_questions (
    user_id INTEGER NOT NULL REFERENCES vault_profiles(user_id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 3),
    question TEXT NOT NULL,
    answer_hash TEXT NOT NULL,
    PRIMARY KEY (user_id, position)
);
