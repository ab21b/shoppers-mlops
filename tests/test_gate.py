import hashlib

import pytest

from shoppers.train import decide_promotion, file_md5, parse_max_features


@pytest.mark.parametrize(
    "new, champion, min_gain, expected",
    [
        (0.70, None, 0.005, True),      # champion еще нет: первая версия проходит
        (0.70, 0.75, 0.005, False),     # хуже champion
        (0.752, 0.75, 0.005, False),    # лучше, но меньше запаса: это шум
        (0.755, 0.75, 0.005, False),   
        (0.756, 0.75, 0.005, True),     
        (0.75, 0.75, 0.0, False),      
    ],
)
def test_decide_promotion(new, champion, min_gain, expected):
    assert decide_promotion(new, champion, min_gain) is expected


def test_file_md5_matches_hashlib(tmp_path):
    f = tmp_path / "data.csv"
    f.write_bytes(b"a,b\n1,2\n")
    assert file_md5(f) == hashlib.md5(b"a,b\n1,2\n").hexdigest()


def test_data_md5_matches_dvc_pointer_when_data_present():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    dvc_file, csv = root / "data" / "online_shoppers_intention.csv.dvc", root / "data" / "online_shoppers_intention.csv"
    if not (dvc_file.exists() and csv.exists()):
        pytest.skip("данных нет (CI) или они ещё не под DVC")
    declared = re.search(r"md5:\s*([0-9a-f]{32})", dvc_file.read_text()).group(1)
    assert file_md5(csv) == declared, "CSV изменен, но не зафиксирован: выполните `dvc add` и закоммитьте .dvc"


def test_parse_max_features():
    assert parse_max_features("sqrt") == "sqrt"
    assert parse_max_features("0.5") == 0.5
