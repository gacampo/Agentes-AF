"""Tests de utils/llm.py: prompt caching, web search tool, y reintentos.

No llaman a la API real — se mockea client.messages.stream a nivel del SDK.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import anthropic
import httpx
import pytest

from utils import llm


class FakeStream:
    """Doble mínimo del context manager que retorna client.messages.stream()."""

    def __init__(self, text_chunks, usage):
        self._chunks = text_chunks
        self._usage = usage

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def text_stream(self):
        return iter(self._chunks)

    def get_final_message(self):
        m = MagicMock()
        m.usage = self._usage
        return m


def make_usage(input_tokens=100, output_tokens=50, cache_read=0, cache_write=0, searches=0):
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.cache_read_input_tokens = cache_read
    usage.cache_creation_input_tokens = cache_write
    stu = MagicMock()
    stu.web_search_requests = searches
    usage.server_tool_use = stu
    return usage


def test_cached_context_arma_bloques_con_cache_control():
    captured = {}
    fake_client = MagicMock()

    def fake_stream_call(**kwargs):
        captured.update(kwargs)
        return FakeStream(["hola ", "mundo"], make_usage(cache_read=500, searches=2))

    fake_client.messages.stream.side_effect = fake_stream_call

    with patch.object(llm, "get_client", return_value=fake_client):
        out = llm.ask(
            "system", "user prompt", cached_context="CONTEXTO GRANDE",
            tools=llm.web_search_tool(max_uses=4),
        )

    assert out == "hola mundo"
    content = captured["messages"][0]["content"]
    assert isinstance(content, list) and len(content) == 2
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    assert content[0]["text"] == "CONTEXTO GRANDE"
    assert content[1] == {"type": "text", "text": "user prompt"}
    assert captured["tools"][0]["type"] == llm.WEB_SEARCH_TOOL_VERSION
    assert captured["tools"][0]["max_uses"] == 4


def test_sin_cached_context_el_contenido_es_string_plano():
    fake_client = MagicMock()
    fake_client.messages.stream.side_effect = lambda **kw: FakeStream(["x"], make_usage())

    with patch.object(llm, "get_client", return_value=fake_client):
        llm.ask("system", "solo user prompt")

    call_kwargs = fake_client.messages.stream.call_args.kwargs
    assert call_kwargs["messages"][0]["content"] == "solo user prompt"
    assert "tools" not in call_kwargs


def test_reintenta_ante_error_transitorio_y_despues_funciona():
    attempts = {"n": 0}

    def flaky_call(**kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise anthropic.APIConnectionError(
                message="boom", request=httpx.Request("POST", "https://api.anthropic.com")
            )
        return FakeStream(["ok"], make_usage())

    fake_client = MagicMock()
    fake_client.messages.stream.side_effect = flaky_call

    with patch.object(llm, "get_client", return_value=fake_client), patch.object(llm.time, "sleep", return_value=None):
        out = llm.ask("system", "user", max_retries=4)

    assert out == "ok"
    assert attempts["n"] == 3


def test_agota_reintentos_y_levanta_runtimeerror():
    def always_fails(**kwargs):
        raise anthropic.RateLimitError(
            message="rate limited",
            response=httpx.Response(429, request=httpx.Request("POST", "https://api.anthropic.com")),
            body=None,
        )

    fake_client = MagicMock()
    fake_client.messages.stream.side_effect = always_fails

    with patch.object(llm, "get_client", return_value=fake_client), patch.object(llm.time, "sleep", return_value=None):
        with pytest.raises(RuntimeError):
            llm.ask("system", "user", max_retries=2)

    assert fake_client.messages.stream.call_count == 2


def test_error_4xx_no_reintenta():
    resp = httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com"))

    def bad_request_call(**kwargs):
        raise anthropic.BadRequestError(message="bad request", response=resp, body=None)

    fake_client = MagicMock()
    fake_client.messages.stream.side_effect = bad_request_call

    with patch.object(llm, "get_client", return_value=fake_client):
        with pytest.raises(anthropic.BadRequestError):
            llm.ask("system", "user")

    assert fake_client.messages.stream.call_count == 1


def test_web_search_tool_helper_arma_dict_correcto():
    tools = llm.web_search_tool(max_uses=8, allowed_domains=["sec.gov"])
    assert tools == [
        {
            "type": llm.WEB_SEARCH_TOOL_VERSION,
            "name": "web_search",
            "max_uses": 8,
            "allowed_domains": ["sec.gov"],
        }
    ]
