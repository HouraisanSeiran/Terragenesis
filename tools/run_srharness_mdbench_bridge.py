#!/usr/bin/env python3
"""SRHarness -> mdbench bridge tool.

Subcommands:
  export    - generate a synthetic problem task from a task file.
  discover  - run real SRHarness discovery on a public mdbench problem.
  evaluate  - run official mdbench evaluation against a frozen checkpoint.

This module is intentionally self-contained and uses only real APIs from
src.*, sr_harness.* and agent_mcp.*.
"""

import argparse
import copy
import hashlib
import json
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Runtime configuration (must run before importing numpy).
# ---------------------------------------------------------------------------

def _configure_runtime():
    thread_vars = (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "NUMBA_NUM_THREADS",
        "BLIS_NUM_THREADS",
    )
    for name in thread_vars:
        os.environ[name] = "1"
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

    if os.name == "nt":
        import psutil

        proc = psutil.Process()
        current = proc.cpu_affinity()
        if not current:
            raise RuntimeError("Unable to read current CPU affinity on Windows")
        target = current[:2]
        if not target:
            raise RuntimeError("No CPU cores available for affinity restriction")
        try:
            proc.cpu_affinity(target)
        except Exception as exc:  # pragma: no cover - platform dependent
            raise RuntimeError(f"Failed to set CPU affinity: {exc!r}") from exc
        try:
            proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        except Exception as exc:  # pragma: no cover - platform dependent
            raise RuntimeError(f"Failed to set process priority: {exc!r}") from exc


# ---------------------------------------------------------------------------
# Gateway helpers
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
GW = ROOT / ".scratch" / "deepseek-harness" / "agent_mcp_gateway"


def _load_gateway():
    if str(GW) not in sys.path:
        sys.path.insert(0, str(GW))
    from agent_mcp.config import load_settings, deepseek_credential_scope
    from agent_mcp.security import Credentials

    settings = load_settings(GW / "config.json")
    endpoint = settings.deepseek_base_url
    creds = Credentials(settings.credential_service)
    api_key = creds.get(deepseek_credential_scope(endpoint))
    env = {
        "DEEPSEEK_ENDPOINT": endpoint,
        "DEEPSEEK_API_KEY": api_key,
    }
    model = settings.models["deepseek-text"].model
    return settings, env, model


# ---------------------------------------------------------------------------
# Public problem loading (mdbench layout)
# ---------------------------------------------------------------------------

def _load_public_problem(problem_dir, numpy_module):
    from src.scoring import public_variables, validate_data

    pdir = Path(problem_dir)
    problem_path = pdir / "problem.json"
    train_path = pdir / "train.npy"

    if not problem_path.is_file():
        raise FileNotFoundError(f"Missing public problem file: {problem_path}")
    if not train_path.is_file():
        raise FileNotFoundError(f"Missing public train file: {train_path}")

    with problem_path.open("r", encoding="utf-8") as fh:
        problem = json.load(fh)

    if not isinstance(problem, dict):
        raise ValueError("problem.json must contain a JSON object")

    expected_keys = {"task_description", "variables", "data_columns", "data_layout"}
    actual_keys = set(problem.keys())
    if actual_keys != expected_keys:
        extra = actual_keys - expected_keys
        missing = expected_keys - actual_keys
        raise ValueError(
            f"problem.json has unexpected keys: extra={sorted(extra)} missing={sorted(missing)}"
        )

    if problem["data_layout"] != "variables_by_samples":
        raise ValueError(
            f"Unsupported data_layout: {problem['data_layout']!r}; "
            "expected 'variables_by_samples'"
        )

    train = numpy_module.load(train_path, allow_pickle=False)
    variables, target, columns = public_variables(problem)
    validate_data(train, columns)

    if train.ndim != 2:
        raise ValueError(f"train.npy must be 2D (VARIABLES x SAMPLES), got shape {train.shape}")
    if train.shape[0] != len(columns):
        raise ValueError(
            f"train.npy first dimension {train.shape[0]} does not match columns {len(columns)}"
        )

    data = {col: train[i] for i, col in enumerate(columns)}
    return problem, variables, target, columns, data


# ---------------------------------------------------------------------------
# Subcommand: export
# ---------------------------------------------------------------------------

def _cmd_export(args):
    from src.validate_problem import load_task
    from src.export_problems import export_task

    task = load_task(args.task)
    export_task(
        task,
        Path(args.output),
        force=False,
        train_samples=args.train_samples,
        id_test_samples=args.id_test_samples,
        ood_test_samples=args.ood_test_samples,
        seed=0,
    )


# ---------------------------------------------------------------------------
# Subcommand: discover
# ---------------------------------------------------------------------------

def _cmd_discover(args):
    import numpy as np

    from sr_harness.core.context import AgentContext
    from sr_harness.agents.sr_agent import SRAgent

    settings, env, model = _load_gateway()
    problem, variables, target, columns, data = _load_public_problem(args.problem_dir, np)

    descriptions = {
        v.name: f"{v.description} [{v.unit}]" for v in variables
    }

    context = AgentContext(
        args=argparse.Namespace(api_environment=env),
        data=data,
        target=target,
        variable_descriptions=descriptions,
        workspace=None,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ckpt_path = out_path / "checkpoint.json"
    if ckpt_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing checkpoint: {ckpt_path}")

    agent = SRAgent(
        llm_provider="deepseek",
        llm_model=model,
        context=context,
        tools=["statistics_analysis", "evaluate_formula", "submit_formula"],
        skills=[],
        save_path=str(out_path),
        run_id="mdbench-bridge",
        local_sample_size=1,
        max_refinement_depth=args.depth,
        global_width=1,
        max_restart_loop=1,
        restart_top_k=1,
        llm_max_tokens=args.max_tokens,
        max_workers=0,
        validation_fraction=0.2,
        split_by="random",
        split_random_state=42,
        ranking_metric="mse",
        larger_is_better=False,
        force_initial_diagnostics=False,
        auto_routing=False,
    )

    input_data = {c: data[c] for c in columns if c != target}
    target_data = {target: data[target]}

    result = agent.run(input_data, target_data, problem["task_description"])

    candidates = result.get("candidates")
    best_candidate = result.get("best_candidate")
    if candidates is None or best_candidate is None:
        raise ValueError("SRAgent result missing candidates/best_candidate")
    if not isinstance(best_candidate, int) or not (0 <= best_candidate < len(candidates)):
        raise ValueError(f"Invalid best_candidate index: {best_candidate!r}")
    selected = candidates[best_candidate]

    formula = selected.get("formula")
    if not formula:
        raise ValueError("Selected candidate has no formula")

    if "=" in formula:
        submission = formula
    else:
        submission = f"{target} = {formula}"

    search_state = agent.run_state.export_state()

    checkpoint = {
        "problem": problem,
        "model": model,
        "selected": selected,
        "result": result,
        "submission": submission,
        "search_state": search_state,
    }

    ckpt_path = out_path / "checkpoint.json"
    if ckpt_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing checkpoint: {ckpt_path}")

    serialized = json.dumps(checkpoint, default=str, indent=2)

    ckpt_path.write_text(serialized, encoding="utf-8")
    digest = hashlib.sha256(ckpt_path.read_bytes()).hexdigest()
    (out_path / "checkpoint.sha256.json").write_text(
        json.dumps({"sha256": digest}, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Subcommand: evaluate
# ---------------------------------------------------------------------------

def _make_ask_factory(checkpoint, env, output_dir, budget):
    from sr_harness.api.deepseek_api import DeepSeekAPI

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    frozen_model = checkpoint["model"]
    frozen_problem = checkpoint["problem"]
    frozen_search_state = checkpoint["search_state"]

    state = {"used": 0}

    def make_ask():
        snapshot = copy.deepcopy(
            {
                "problem": frozen_problem,
                "search_state": frozen_search_state,
                "model": frozen_model,
            }
        )

        def ask(question, probe_name, description, output_dir=None):
            if state["used"] >= budget:
                raise RuntimeError("DeepSeek probe API request budget exhausted")
            state["used"] += 1
            request_count = state["used"]

            target_dir = Path(output_dir) if output_dir is not None else output_dir_default
            target_dir.mkdir(parents=True, exist_ok=True)

            system_content = json.dumps(
                {
                    "public_problem": snapshot["problem"],
                    "search_state": snapshot["search_state"],
                },
                default=str,
            )
            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": question},
            ]

            api = DeepSeekAPI(
                model=snapshot["model"],
                environment=env,
                tool_box=None,
                save_path=str(target_dir),
            )

            summary = api(
                messages,
                n=1,
                max_tokens=4096,
                temperature=0,
            )

            samples = list(summary)
            if not getattr(summary, "ok", False):
                raise RuntimeError("DeepSeek API call failed")
            if len(samples) != 1:
                raise ValueError(f"Expected exactly 1 sample, got {len(samples)}")
            sample = samples[0]
            tool_calls = getattr(sample, "tool_calls", None)
            if tool_calls:
                raise ValueError("Unexpected tool calls in probe response")
            content = getattr(sample, "content", None)
            if not content:
                raise ValueError("Empty probe response content")

            record = {
                "probe_name": probe_name,
                "description": description,
                "question": question,
                "response": content,
                "token_usage": getattr(summary, "token_usage", None),
                "request_count": request_count,
                "actual_cost": "unknown",
            }
            record_path = target_dir / f"probe_{probe_name}.json"
            record_path.write_text(json.dumps(record, default=str, indent=2), encoding="utf-8")

            return content

        return ask

    output_dir_default = output_dir
    return make_ask


def _verify_checkpoint_hash(ckpt_path):
    ckpt_path = Path(ckpt_path)
    sidecar = ckpt_path.with_name("checkpoint.sha256.json")
    if not ckpt_path.is_file():
        raise FileNotFoundError(f"Missing checkpoint: {ckpt_path}")
    if not sidecar.is_file():
        raise FileNotFoundError(f"Missing checkpoint hash sidecar: {sidecar}")

    with sidecar.open("r", encoding="utf-8") as fh:
        expected = json.load(fh)["sha256"]

    serialized = ckpt_path.read_text(encoding="utf-8")
    actual = hashlib.sha256(ckpt_path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(
            f"Checkpoint integrity check failed: expected {expected}, got {actual}"
        )

    return json.loads(serialized)


def _cmd_evaluate(args):
    import numpy as np

    settings, env, model = _load_gateway()

    out_path = Path(args.output)
    integrity_error = None
    checkpoint = None
    try:
        checkpoint = _verify_checkpoint_hash(args.checkpoint)

        if checkpoint.get("model") != model:
            raise ValueError(
                f"Frozen model {checkpoint.get('model')!r} does not match gateway model {model!r}"
            )

        from src.evaluate import evaluate

        make_ask = _make_ask_factory(checkpoint, env, out_path, budget=1)

        metrics = evaluate(
            argparse.Namespace(save_path=str(out_path), probe_workers=1),
            args.answer,
            [checkpoint["submission"]],
            make_ask,
        )

        out_path.mkdir(parents=True, exist_ok=True)
        (out_path / "metrics.json").write_text(
            json.dumps(metrics, default=str, indent=2), encoding="utf-8"
        )
        if not metrics["phenomenal"].get("ok") or any(
            not p.get("ok") for p in metrics["mechanism_probes"]
        ):
            raise RuntimeError("official evaluation execution failed; see metrics.json")
    finally:
        if checkpoint is not None:
            try:
                _verify_checkpoint_hash(args.checkpoint)
            except Exception as exc:
                integrity_error = exc
        elif args.checkpoint is not None:
            try:
                _verify_checkpoint_hash(args.checkpoint)
            except Exception as exc:
                integrity_error = exc
        if integrity_error is not None:
            raise integrity_error


# ---------------------------------------------------------------------------
# Argument parsing / dispatch
# ---------------------------------------------------------------------------

def _build_parser():
    parser = argparse.ArgumentParser(
        prog="run_srharness_mdbench_bridge",
        description="Bridge SRHarness discovery to mdbench evaluation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="Export an mdbench task problem directory")
    p_export.add_argument("--task", required=True)
    p_export.add_argument("--output", required=True)
    p_export.add_argument("--train-samples", type=int, default=128)
    p_export.add_argument("--id-test-samples", type=int, default=64)
    p_export.add_argument("--ood-test-samples", type=int, default=64)
    p_export.set_defaults(func=_cmd_export)

    p_discover = sub.add_parser("discover", help="Run SRHarness discovery on a public problem")
    p_discover.add_argument("--problem-dir", required=True)
    p_discover.add_argument("--output", required=True)
    p_discover.add_argument("--depth", type=int, default=3)
    p_discover.add_argument("--max-tokens", type=int, default=4096)
    p_discover.set_defaults(func=_cmd_discover)

    p_eval = sub.add_parser("evaluate", help="Run official mdbench evaluation")
    p_eval.add_argument("--answer", required=True)
    p_eval.add_argument("--checkpoint", required=True)
    p_eval.add_argument("--output", required=True)
    p_eval.set_defaults(func=_cmd_evaluate)

    return parser


def main(argv=None):
    _configure_runtime()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "depth", None) is not None:
        if not (1 <= args.depth <= 4):
            parser.error("--depth must be between 1 and 4")

    args.func(args)


if __name__ == "__main__":
    main()
