# Data Modeling Rules

## Preserving Existing Tables
- Never drop or truncate existing tables: `research_sessions`, `sources`, `claims`, `cache`.
- Apply non-destructive migrations using `ALTER TABLE ... ADD COLUMN` or `CREATE TABLE IF NOT EXISTS`.

## Core Entities & Registry Schema
1. `registry_sources`:
   - `id`, `name`, `domain_category`, `subcategory`, `base_url`, `allowed_paths`, `type`, `crawl_method`, `robots_status`, `last_checked`, `reachability`, `trust_score`, `trust_reasons`, `language`, `region`, `owner`, `notes`.
2. `crawl_jobs`:
   - `id`, `category`, `domain`, `status` (`pending`, `running`, `completed`, `failed`), `progress_pct`, `processed_count`, `total_count`, `error`, `created_at`, `updated_at`.
3. `entities`:
   - `id`, `name`, `normalized_name`, `entity_type` (exam, college, scheme, scholarship, job, grant, course), `domain_category`, `subcategory`, `issuing_body`, `region`, `created_at`.
4. `entity_attributes`:
   - `id`, `entity_id`, `attribute_name`, `attribute_value`, `exact_quote`, `source_id`, `verified` (BOOLEAN), `uncertain` (BOOLEAN), `created_at`.
5. `entity_sources`:
   - `id`, `entity_id`, `source_id`, `linked_at`.

## FTS5 Full-Text Search
- Full-text index `entities_fts` indexing `name`, `domain_category`, `subcategory`, `issuing_body`, and concatenated attribute values for instant multi-field search.
