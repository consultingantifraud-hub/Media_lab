-- Migration 006: Create ai_assistant_questions table for logging AI assistant questions
CREATE TABLE IF NOT EXISTS ai_assistant_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer TEXT,
    error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_ai_assistant_questions_user_id ON ai_assistant_questions(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_assistant_questions_created_at ON ai_assistant_questions(created_at);




