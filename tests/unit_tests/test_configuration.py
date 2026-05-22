from langgraph.pregel import Pregel

from agent.graph import graph
from agent.llm import (
    deployment_for_artifact,
    deployment_for_classification,
    deployment_for_draft,
    deployment_for_revision,
)
from agent.orchestrator.router import (
    mapped_request_type,
    route_after_architecture,
    route_after_documentation,
    route_after_planning,
    route_after_platform_selection,
    route_after_qa,
    route_after_requirements,
)


def test_graph_is_compiled() -> None:
    assert isinstance(graph, Pregel)


def test_router_maps_proposal_to_offer() -> None:
    assert mapped_request_type({"request_type": "proposal"}) == "offer"


def test_model_deployment_routing(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.1")
    monkeypatch.setenv("AZURE_OPENAI_CLASSIFICATION_DEPLOYMENT", "gpt-5-mini")
    monkeypatch.setenv("AZURE_OPENAI_ARCHITECTURE_DEPLOYMENT", "gpt-5.4")
    monkeypatch.setenv("AZURE_OPENAI_REVIEW_DEPLOYMENT", "gpt-5.4")
    monkeypatch.setenv("AZURE_OPENAI_DOCUMENTATION_DEPLOYMENT", "gpt-5-mini")
    monkeypatch.setenv("AZURE_OPENAI_REVISION_DEPLOYMENT", "gpt-5.1")
    monkeypatch.setenv("AZURE_OPENAI_DRAFT_DEPLOYMENT", "gpt-5-mini")

    assert deployment_for_classification() == "gpt-5-mini"
    assert deployment_for_artifact("architecture.md") == "gpt-5.4"
    assert deployment_for_artifact("review-checklist.md", "high") == "gpt-5.4"
    assert deployment_for_artifact("ticket-comment.md") == "gpt-5-mini"
    assert deployment_for_artifact("requirements.md") == "gpt-5.1"
    assert deployment_for_revision() == "gpt-5.1"
    assert deployment_for_draft() == "gpt-5-mini"


def test_generation_stage_routes_to_approval_on_human_review() -> None:
    state = {"next_action": "human_review"}

    assert route_after_platform_selection(state) == "approval"
    assert route_after_requirements(state) == "approval"
    assert route_after_architecture(state) == "approval"
    assert route_after_planning(state) == "approval"
    assert route_after_qa(state) == "approval"
    assert route_after_documentation(state) == "approval"
