import json

from elk_lead_agent.cli import main


def test_cli_run_json(capsys):
    rc = main(["run", "--no-state", "--no-write", "--format", "json"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "projects" in data
    assert data["threshold_lead"] == 60


def test_cli_sources(capsys):
    rc = main(["sources"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ANKÖ" in out or "ANK" in out


def test_cli_run_console_smoke(capsys):
    rc = main(["run", "--no-state", "--no-write"])
    assert rc == 0
    assert "Leads" in capsys.readouterr().out
