#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib import error, request

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEATURES_PATH = REPO_ROOT / "specification" / "features"
DEFAULT_BINDINGS_PATH = REPO_ROOT / "specification" / "gherkin-bindings.yaml"
FEATURE_PREFIX = "Feature:"
SCENARIO_PREFIXES = ("Scenario:", "Scenario Outline:")
STEP_PREFIXES = ("Given ", "When ", "Then ", "And ", "But ")
REQUIRED_STEP_PREFIXES = ("Given ", "When ", "Then ")
EXECUTABLE_STATUS = "executable"
PLANNED_STATUS = "planned"
VALID_STATUSES = {EXECUTABLE_STATUS, PLANNED_STATUS}
DOCUMENT_ACTION_SUFFIXES = {".feature", ".md"}
FORBIDDEN_EXECUTABLE_STEP_PATTERNS = [
    re.compile(r"`?(GET|POST|PATCH|PUT|DELETE)\s+/", re.IGNORECASE),
    re.compile(r"`/[A-Za-z0-9_{]"),
    re.compile(r"\b(JSONPath|pytest|FastAPI)\b", re.IGNORECASE),
    re.compile(
        r"`(?:[1-5][0-9][0-9]|[1-5]xx)`|\b(?:[1-5]xx|200|201|400|401|403|404|409|422|500)\b",
        re.IGNORECASE,
    ),
]


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class Scenario:
    name: str
    section: str

    @property
    def steps(self) -> list[str]:
        return [line.strip() for line in self.section.splitlines() if line.startswith(STEP_PREFIXES)]


@dataclass(frozen=True)
class Contract:
    scenarios: list[Scenario]
    profiles: dict[str, Any]
    fixtures: dict[str, Any]
    bindings: dict[str, dict[str, Any]]

    @property
    def executable_bindings(self) -> dict[str, dict[str, Any]]:
        return {
            scenario.name: self.bindings[scenario.name]
            for scenario in self.scenarios
            if self.bindings.get(scenario.name, {}).get("status") == EXECUTABLE_STATUS
        }


def feature_scenarios(features_path: Path) -> list[Scenario]:
    scenarios: list[Scenario] = []
    seen_names: set[str] = set()
    for feature_file in _feature_files(features_path):
        for scenario in _parse_feature_file(feature_file):
            if scenario.name in seen_names:
                raise ContractError(f"duplicate scenario name: {scenario.name}")
            seen_names.add(scenario.name)
            scenarios.append(scenario)
    return scenarios


def load_contract(features_path: Path, bindings_path: Path) -> Contract:
    raw_bindings = yaml.safe_load(bindings_path.read_text())
    if not isinstance(raw_bindings, dict):
        raise ContractError("binding document must be a mapping")

    profiles = _mapping(raw_bindings.get("profiles"), "profiles")
    fixtures = _mapping(raw_bindings.get("fixtures"), "fixtures")
    bindings = _mapping(raw_bindings.get("scenarios"), "scenarios")
    return Contract(
        scenarios=feature_scenarios(features_path),
        profiles=profiles,
        fixtures=fixtures,
        bindings=bindings,
    )


def _feature_files(features_path: Path) -> list[Path]:
    if features_path.is_file():
        if features_path.suffix != ".feature":
            raise ContractError(f"feature path must be a .feature file or directory: {features_path}")
        return [features_path]
    if features_path.is_dir():
        feature_files = sorted(features_path.rglob("*.feature"))
        if feature_files:
            return feature_files
        raise ContractError(f"no .feature files found in {features_path}")
    raise ContractError(f"feature path does not exist: {features_path}")


def _parse_feature_file(feature_file: Path) -> list[Scenario]:
    scenarios: list[Scenario] = []
    feature_seen = False
    current_name: str | None = None
    current_lines: list[str] = []

    def flush_current() -> None:
        if current_name is not None:
            scenarios.append(Scenario(name=current_name, section="\n".join(current_lines)))

    for line_number, raw_line in enumerate(feature_file.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("@"):
            continue
        if line.startswith(FEATURE_PREFIX):
            if feature_seen:
                raise ContractError(f"{feature_file}:{line_number}: duplicate Feature heading")
            feature_seen = True
            continue
        scenario_prefix = next((prefix for prefix in SCENARIO_PREFIXES if line.startswith(prefix)), None)
        if scenario_prefix:
            if not feature_seen:
                raise ContractError(f"{feature_file}:{line_number}: Scenario appears before Feature")
            flush_current()
            name = line.removeprefix(scenario_prefix).strip()
            if not name:
                raise ContractError(f"{feature_file}:{line_number}: Scenario name is required")
            current_name = name
            current_lines = [f"{scenario_prefix} {name}"]
            continue
        if current_name is not None:
            current_lines.append(line)
            continue
        if not feature_seen:
            raise ContractError(f"{feature_file}:{line_number}: expected Feature heading")

    if not feature_seen:
        raise ContractError(f"{feature_file}: missing Feature heading")
    flush_current()
    if len(scenarios) != 1:
        raise ContractError(f"{feature_file}: expected exactly one scenario, found {len(scenarios)}")
    return scenarios


def validate_contract(contract: Contract) -> list[str]:
    errors: list[str] = []
    scenario_names = [scenario.name for scenario in contract.scenarios]
    binding_names = list(contract.bindings)

    if not scenario_names:
        errors.append("no scenarios found in feature files")
    if binding_names != scenario_names:
        errors.append("binding scenarios must match feature scenarios exactly and in order")
        missing = [name for name in scenario_names if name not in contract.bindings]
        extra = [name for name in binding_names if name not in scenario_names]
        if missing:
            errors.append(f"missing bindings: {', '.join(missing)}")
        if extra:
            errors.append(f"extra bindings: {', '.join(extra)}")

    for scenario in contract.scenarios:
        binding = contract.bindings.get(scenario.name)
        if not isinstance(binding, dict):
            errors.append(f"{scenario.name}: binding must be a mapping")
            continue

        for prefix in REQUIRED_STEP_PREFIXES:
            if not any(step.startswith(prefix) for step in scenario.steps):
                errors.append(f"{scenario.name}: missing {prefix.strip()} step")
        _validate_business_steps(scenario, errors)

        binding_id = binding.get("binding")
        if not isinstance(binding_id, str) or not binding_id:
            errors.append(f"{scenario.name}: binding id is required")

        status = binding.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"{scenario.name}: status must be one of {sorted(VALID_STATUSES)}")

        group = binding.get("group")
        if not isinstance(group, str) or not group:
            errors.append(f"{scenario.name}: group is required")

        for profile in _string_list(binding.get("profiles"), scenario.name, "profiles", errors):
            if profile not in contract.profiles:
                errors.append(f"{scenario.name}: unknown profile {profile!r}")

        for fixture in _string_list(binding.get("fixtures"), scenario.name, "fixtures", errors):
            if fixture not in contract.fixtures:
                errors.append(f"{scenario.name}: unknown fixture {fixture!r}")
        _validate_string_mapping(binding.get("requires_env", {}), scenario.name, "requires_env", errors)
        _validate_string_mapping(binding.get("state_from_env", {}), scenario.name, "state_from_env", errors)

        actions = binding.get("actions")
        assertions = binding.get("assertions")
        if status == EXECUTABLE_STATUS:
            if not isinstance(actions, list) or not actions:
                errors.append(f"{scenario.name}: executable binding requires actions")
            if not isinstance(assertions, list) or not assertions:
                errors.append(f"{scenario.name}: executable binding requires assertions")
            _validate_action_references(scenario.name, actions, assertions, contract, errors)

    return errors


def print_validation_summary(contract: Contract) -> None:
    print(
        f"gherkin-contract: verified {len(contract.scenarios)} scenarios, "
        f"{len(contract.executable_bindings)} executable bindings"
    )
    for scenario_name, binding in contract.executable_bindings.items():
        print(f"- {binding['binding']}: {scenario_name}")


def run_dry_run(contract: Contract, scenario_names: list[str], profile: str, selection_label: str) -> None:
    profile_config = _mapping(contract.profiles[profile], f"profile {profile}")
    token_envs = _profile_token_envs(profile_config, profile)
    base_url_env = _required_string(profile_config.get("base_url_env"), f"profile {profile}.base_url_env")
    print(f"dry-run: {profile} {selection_label}")
    for scenario_name in scenario_names:
        binding = contract.bindings[scenario_name]
        print(f"DRY-RUN {scenario_name}")
        required_env = _required_env(binding, token_envs)
        if _binding_requires_base_url(binding):
            required_env.append(base_url_env)
        if required_env := list(dict.fromkeys(required_env)):
            print(f"  requires-env: {', '.join(required_env)}")
        for action in binding.get("actions", []):
            if document_path := action.get("document_path"):
                print(f"  - DOC {document_path}")
            else:
                method = action.get("method", "GET")
                path = action.get("path", "")
                print(f"  - {method} {path}")


def run_live(contract: Contract, scenario_names: list[str], profile: str) -> None:
    profile_config = _mapping(contract.profiles[profile], f"profile {profile}")
    base_url_env = _required_string(profile_config.get("base_url_env"), f"profile {profile}.base_url_env")
    base_url = os.environ.get(base_url_env, "").rstrip("/")

    timeout = float(profile_config.get("timeout_seconds", 10))
    token_envs = _profile_token_envs(profile_config, profile)

    for scenario_name in scenario_names:
        binding = contract.bindings[scenario_name]
        state, missing_env = _state_from_env(binding)
        missing_env.extend(
            env_name
            for env_name in _required_env(binding, token_envs)
            if not os.environ.get(env_name) and env_name not in missing_env
        )
        if _binding_requires_base_url(binding) and not base_url and base_url_env not in missing_env:
            missing_env.append(base_url_env)
        if missing_env:
            print(f"GATED {scenario_name}: missing required environment {', '.join(missing_env)}")
            continue
        responses: dict[str, tuple[int, Any]] = {}
        print(f"RUN {scenario_name}")
        for action in binding.get("actions", []):
            status, payload = _execute_action(action, contract.fixtures, token_envs, base_url, timeout, state)
            responses[_required_string(action.get("name"), f"{scenario_name}.actions[].name")] = (status, payload)
            print(f"  - {action['name']}: {status}")
        _assert_responses(scenario_name, binding.get("assertions", []), responses, state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run black-box quote Gherkin contracts")
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES_PATH)
    parser.add_argument("--bindings", type=Path, default=DEFAULT_BINDINGS_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List feature scenarios and binding status")
    subparsers.add_parser("validate", help="Validate feature scenario to binding coverage")

    run_parser = subparsers.add_parser("run", help="Run a selected scenario or binding group")
    run_parser.add_argument("--profile", required=True)
    run_parser.add_argument("--scenario")
    run_parser.add_argument("--group")
    run_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(_normalize_source_args(argv if argv is not None else sys.argv[1:]))

    try:
        contract = load_contract(args.features, args.bindings)
        errors = validate_contract(contract)
        if errors:
            for validation_error in errors:
                print(f"gherkin-contract: {validation_error}", file=sys.stderr)
            return 1

        if args.command == "list":
            print(
                f"gherkin-contract: {len(contract.scenarios)} scenarios "
                f"({len(contract.executable_bindings)} executable bindings)"
            )
            for scenario in contract.scenarios:
                binding = contract.bindings[scenario.name]
                print(f"- [{binding['status']}] {binding['binding']}: {scenario.name}")
            return 0

        if args.command == "validate":
            print_validation_summary(contract)
            return 0

        scenario_names, selection_label = _select_scenarios(contract, args.scenario, args.group)
        if args.profile not in contract.profiles:
            raise ContractError(f"unknown profile: {args.profile}")
        if args.dry_run:
            run_dry_run(contract, scenario_names, args.profile, selection_label)
        else:
            run_live(contract, scenario_names, args.profile)
        return 0
    except (ContractError, OSError, yaml.YAMLError) as exception:
        print(f"gherkin-contract: {exception}", file=sys.stderr)
        return 1


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{name} must be a mapping")
    return value


def _normalize_source_args(argv: list[str]) -> list[str]:
    normalized: list[str] = []
    source_args: list[str] = []
    commands = {"list", "validate", "run"}
    saw_command = False
    index = 0
    while index < len(argv):
        value = argv[index]
        if saw_command and value in {"--features", "--bindings"} and index + 1 < len(argv):
            source_args.extend([value, argv[index + 1]])
            index += 2
            continue
        if value in commands:
            saw_command = True
        normalized.append(value)
        index += 1
    return source_args + normalized


def _string_list(value: Any, scenario_name: str, field: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{scenario_name}: {field} must be a list")
        return []
    strings = [item for item in value if isinstance(item, str)]
    if len(strings) != len(value):
        errors.append(f"{scenario_name}: {field} must contain only strings")
    return strings


def _required_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{name} is required")
    return value


def _validate_string_mapping(value: Any, scenario_name: str, field: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{scenario_name}: {field} must be a mapping")
        return

    for key, item in value.items():
        if not isinstance(key, str) or not key or not isinstance(item, str) or not item:
            errors.append(f"{scenario_name}: {field} must map non-empty strings to non-empty strings")


def _validate_business_steps(scenario: Scenario, errors: list[str]) -> None:
    for step in scenario.steps:
        for pattern in FORBIDDEN_EXECUTABLE_STEP_PATTERNS:
            if pattern.search(step):
                errors.append(f"{scenario.name}: executable scenario step is not business-readable: {step}")
                break


def _validate_action_references(
    scenario_name: str,
    actions: Any,
    assertions: Any,
    contract: Contract,
    errors: list[str],
) -> None:
    if not isinstance(actions, list) or not isinstance(assertions, list):
        return
    action_names: set[str] = set()
    for action in actions:
        if not isinstance(action, dict):
            errors.append(f"{scenario_name}: action must be a mapping")
            continue
        action_name = action.get("name")
        if not isinstance(action_name, str) or not action_name:
            errors.append(f"{scenario_name}: action name is required")
        else:
            action_names.add(action_name)
        if action.get("auth") and action.get("authorization"):
            errors.append(f"{scenario_name}: action cannot define both auth and authorization")
        headers = action.get("headers")
        if headers is not None and not isinstance(headers, dict):
            errors.append(f"{scenario_name}: action headers must be a mapping")
        body_fixture = action.get("body_fixture")
        if body_fixture is not None and body_fixture not in contract.fixtures:
            errors.append(f"{scenario_name}: unknown action body fixture {body_fixture!r}")
        document_path = action.get("document_path")
        if document_path is not None:
            try:
                _document_path(document_path)
            except ContractError as exception:
                errors.append(f"{scenario_name}: {exception}")
            continue
        method = action.get("method")
        path = action.get("path")
        if not isinstance(method, str) or not method:
            errors.append(f"{scenario_name}: HTTP action method is required")
        if not isinstance(path, str) or not path:
            errors.append(f"{scenario_name}: HTTP action path is required")
        if "authorization" in action and not isinstance(action["authorization"], str):
            errors.append(f"{scenario_name}: action authorization must be a string")

    for assertion in assertions:
        if not isinstance(assertion, dict):
            errors.append(f"{scenario_name}: assertion must be a mapping")
            continue
        action_name = assertion.get("action")
        if action_name not in action_names:
            errors.append(f"{scenario_name}: assertion references unknown action {action_name!r}")


def _select_scenarios(contract: Contract, scenario_name: str | None, group: str | None) -> tuple[list[str], str]:
    if bool(scenario_name) == bool(group):
        raise ContractError("choose exactly one of --scenario or --group")
    if scenario_name:
        if scenario_name not in contract.bindings:
            raise ContractError(f"unknown scenario: {scenario_name}")
        binding = contract.bindings[scenario_name]
        if binding.get("status") != EXECUTABLE_STATUS:
            raise ContractError(f"scenario is not executable: {scenario_name}")
        return [scenario_name], scenario_name

    selected = [
        scenario.name
        for scenario in contract.scenarios
        if contract.bindings[scenario.name].get("group") == group
        and contract.bindings[scenario.name].get("status") == EXECUTABLE_STATUS
    ]
    if not selected:
        raise ContractError(f"group has no executable scenarios: {group}")
    return selected, group or ""


def _execute_action(
    action: dict[str, Any],
    fixtures: dict[str, Any],
    token_envs: dict[str, Any],
    base_url: str,
    timeout: float,
    state: dict[str, Any],
) -> tuple[int, Any]:
    if document_path := action.get("document_path"):
        return 200, _document_path(document_path).read_text()

    method = _required_string(action.get("method"), "action.method")
    path = _required_string(action.get("path"), "action.path").format(**state)
    url = f"{base_url}{path}"
    body = None
    headers = {"Accept": "application/json"}

    body_fixture = action.get("body_fixture")
    if body_fixture:
        body = json.dumps(_render_templates(fixtures[body_fixture], state)).encode()
        headers["Content-Type"] = "application/json"

    if authorization := action.get("authorization"):
        headers["Authorization"] = str(authorization)
    elif auth_name := action.get("auth"):
        token_env = _required_string(token_envs.get(auth_name), f"token env for {auth_name}")
        token = os.environ.get(token_env)
        if not token:
            raise ContractError(f"auth {auth_name!r} requires environment variable {token_env}")
        headers["Authorization"] = f"Bearer {token}"

    if actor := action.get("actor"):
        headers["X-Actor"] = str(actor)

    for header_name, header_value in _mapping(action.get("headers", {}), "action.headers").items():
        headers[str(header_name)] = str(_render_templates(header_value, state))

    http_request = request.Request(url=url, data=body, method=method, headers=headers)
    try:
        with request.urlopen(http_request, timeout=timeout) as response:
            status = response.getcode()
            payload = _decode_json(response.read())
    except error.HTTPError as exception:
        status = exception.code
        payload = _decode_json(exception.read())

    for variable, pointer in action.get("save", {}).items():
        state[variable] = _json_path(payload, pointer)

    return status, payload


def _assert_responses(
    scenario_name: str,
    assertions: list[dict[str, Any]],
    responses: dict[str, tuple[int, Any]],
    state: dict[str, Any] | None = None,
) -> None:
    saved_state = state or {}
    for assertion in assertions:
        action_name = _required_string(assertion.get("action"), f"{scenario_name}.assertions[].action")
        status, payload = responses[action_name]
        if "status" in assertion and status != assertion["status"]:
            raise ContractError(f"{scenario_name}: {action_name} returned {status}, expected {assertion['status']}")
        if "json_field" in assertion:
            _json_path(payload, assertion["json_field"])
        if "json_missing" in assertion:
            path = _required_string(assertion.get("json_missing"), f"{scenario_name}.assertions[].json_missing")
            if _json_path_exists(payload, path):
                raise ContractError(f"{scenario_name}: {action_name} unexpectedly contained {path}")
        if "json_equals" in assertion:
            expected = assertion["json_equals"]
            actual = _json_path(payload, _required_string(assertion.get("path"), f"{scenario_name}.assertions[].path"))
            if actual != expected:
                raise ContractError(f"{scenario_name}: {action_name} {assertion['path']} was {actual!r}, expected {expected!r}")
        if "json_equals_state" in assertion:
            state_key = _required_string(
                assertion.get("json_equals_state"),
                f"{scenario_name}.assertions[].json_equals_state",
            )
            if state_key not in saved_state:
                raise ContractError(f"{scenario_name}: saved state {state_key!r} is not available")
            path = _required_string(assertion.get("path"), f"{scenario_name}.assertions[].path")
            expected = saved_state[state_key]
            actual = _json_path(payload, path)
            if actual != expected:
                raise ContractError(
                    f"{scenario_name}: {action_name} {path} was {actual!r}, "
                    f"expected saved state {state_key}={expected!r}"
                )
        if "text_contains" in assertion:
            expected = _required_string(assertion.get("text_contains"), f"{scenario_name}.assertions[].text_contains")
            if expected not in _payload_text(payload):
                raise ContractError(f"{scenario_name}: {action_name} did not contain {expected!r}")
        if "text_not_contains" in assertion:
            forbidden = _required_string(
                assertion.get("text_not_contains"),
                f"{scenario_name}.assertions[].text_not_contains",
            )
            if forbidden in _payload_text(payload):
                raise ContractError(f"{scenario_name}: {action_name} unexpectedly contained {forbidden!r}")


def _decode_json(body: bytes) -> Any:
    if not body:
        return None
    try:
        return json.loads(body.decode())
    except json.JSONDecodeError:
        return body.decode(errors="replace")


def _json_path(document: Any, pointer: Any) -> Any:
    path = _required_string(pointer, "json path")
    if not path.startswith("$."):
        raise ContractError(f"unsupported json path: {path}")
    value = document
    for part in path[2:].split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise ContractError(f"json path not found: {path}")
    return value


def _json_path_exists(document: Any, pointer: Any) -> bool:
    try:
        _json_path(document, pointer)
        return True
    except ContractError:
        return False


def _profile_token_envs(profile_config: dict[str, Any], profile: str) -> dict[str, Any]:
    token_envs = profile_config.get("tokens", {})
    if not isinstance(token_envs, dict):
        raise ContractError(f"profile {profile}.tokens must be a mapping")
    return token_envs


def _required_env(binding: dict[str, Any], token_envs: dict[str, Any]) -> list[str]:
    required_env: list[str] = []
    for env_key, env_reference in _mapping(binding.get("requires_env", {}), "requires_env").items():
        if not _is_env_reference(env_reference, token_envs):
            env_reference = env_key
        required_env.append(_resolve_env_reference(env_reference, token_envs))

    for action in binding.get("actions", []):
        if isinstance(action, dict) and action.get("auth"):
            required_env.append(_token_env_name(action["auth"], token_envs))

    return list(dict.fromkeys(required_env))


def _binding_requires_base_url(binding: dict[str, Any]) -> bool:
    return any(_action_requires_base_url(action) for action in binding.get("actions", []))


def _action_requires_base_url(action: Any) -> bool:
    return isinstance(action, dict) and "document_path" not in action


def _resolve_env_reference(env_reference: Any, token_envs: dict[str, Any]) -> str:
    reference = _required_string(env_reference, "requires_env")
    if reference in token_envs:
        return _token_env_name(reference, token_envs)
    return reference


def _is_env_reference(value: Any, token_envs: dict[str, Any]) -> bool:
    if not isinstance(value, str):
        return False
    if value in token_envs:
        return True
    return bool(re.fullmatch(r"[A-Z][A-Z0-9_]*", value))


def _token_env_name(auth_name: Any, token_envs: dict[str, Any]) -> str:
    auth_key = _required_string(auth_name, "action.auth")
    return _required_string(token_envs.get(auth_key), f"token env for {auth_key}")


def _document_path(path: Any) -> Path:
    relative_path = Path(_required_string(path, "action.document_path"))
    if relative_path.is_absolute():
        raise ContractError(f"document path must be relative: {relative_path}")
    resolved_path = (REPO_ROOT / relative_path).resolve()
    if not resolved_path.is_relative_to(REPO_ROOT.resolve()):
        raise ContractError(f"document path must stay inside the repository: {relative_path}")
    if resolved_path.suffix not in DOCUMENT_ACTION_SUFFIXES:
        raise ContractError(f"document action may only read Markdown or feature files: {relative_path}")
    if not resolved_path.is_file():
        raise ContractError(f"document path does not exist: {relative_path}")
    return resolved_path


def _payload_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, sort_keys=True)


def _state_from_env(binding: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    state_env = _mapping(binding.get("state_from_env", {}), "state_from_env")
    state: dict[str, str] = {}
    missing: list[str] = []
    for variable, env_name in state_env.items():
        value = os.environ.get(env_name)
        if not value:
            missing.append(env_name)
            continue
        state[variable] = value
    return state, missing


def _render_templates(value: Any, state: dict[str, Any]) -> Any:
    if isinstance(value, str):
        try:
            return value.format(**state)
        except KeyError as exception:
            raise ContractError(f"missing state for fixture placeholder: {exception.args[0]}") from None
    if isinstance(value, list):
        return [_render_templates(item, state) for item in value]
    if isinstance(value, dict):
        return {key: _render_templates(item, state) for key, item in value.items()}
    return value


if __name__ == "__main__":
    raise SystemExit(main())
