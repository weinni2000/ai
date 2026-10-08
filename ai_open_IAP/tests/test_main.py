import json

from fastapi.testclient import TestClient

from odoo_ai_proxy import main


def test_get_completions_sync_wraps_openai_response(monkeypatch):
    def fake_post_provider(path, payload):
        assert path == "/chat/completions"
        assert payload["messages"][0] == {"role": "system", "content": "Be brief."}
        assert payload["messages"][1] == {"role": "user", "content": "Hello"}
        return {
            "model": "demo",
            "usage": {"prompt_tokens": 2, "completion_tokens": 3},
            "choices": [{"message": {"content": "Hi there"}}],
        }

    monkeypatch.setattr(main, "_post_provider", fake_post_provider)
    client = TestClient(main.app)
    response = client.post(
        "/api/odoo_ai/1/get_completions_sync",
        json={
            "jsonrpc": "2.0",
            "method": "call",
            "id": "abc",
            "params": {
                "instructions": "Be brief.",
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": "Hello"}]}
                ],
                "tools": [],
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "jsonrpc": "2.0",
        "id": "abc",
        "result": {
            "result": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi there"}],
                "provider_metadata": {
                    "model": "demo",
                    "usage": {"prompt_tokens": 2, "completion_tokens": 3},
                },
            }
        },
    }


def test_get_completions_sync_maps_tool_calls(monkeypatch):
    def fake_post_provider(path, payload):
        assert payload["tools"][0]["function"]["name"] == "lookup_partner"
        return {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "lookup_partner",
                                    "arguments": json.dumps({"name": "Azure"}),
                                },
                            }
                        ]
                    }
                }
            ]
        }

    monkeypatch.setattr(main, "_post_provider", fake_post_provider)
    client = TestClient(main.app)
    response = client.post(
        "/api/odoo_ai/1/get_completions_sync",
        json={
            "jsonrpc": "2.0",
            "id": "abc",
            "params": {
                "messages": [{"role": "user", "content": [{"type": "text", "text": "Find it"}]}],
                "tools": [
                    {
                        "name": "lookup_partner",
                        "instructions": "Find a partner.",
                        "schema": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                            "required": ["name"],
                        },
                    }
                ],
            },
        },
    )

    content = response.json()["result"]["result"]["content"]
    assert content[0]["type"] == "tool_call"
    assert content[0]["name"] == "lookup_partner"
    assert content[0]["args"] == {"name": "Azure"}
    assert content[0]["call_id"] == "call_1"


def test_get_embeddings_maps_gemini_data(monkeypatch):
    def fake_post_gemini_embeddings(requests):
        assert [request["content"]["parts"][0]["text"] for request in requests] == [
            "One",
            "Two",
        ]
        assert {request["taskType"] for request in requests} == {"RETRIEVAL_DOCUMENT"}
        assert {request["outputDimensionality"] for request in requests} == {1536}
        assert requests[0]["title"] == "First"
        assert "title" not in requests[1]
        return [[1.0, 2.0], [3.0, 4.0]]

    monkeypatch.setattr(main, "_post_gemini_embeddings", fake_post_gemini_embeddings)
    client = TestClient(main.app)
    response = client.post(
        "/api/odoo_ai/1/get_embeddings",
        json={
            "jsonrpc": "2.0",
            "id": "emb",
            "params": {
                "input": [{"title": "First", "content": "One"}, {"content": "Two"}],
                "model": main.EMBEDDING_MODEL,
                "mode": "document",
            },
        },
    )

    assert response.json() == {
        "jsonrpc": "2.0",
        "id": "emb",
        "result": {"embeddings": [[1.0, 2.0], [3.0, 4.0]]},
    }
