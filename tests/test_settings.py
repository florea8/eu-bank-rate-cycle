from bankcycle.settings import REPO_ROOT, get_settings


def test_defaults(clean_env):
    s = get_settings()
    assert s.pghost == "localhost"
    assert s.pgport == 5432
    assert s.pgdatabase == "bankcycle"
    assert s.sample_mode is False
    assert s.data_dir == REPO_ROOT / "data"


def test_values_are_typed(clean_env):
    clean_env.setenv("PGPORT", "5499")
    clean_env.setenv("SAMPLE_MODE", "TRUE")
    clean_env.setenv("HTTP_TIMEOUT_S", "15")
    clean_env.setenv("LOG_LEVEL", "debug")
    s = get_settings()
    assert s.pgport == 5499
    assert s.sample_mode is True
    assert s.http_timeout_s == 15
    assert s.log_level == "DEBUG"


def test_absolute_data_dir_is_kept(clean_env, tmp_path):
    clean_env.setenv("DATA_DIR", str(tmp_path))
    assert get_settings().data_dir == tmp_path
