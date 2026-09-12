from pathlib import Path
import json
import re


BASE_DIR = Path(__file__).resolve().parents[1]

ATTACHMENTS_FILE = (
    BASE_DIR
    / "data"
    / "attachments"
    / "attachments.json"
)


CALIBRATION_CASES = {
    "CAL-091": {
        "attachment": "oblachny-sad-decision-cases-partial-refund",
        "keywords": [
            "статус",
            "публика",
        ],
    },
    "CAL-092": {
        "attachment": "oblachny-sad-source-contracts-event-delta",
        "keywords": [
            "Purpose",
            "Rule",
        ],
    },
    "CAL-093": {
        "attachment": "oblachny-sad-decision-cases-timezone",
        "keywords": [
            "Рабочий порядок",
        ],
    },
    "CAL-094": {
        "attachment": "oblachny-sad-source-contracts-reconciliation",
        "keywords": [
            "Контекст для обсуждения",
        ],
    },
    "CAL-095": {
        "attachment": "oblachny-sad-decision-cases-full-refund",
        "keywords": [
            "Контроль",
            "Эскалация",
        ],
    },
    "CAL-096": {
        "attachment": "oblachny-sad-dimension-specs-quality-state",
        "keywords": [
            "control_code",
            "status",
            "note",
        ],
    },
    "CAL-097": {
        "attachment": "oblachny-sad-source-contracts-permissions",
        "keywords": [
            "reporting",
            "quality_checks",
        ],
    },
    "CAL-098": {
        "attachment": "mozaika-decision-cases-audience-spike",
        "keywords": [
            "publication_status",
        ],
    },
    "CAL-099": {
        "attachment": "mahoviq-dimension-specs-lifecycle",
        "keywords": [
            "PublicationGate",
            "Status",
        ],
    },
    "CAL-100": {
        "attachment": "oblachny-sad-source-contracts-retention",
        "keywords": [
            "publication_gate_example",
        ],
    },
}


def normalize(value: str) -> str:
    """Упрощаем текст для поиска."""
    value = value.lower()
    value = value.replace("ё", "е")
    value = re.sub(r"\s+", " ", value)
    return value


def load_attachments():
    if not ATTACHMENTS_FILE.exists():
        raise FileNotFoundError(
            f"Не найден файл:\n{ATTACHMENTS_FILE}"
        )

    with ATTACHMENTS_FILE.open(
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    return data.get("attachments", [])


def find_attachment(attachments, identifier):
    """
    Ищем attachment по имени файла.
    """
    identifier = normalize(identifier)

    matches = []

    for item in attachments:
        path = normalize(
            item.get("attachment_path", "")
        )

        if identifier in path:
            matches.append(item)

    return matches


def check_case(case_id, case, attachments):
    matches = find_attachment(
        attachments,
        case["attachment"]
    )

    if not matches:
        return {
            "status": "NOT_FOUND",
            "reason": "Attachment не найден",
        }

    if len(matches) > 1:
        # Обычно это не ошибка, но покажем оператору.
        item = matches[0]
    else:
        item = matches[0]

    text = item.get("text", "")
    normalized_text = normalize(text)

    if not text.strip():
        return {
            "status": "EMPTY",
            "path": item.get("attachment_path"),
            "reason": "Из attachment не извлечён текст",
        }

    missing_keywords = []

    for keyword in case["keywords"]:
        if normalize(keyword) not in normalized_text:
            missing_keywords.append(keyword)

    if missing_keywords:
        return {
            "status": "PARTIAL",
            "path": item.get("attachment_path"),
            "format": item.get("attachment_format"),
            "parser": item.get("parser"),
            "ocr_used": item.get("ocr_used"),
            "text_length": item.get("text_length"),
            "missing_keywords": missing_keywords,
        }

    return {
        "status": "PASS",
        "path": item.get("attachment_path"),
        "format": item.get("attachment_format"),
        "parser": item.get("parser"),
        "ocr_used": item.get("ocr_used"),
        "confidence": item.get("confidence"),
        "text_length": item.get("text_length"),
    }


def main():
    print("=" * 70)
    print("ATTACHMENT CALIBRATION VALIDATION")
    print("=" * 70)

    attachments = load_attachments()

    print(f"\nAttachments loaded: {len(attachments)}")
    print()

    results = {}

    passed = 0
    partial = 0
    failed = 0

    for case_id, case in CALIBRATION_CASES.items():

        result = check_case(
            case_id,
            case,
            attachments
        )

        results[case_id] = result

        status = result["status"]

        if status == "PASS":
            passed += 1
            symbol = "✓"

        elif status == "PARTIAL":
            partial += 1
            symbol = "!"

        else:
            failed += 1
            symbol = "✗"

        print(
            f"{symbol} {case_id}: {status}"
        )

        if result.get("path"):
            print(
                f"    file: {result['path']}"
            )

        if result.get("format"):
            print(
                f"    format: {result['format']}"
            )

        if result.get("parser"):
            print(
                f"    parser: {result['parser']}"
            )

        if result.get("ocr_used"):
            print(
                f"    OCR: YES"
            )

        if result.get("text_length") is not None:
            print(
                f"    text length: "
                f"{result['text_length']}"
            )

        if result.get("missing_keywords"):
            print(
                f"    missing: "
                f"{', '.join(result['missing_keywords'])}"
            )

        if result.get("reason"):
            print(
                f"    reason: "
                f"{result['reason']}"
            )

        print()

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(f"PASS:    {passed}")
    print(f"PARTIAL: {partial}")
    print(f"FAILED:  {failed}")

    output_file = (
        BASE_DIR
        / "data"
        / "attachments"
        / "calibration_results.json"
    )

    with output_file.open(
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            {
                "total": len(CALIBRATION_CASES),
                "passed": passed,
                "partial": partial,
                "failed": failed,
                "results": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print(
        f"Results saved to:\n{output_file}"
    )

    if failed > 0:
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())