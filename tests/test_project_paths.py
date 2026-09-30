import importlib.util
import json
from pathlib import Path
import shutil


def test_coingecko_cleaner_finds_project_data_from_another_directory(tmp_path, monkeypatch):
    project = tmp_path / "project"
    script = project / "src/transformers/clean_coingecko_market_chart.py"
    script.parent.mkdir(parents=True)
    source = Path(__file__).resolve().parents[1] / "src/transformers/clean_coingecko_market_chart.py"
    shutil.copyfile(source, script)
    raw_path = project / "data/raw/coingecko_market_chart_raw.json"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text(json.dumps({
        "BTCUSDT": {"coingecko_id": "bitcoin", "data": {
            "prices": [[1704067200000, 42000]],
            "market_caps": [[1704067200000, 820000000000]],
            "total_volumes": [[1704067200000, 25000000000]],
        }}
    }))
    unrelated = tmp_path / "editor-working-directory"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    spec = importlib.util.spec_from_file_location("isolated_cleaner", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.clean_coingecko_market_chart()

    assert result["coingecko_price_usd"].tolist() == [42000]
    assert (project / "data/processed/coingecko_market_chart_clean.csv").is_file()
    assert not (unrelated / "data").exists()
