import json
import logging
from pathlib import Path

from code_assistance.config import load_config
from code_assistance.review_analysis import REVIEW_RESPONSE_SCHEMA, ReviewAnalyzer
from code_assistance.review_service import ReviewService
from code_assistance.review_state import ReviewJob, ReviewJobStore
from tests.conftest import FakeEmbeddings
from tests.test_reviewer import BASE_SHA, HEAD_SHA, FakeChat, FakeGitHub


def test_successful_publication_logs_complete_model_request_and_retrieved_chunks(
    tmp_path: Path, caplog
) -> None:
    github = FakeGitHub()
    chat = FakeChat(
        json.dumps(
            {
                "summary": "Ошибка в расчёте оплаты.",
                "findings": [
                    {
                        "path": "payment.py",
                        "line": 1,
                        "side": "RIGHT",
                        "category": "bug",
                        "blocking": True,
                        "body": "Результат неверен.",
                    }
                ],
            }
        )
    )
    config = load_config(tmp_path / "missing-config.toml")
    analyzer = ReviewAnalyzer(config, FakeEmbeddings(), chat, tmp_path / "indexes")
    service = ReviewService(
        lambda _: github,
        analyzer,
        ReviewJobStore(tmp_path / "jobs.sqlite3"),
        config.max_file_bytes,
    )  # type: ignore[arg-type]

    with caplog.at_level(logging.INFO, logger="code_assistance.review_service"):
        service.process(ReviewJob(12, 34, "owner/project", 5, HEAD_SHA, BASE_SHA))

    audit_record = next(record for record in caplog.records if "REVIEW_AUDIT " in record.message)
    encoded_payload = audit_record.message.split("REVIEW_AUDIT ", maxsplit=1)[1]
    payload = json.loads(encoded_payload)
    assert "\n" not in audit_record.message
    assert len(github.reviews) == 1  # The audit follows successful publication.
    assert payload["request"]["instructions"].startswith("You are a senior software engineer")
    assert "FILE payment.py" in payload["request"]["input"]
    assert "return 2" in payload["request"]["input"]
    assert payload["request"]["text"]["format"]["schema"] == REVIEW_RESPONSE_SCHEMA
    assert payload["changed_files_in_diff"] == ["payment.py"]
    assert payload["retrieval"]["queries"][0]["changed_file"] == "payment.py"
    assert "@@ -1 +1 @@" in payload["retrieval"]["queries"][0]["text"]
    assert any(chunk["path"] == "architecture/rules.md" for chunk in payload["retrieved_chunks"])
    finding = payload["result"]["findings"][0]
    assert finding["available_context_chunk_ids"] == [
        chunk["id"] for chunk in payload["retrieved_chunks"]
    ]
    assert finding["available_diff_files"] == ["payment.py"]
    assert payload["raw_response"] == chat.result
