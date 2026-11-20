"""Test mock end-to-end MUFAKAT Room (demo): handoff mock + konsensus + gates nyata."""

from mufakat.room.demo import run_mock_demo


def test_mock_demo_end_to_end(tmp_path):
    summary = run_mock_demo("Buat REST API todo dengan FastAPI + test + audit",
                            output_dir=tmp_path / "room-mock")
    assert summary["state"] == "FINAL_REVIEW"
    assert summary["consensus"]["decision"] == "mufakat"
    assert summary["gate_verdict"] in ("AMAN", "TIDAK AMAN")
    report = (tmp_path / "room-mock" / "final_report.md").read_text(encoding="utf-8")
    assert "manual_handoff" in report
    assert "MOCK" in report
    assert (tmp_path / "room-mock" / "room" / "room.json").is_file()
    assert (tmp_path / "room-mock" / "room" / "transcript.jsonl").is_file()
