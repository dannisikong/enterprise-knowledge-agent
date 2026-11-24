#!/usr/bin/env python3
"""Run low-volume, non-destructive smoke and isolation checks against production.

This script uses only Python's standard library. It creates two temporary demo
sessions and one uniquely named TXT document. The application currently has no
single-document delete endpoint, so the test data remains isolated in its test
session until the normal 24-hour session expiry cleanup removes it.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = os.getenv(
    "BASE_URL",
    "https://enterprise-knowledge-agent-main.onrender.com",
).rstrip("/")
TIMEOUT_SECONDS = 25
REPORT_PATH = Path("production-smoke-report.json")


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> tuple[int, Any]:
        headers = {"Accept": "application/json"}
        if token:
            headers["X-Session-Token"] = token
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                status = response.status
                raw = response.read()
        except HTTPError as error:
            status = error.code
            raw = error.read()
        except (URLError, TimeoutError) as error:
            raise RuntimeError(f"Request failed ({type(error).__name__}).") from None

        if not raw:
            return status, None
        try:
            return status, json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return status, None


def multipart_file(filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = f"----ProductionSmoke{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


def main() -> int:
    if not BASE_URL.startswith("https://"):
        print("Refusing to run: BASE_URL must use HTTPS.", file=sys.stderr)
        return 2

    client = ApiClient(BASE_URL)
    results: list[dict[str, str]] = []
    context: dict[str, Any] = {}
    marker = f"production smoke verification {uuid.uuid4().hex}"

    def check(name: str, action) -> None:
        try:
            action()
            results.append({"name": name, "status": "passed", "detail": "Passed"})
            print(f"PASS  {name}")
        except Exception as error:
            detail = str(error).replace("\n", " ")[:240]
            results.append({"name": name, "status": "failed", "detail": detail})
            print(f"FAIL  {name}: {detail}")

    def health_check() -> None:
        status, payload = client.request("GET", "/health")
        assert status == 200, f"Expected HTTP 200, received {status}"
        assert isinstance(payload, dict) and payload.get("status") == "ok", "Health payload is not healthy"

    def create_test_sessions() -> None:
        created = []
        for _ in range(2):
            status, payload = client.request("POST", "/session")
            assert status == 200, f"Session creation returned HTTP {status}"
            assert isinstance(payload, dict), "Session response is not JSON"
            assert payload.get("session_id") and payload.get("token"), "Session response is incomplete"
            created.append(payload)
            time.sleep(1)
        context["session_a"] = created[0]
        context["session_b"] = created[1]

    def upload_valid_document() -> None:
        session = context.get("session_a")
        assert session, "Test Session A was not created"
        filename = f"production-smoke-{uuid.uuid4().hex[:12]}.txt"
        body, content_type = multipart_file(filename, (marker + "\nThis is an isolated production smoke-test document.").encode())
        status, payload = client.request(
            "POST", "/documents", token=session["token"],
            body=body, content_type=content_type,
        )
        assert status == 200, f"Valid TXT upload returned HTTP {status}"
        assert isinstance(payload, dict) and payload.get("id"), "Upload response has no document ID"
        context["document_id"] = payload["id"]

    def verify_document_list_isolation() -> None:
        document_id = context.get("document_id")
        assert document_id, "Test document was not uploaded"
        for label in ("session_a", "session_b"):
            session = context[label]
            status, payload = client.request("GET", "/documents", token=session["token"])
            assert status == 200, f"{label} document list returned HTTP {status}"
            assert isinstance(payload, list), f"{label} document list is not an array"
            contains_document = any(item.get("id") == document_id for item in payload if isinstance(item, dict))
            expected = label == "session_a"
            assert contains_document == expected, f"{label} document ownership check failed"

    def verify_document_detail_isolation() -> None:
        document_id = context.get("document_id")
        assert document_id, "Test document was not uploaded"
        owner_status, owner_payload = client.request(
            "GET", f"/documents/{document_id}/text",
            token=context["session_a"]["token"],
        )
        assert owner_status == 200, f"Owner document detail returned HTTP {owner_status}"
        assert isinstance(owner_payload, dict) and marker in owner_payload.get("extracted_text", ""), "Owner cannot read uploaded test text"

        other_status, _ = client.request(
            "GET", f"/documents/{document_id}/text",
            token=context["session_b"]["token"],
        )
        assert other_status == 404, f"Non-owner document access returned HTTP {other_status}, expected 404"

    def verify_search_isolation() -> None:
        query = {"query": marker, "limit": 5, "mode": "keyword"}
        encoded = json.dumps(query).encode("utf-8")
        status_a, payload_a = client.request(
            "POST", "/search", token=context["session_a"]["token"],
            body=encoded, content_type="application/json",
        )
        assert status_a == 200, f"Owner search returned HTTP {status_a}"
        results_a = payload_a.get("results", []) if isinstance(payload_a, dict) else []
        assert any(marker in str(item) for item in results_a), "Owner search did not retrieve its own test document"

        status_b, payload_b = client.request(
            "POST", "/search", token=context["session_b"]["token"],
            body=encoded, content_type="application/json",
        )
        assert status_b == 200, f"Non-owner search returned HTTP {status_b}"
        results_b = payload_b.get("results", []) if isinstance(payload_b, dict) else []
        assert not any(marker in str(item) for item in results_b), "Non-owner search exposed another session's test content"

    def verify_invalid_file_rejected() -> None:
        body, content_type = multipart_file("production-smoke-invalid.exe", b"not an allowed document")
        status, _ = client.request(
            "POST", "/documents", token=context["session_a"]["token"],
            body=body, content_type=content_type,
        )
        assert status == 400, f"Unsupported extension returned HTTP {status}, expected 400"

    def verify_malformed_docx_rejected() -> None:
        body, content_type = multipart_file("production-smoke-malformed.docx", b"not a valid DOCX archive")
        status, _ = client.request(
            "POST", "/documents", token=context["session_a"]["token"],
            body=body, content_type=content_type,
        )
        assert status == 400, f"Malformed DOCX returned HTTP {status}, expected 400"

    check("Health endpoint", health_check)
    check("Create two isolated test sessions", create_test_sessions)

    if "session_a" in context and "session_b" in context:
        check("Upload a small TXT test document", upload_valid_document)

    if "document_id" in context:
        check("Document list is isolated by session", verify_document_list_isolation)
        check("Document detail is isolated by session", verify_document_detail_isolation)
        check("Keyword search is isolated by session", verify_search_isolation)

    if "session_a" in context:
        check("Unsupported file extension is rejected", verify_invalid_file_rejected)
        check("Malformed DOCX is rejected", verify_malformed_docx_rejected)

    passed = sum(item["status"] == "passed" for item in results)
    failed = len(results) - passed
    report = {
        "base_url": BASE_URL,
        "created_test_sessions": 2 if "session_a" in context and "session_b" in context else len(context),
        "test_document_created": bool(context.get("document_id")),
        "cleanup": "Test session data expires after 24 hours and is removed by the application's expiry cleanup; no existing user data is modified.",
        "summary": {"passed": passed, "failed": failed, "total": len(results)},
        "tests": results,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        lines = [
            "## Production smoke test results",
            f"- Target: {BASE_URL}",
            f"- Result: {passed} passed / {failed} failed",
            f"- Test data cleanup: {report['cleanup']}",
            "",
            "| Test | Result | Detail |",
            "|---|---|---|",
        ]
        for item in results:
            lines.append(f"| {item['name']} | {item['status']} | {item['detail'].replace('|', '/')} |")
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("\n".join(lines) + "\n")

    print(f"\nResult: {passed} passed, {failed} failed.")
    print("A JSON report was written to production-smoke-report.json.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
