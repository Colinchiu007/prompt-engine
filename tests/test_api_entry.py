"""prompt_engine.api 入口端口解析 — PORT 环境变量必须优先于 config.yaml

回归背景：BasePythonBridge 以 `PORT` 环境变量下发端口（与 splitter/server.py 约定一致），
但 prompt_engine.api 此前只读 config.yaml server.port，导致 PROMPT_PORT 覆盖失效、
多实例隔离端口时绑定冲突 / 健康检查超时（图片轮播流水线卡在提示词优化阶段）。
"""
import pytest


@pytest.fixture(autouse=True)
def _isolate_main(monkeypatch):
    """每个用例独立替换入口模块的 uvicorn.run 与 load_config，避免真实启动服务。"""
    import prompt_engine.api.__main__ as main_module

    calls = {}

    def fake_uvicorn_run(app, **kwargs):
        calls.update(kwargs)

    monkeypatch.setattr(main_module.uvicorn, "run", fake_uvicorn_run)
    monkeypatch.setattr(
        main_module,
        "load_config",
        lambda: {"server": {"host": "0.0.0.0", "port": 8013, "log_level": "info"}},
    )
    return main_module, calls


def test_api_main_port_prefers_port_env(monkeypatch, _isolate_main):
    main_module, calls = _isolate_main
    monkeypatch.setenv("PORT", "8014")
    main_module.main()
    assert calls["port"] == 8014
    assert calls["host"] == "0.0.0.0"


def test_api_main_port_falls_back_to_config(monkeypatch, _isolate_main):
    main_module, calls = _isolate_main
    monkeypatch.delenv("PORT", raising=False)
    main_module.main()
    assert calls["port"] == 8013


def test_api_main_port_invalid_env_fails_fast(monkeypatch, _isolate_main):
    main_module, _ = _isolate_main
    monkeypatch.setenv("PORT", "not-a-port")
    with pytest.raises(ValueError):
        main_module.main()
