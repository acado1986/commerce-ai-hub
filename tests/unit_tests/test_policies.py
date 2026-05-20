from agent.orchestrator.policies import confidence_requires_review, load_policy


def test_confidence_policy_threshold() -> None:
    assert confidence_requires_review(0.1) is True
    assert confidence_requires_review(0.95) is False


def test_policy_files_load() -> None:
    assert "min_confidence" in load_policy("confidence-policy.yaml")
