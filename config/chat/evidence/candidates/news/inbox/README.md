# Manual weekly news metadata input

For a manual `chat-news-candidates.yml` dispatch, place a JSON array in this
folder and point `metadata_file` to it. Each row may include `published_at`
(ISO date), `publisher`, `title`, the direct publisher article `url`, pinned
`source_sha256`, a curator-written `description` (up to 320 characters), and
short `companies` / `topics` arrays. Do not include any article text, quotes,
paywalled material, private data, or owner approval receipts. The workflow only emits a closed candidate artifact;
review and actual approval happen separately.
