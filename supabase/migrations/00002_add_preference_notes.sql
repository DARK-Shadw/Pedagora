-- Add free-text note columns to user_preferences
-- These supplement the existing ENUM card selections with optional user elaboration

ALTER TABLE user_preferences
  ADD COLUMN learning_style_note TEXT NOT NULL DEFAULT '',
  ADD COLUMN content_depth_note TEXT NOT NULL DEFAULT '',
  ADD COLUMN teaching_style_note TEXT NOT NULL DEFAULT '',
  ADD COLUMN assessment_type_note TEXT NOT NULL DEFAULT '',
  ADD COLUMN education_level_note TEXT NOT NULL DEFAULT '';
