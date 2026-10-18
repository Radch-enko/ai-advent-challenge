# GitHub App reviewer setup

This guide runs a private GitHub App on your Mac in Docker. GitHub sends PR webhooks
through ngrok. The app reviews repositories selected during installation; it does not
need a workflow in those repositories. Keep Docker and ngrok running while testing.

## 1. Prepare the tunnel and local secrets

Start ngrok first to obtain a public HTTPS URL:

```sh
ngrok http 8080
```

The GitHub webhook URL will be `https://YOUR-NGROK-HOST/webhook`. The local service
can be started after App registration. Copy `.env.example` to `.env` in the Code
Assistance root; fill the values as you complete the next step:

| Variable | Value |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI API key used by the local container. |
| `GITHUB_APP_ID` | Numeric App ID from GitHub App settings. |
| `GITHUB_ACCOUNT_LOGIN` | Your personal GitHub account login. |
| `GITHUB_WEBHOOK_SECRET` | A long random secret; use the same value in GitHub. |
| `GITHUB_APP_PRIVATE_KEY_FILE` | Absolute Mac path to the downloaded `.pem` file. |
| `REVIEWER_HTTP_MAX_ATTEMPTS` | Total attempts for transient GitHub/OpenAI failures; default `5`, range `1..10`. |
| `REVIEWER_RETRY_BASE_SECONDS` | Initial retry delay; default `1`, range `0.1..60`. |

Keep `.env` and the private key readable only by your account (for example,
`chmod 600 .env /absolute/path/to/github-app.pem`). Neither file belongs in Git or
the Docker image. The service reads `OPENAI_API_KEY` from its process environment;
the Compose `env_file` supplies it. The key is not entered during App installation.

## 2. Register a private GitHub App

In GitHub, open **Settings → Developer settings → GitHub Apps → New GitHub App**.
Choose **Only on this account**, enter the HTTPS webhook URL, enable webhooks, and
set the webhook secret from `.env`. Leave **Setup URL** blank.

Repository permissions:

- **Contents: Read-only** — fetch code and Markdown at exact commits.
- **Pull requests: Read and write** — read PR files and publish formal reviews.

Subscribe to the **Pull request** event. Create the App, copy its numeric App ID to
`.env`, and generate/download one private key. Save the `.pem` **outside this
repository** and set its absolute path in `.env`.

Install the App into your personal account and select only the repositories to
review. The reviewer accepts PRs whose base repository belongs to
`GITHUB_ACCOUNT_LOGIN`, including PRs from forks when GitHub exposes the head
snapshot to the App. Draft PRs are skipped until `ready_for_review`.

## 3. Start the container

From the Code Assistance root, run:

```sh
docker compose up --build -d
docker compose logs -f reviewer
```

The service listens on `127.0.0.1:8080` on the Mac. Check
`http://127.0.0.1:8080/health`. If you later change `.env`, restart with
`docker compose up -d --force-recreate`. If ngrok assigns a new URL, update the
Webhook URL in GitHub App settings. There is no Setup URL.

## 4. Review behavior and branch rules

For each non-draft PR open, reopen, update, or ready event, the service reads the PR
diff, Markdown rules at the base SHA, and safe text files at the head SHA. It sends
selected excerpts and diff to the configured OpenAI endpoint. The review response
uses a strict JSON Schema; findings are then checked against changed lines before
GitHub receives the review. Blocking
findings produce `REQUEST_CHANGES`; otherwise the service uses `APPROVE`. API,
indexing, model, safety-limit, and stale-SHA failures do not produce approval.
The reviewer uses a dedicated role prompt to check correctness, regressions, edge
cases, error handling, architecture, style, and repository guidance. It indexes
`.md` files from the base commit and gives likely rule documents priority in RAG
retrieval. Rule documents are detected from names, directories such as
`.agents/skills/` and `.github/instructions/`, and Markdown headings. For each
changed file, retrieval selects up to 30 excerpts from the Markdown index and up
to 30 code excerpts by similarity; matching rule documents rank ahead of other
Markdown excerpts.
The model receives the exact allowed changed-line anchors and their `LEFT`/`RIGHT`
sides. If a generated draft violates review-field or anchor validation, the service
requests up to three corrected drafts and validates each one again. If all four
drafts fail validation, no review is published.

To make formal reviews affect merging, configure a branch protection rule or
ruleset in the target repository that requires PR reviews. GitHub determines which
reviewers count under that rule. Verify the App's behavior in a disposable test PR;
an API response alone does not prove that the review blocks or permits merge.

## 5. Test and troubleshoot

1. Open a **draft** test PR in an installed repository. Confirm no review appears.
2. Mark it **Ready for review**. Confirm inline comments, summary, and formal verdict.
3. Push a new commit and confirm a new review targets the new SHA. Redeliver the same
   webhook from **App settings → Advanced → Recent Deliveries** and confirm no
   duplicate review appears for that SHA.
4. Test one PR with a clear blocking defect and one without. With a review rule
   enabled, inspect whether `REQUEST_CHANGES` blocks merge and a later `APPROVE`
   allows it under your repository settings.

To prepare a stored PR task for webhook redelivery, build the image once so the
reset command is installed, then run it in a one-off container sharing the reviewer's
data volume:

```sh
docker compose build reviewer
docker compose run --rm --no-deps reviewer code-assistance-review-reset \
  --repository Radch-enko/ai-advent-challenge --pr 1
```

The command selects the newest stored task for that repository and PR and prints
its head and base SHAs. Pass `--head-sha` and optionally `--base-sha` to select a
specific commit pair. It marks only that local task retryable and preserves webhook
delivery records, so the original delivery can be redelivered from **App settings
→ Advanced → Recent Deliveries**. A currently running task cannot be reset. If a
review was already published for the same commit, the service will see its marker
on GitHub and skip another model run; removing the local task status alone does not
remove that marker.

Inspect `docker compose logs reviewer` for failures. `/data/review_jobs.sqlite3`
and `/data/indexes/` live in the `reviewer_data` Docker volume; remove neither while
investigating a retry. Failed jobs can be retried by redelivering the webhook.
Completed groups of files are committed to SQLite after embedding. If the container
stops during indexing, a retry reuses those files when their content digests and
embedding settings still match. The temporary repository snapshots are fetched
again; up to six GitHub blobs are fetched concurrently. An interrupted group may
need embedding again, and changing the embedding model rebuilds the index.
The logs show `stage=` for the current step and `files=done/total` while preparing
snapshots and indexing rules or code. The counters do not expose file contents.
Temporary connection errors, timeouts, rate limits, and HTTP `408`, `409`, `429`,
and selected `5xx` responses are retried with bounded exponential backoff and
jitter. Every retry is logged with the operation, attempt, and delay. Permanent
authentication, permission, validation, and other `4xx` failures fail immediately.
If publishing a review returns an ambiguous network error, the service first looks
for the review's unique marker before repeating the write.
The service logs the OpenAI endpoint and a data-sharing warning before API work.
After a review is successfully published, it writes one `REVIEW_AUDIT` JSON record
to the container log. The record contains the exact model instructions, complete
prompt, response schema, returned model text, verdict and findings, plus every
retrieved chunk with its path, line range, similarity score, text, and the changed
files whose retrieval query selected it. It also records each exact retrieval
query and the embedding model, dimensions, similarity threshold, and top-k setting.
Each finding lists all chunks and diff files available in the shared prompt; this
is input provenance, not a claim that the model relied on each listed chunk. The
record is JSON-escaped on one line.
These logs can contain private source code and should be handled like repository
data. They never contain API keys or GitHub App private-key contents.

### Review input and output limits

These are application limits in addition to the limits imposed by the selected
OpenAI model and GitHub API:

| Input or output | Application behavior |
| --- | --- |
| PR diff | Up to 100,000 characters across all returned patches; missing or incomplete patches fail the review. |
| User input sent to the review model | Up to 360,000 characters, including all diffs, retrieved context, anchor guide, and any validation correction. The separately sent system instructions and response schema are not included in this count. This is characters, not tokens. |
| Retrieval query | One query per changed file, containing the path and at most the first 1,200 patch characters. |
| Retrieved chunks | Up to 30 Markdown rule chunks and 30 code chunks per changed file, then deduplicated across the PR. The reviewer's fixed value is 30; `[index].top_k` controls CLI search and does not change this. Chunks below `[index].minimum_similarity` (default `0.25`) are excluded. |
| Chunk text | At most 2,000 characters per indexed chunk, with up to 200 characters of overlap. |
| Snapshot | At most 10,000 included files and 100,000,000 bytes total in each base-rules and PR-code snapshot. Per-file limit is `[index].max_file_bytes`, default 1,048,576 bytes and maximum 10,485,760 bytes. Oversized files are skipped from the snapshot; an oversized changed code file prevents a complete review. |
| Findings and comment text | No application-level maximum finding count, summary length, or finding body length. The schema has no `maxItems` or `maxLength`. The provider/model output-token limits and GitHub review limits can still reject very large output. |
| Retry and timeout limits | Up to 3 correction requests after the first invalid model response (4 generation attempts total). Each transient HTTP operation has up to 5 attempts. OpenAI request timeout defaults to 60 seconds and is configurable up to 300 seconds. |

The analysis sends one shared prompt containing the full PR diff and all selected
chunks. The model does not return a reliable per-finding attribution to specific
chunks, so the audit can show what evidence was available and which query selected
it, but cannot establish which passage caused a particular finding.

The GitHub App currently uses GitHub's hosted API. Files omitted from GitHub's PR
patch or a truncated repository tree cause a failed review rather than an approval.
