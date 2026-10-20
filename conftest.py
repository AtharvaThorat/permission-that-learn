"""Default test runs cannot contact endpoints or initialize model workers."""
import pytest


def pytest_addoption(parser):
    parser.addoption('--run-model-backed', action='store_true', default=False)


def pytest_collection_modifyitems(config, items):
    if not config.getoption('--run-model-backed'):
        selected = [i for i in items if 'model_backed' not in i.keywords]
        config.hook.pytest_deselected(items=[i for i in items if i not in selected])
        items[:] = selected


@pytest.fixture(autouse=True)
def offline_cpu_tests(monkeypatch, request):
    if request.config.getoption('--run-model-backed'):
        return
    import socket
    def forbidden(*a, **kw):
        raise AssertionError('Network/model operation forbidden in CPU tests')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setenv('HF_HUB_OFFLINE','1')
    monkeypatch.setenv('TRANSFORMERS_OFFLINE','1')
    from gatekeeper.laya_adapter import LayaBackend
    monkeypatch.setattr(LayaBackend, 'initialize', forbidden)
