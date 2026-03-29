"""
Evaluation Service
==================

Dify-inspired LLM output quality scoring framework.

Manages evaluation datasets, test cases, execution runs, and result scoring.
Supports four scoring methods:
  - exact_match: binary match on stripped strings
  - contains: expected output is a substring of actual
  - semantic_similarity: cosine similarity via VectorStore embeddings
  - llm_judge: LLM grades actual output 0.0-1.0 against expected
"""

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Pass threshold: score >= 0.7
PASS_THRESHOLD = 0.7

# Maximum bulk import size
MAX_BULK_IMPORT = 500

# ---------------------------------------------------------------------------
# Lazy DB access (same pattern as rag_service / annotation_service)
# ---------------------------------------------------------------------------

_Database = None


async def _get_db():
    global _Database
    if _Database is None:
        try:
            from apps.backend.core.unified_auth import Database

            _Database = Database
        except ImportError:
            from apps.backend.saas_auth import Database

            _Database = Database
    return _Database


# ---------------------------------------------------------------------------
# Evaluation Service
# ---------------------------------------------------------------------------


class EvaluationService:
    """Manages evaluation datasets, test cases, runs, and scoring."""

    def __init__(self):
        self._vector_store = None
        self._llm = None

    def _get_vector_store(self):
        if self._vector_store is None:
            try:
                from apps.backend.core.vector_store import vector_store

                self._vector_store = vector_store
            except Exception as e:
                logger.warning("VectorStore unavailable: %s", e)
        return self._vector_store

    def _get_llm(self):
        if self._llm is None:
            try:
                from apps.backend.services.unified_llm import unified_llm

                self._llm = unified_llm
            except Exception as e:
                logger.warning("UnifiedLLMService unavailable: %s", e)
        return self._llm

    # -----------------------------------------------------------------------
    # Dataset CRUD
    # -----------------------------------------------------------------------

    async def create_dataset(self, user_id: str, name: str, description: str | None = None) -> dict[str, Any]:
        Database = await _get_db()
        dataset_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        await Database.execute(
            """
            INSERT INTO evaluation_datasets
                (id, user_id, name, description, test_case_count, status, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 0, 'active', $5, $5)
            """,
            dataset_id,
            user_id,
            name,
            description,
            now,
        )

        return {
            "id": dataset_id,
            "user_id": user_id,
            "name": name,
            "description": description,
            "test_case_count": 0,
            "status": "active",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

    async def list_datasets(self, user_id: str) -> list[dict[str, Any]]:
        Database = await _get_db()

        rows = await Database.fetch(
            """
            SELECT * FROM evaluation_datasets
            WHERE user_id = $1 AND status != 'deleted'
            ORDER BY created_at DESC
            """,
            user_id,
        )
        return [dict(r) for r in rows]

    async def get_dataset(self, dataset_id: str, user_id: str) -> dict[str, Any] | None:
        Database = await _get_db()

        row = await Database.fetchrow(
            """
            SELECT * FROM evaluation_datasets
            WHERE id = $1 AND user_id = $2 AND status != 'deleted'
            """,
            dataset_id,
            user_id,
        )
        return dict(row) if row else None

    async def delete_dataset(self, dataset_id: str, user_id: str) -> bool:
        Database = await _get_db()

        dataset = await self.get_dataset(dataset_id, user_id)
        if not dataset:
            return False

        # Delete results for all runs in this dataset
        await Database.execute(
            """
            DELETE FROM evaluation_results
            WHERE run_id IN (
                SELECT id FROM evaluation_runs WHERE dataset_id = $1
            )
            """,
            dataset_id,
        )
        # Delete runs
        await Database.execute("DELETE FROM evaluation_runs WHERE dataset_id = $1", dataset_id)
        # Delete test cases
        await Database.execute("DELETE FROM evaluation_test_cases WHERE dataset_id = $1", dataset_id)
        # Soft-delete dataset
        await Database.execute(
            "UPDATE evaluation_datasets SET status = 'deleted', updated_at = $2 WHERE id = $1",
            dataset_id,
            datetime.now(UTC),
        )
        return True

    # -----------------------------------------------------------------------
    # Test Case CRUD
    # -----------------------------------------------------------------------

    async def add_test_case(
        self,
        dataset_id: str,
        user_id: str,
        input_text: str,
        expected_output: str | None = None,
        category: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        Database = await _get_db()

        # Verify dataset ownership
        dataset = await self.get_dataset(dataset_id, user_id)
        if not dataset:
            raise ValueError("Dataset not found")

        case_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        await Database.execute(
            """
            INSERT INTO evaluation_test_cases
                (id, dataset_id, user_id, input_text, expected_output, category, metadata_json, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            case_id,
            dataset_id,
            user_id,
            input_text,
            expected_output,
            category,
            metadata_json,
            now,
        )

        # Update test case count
        await Database.execute(
            """
            UPDATE evaluation_datasets
            SET test_case_count = test_case_count + 1, updated_at = $2
            WHERE id = $1
            """,
            dataset_id,
            now,
        )

        return {
            "id": case_id,
            "dataset_id": dataset_id,
            "input_text": input_text,
            "expected_output": expected_output,
            "category": category,
            "metadata_json": metadata_json,
            "created_at": now.isoformat(),
        }

    async def list_test_cases(
        self, dataset_id: str, user_id: str, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        Database = await _get_db()

        # Verify dataset ownership
        dataset = await self.get_dataset(dataset_id, user_id)
        if not dataset:
            raise ValueError("Dataset not found")

        rows = await Database.fetch(
            """
            SELECT * FROM evaluation_test_cases
            WHERE dataset_id = $1 AND user_id = $2
            ORDER BY created_at ASC
            LIMIT $3 OFFSET $4
            """,
            dataset_id,
            user_id,
            limit,
            offset,
        )
        return [dict(r) for r in rows]

    async def delete_test_case(self, test_case_id: str, user_id: str) -> bool:
        Database = await _get_db()

        row = await Database.fetchrow(
            "SELECT dataset_id FROM evaluation_test_cases WHERE id = $1 AND user_id = $2",
            test_case_id,
            user_id,
        )
        if not row:
            return False

        dataset_id = row["dataset_id"]

        await Database.execute("DELETE FROM evaluation_test_cases WHERE id = $1", test_case_id)

        # Decrement test case count
        await Database.execute(
            """
            UPDATE evaluation_datasets
            SET test_case_count = GREATEST(test_case_count - 1, 0), updated_at = $2
            WHERE id = $1
            """,
            dataset_id,
            datetime.now(UTC),
        )
        return True

    async def bulk_import_test_cases(
        self, dataset_id: str, user_id: str, cases: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Import up to 500 test cases at once."""
        if len(cases) > MAX_BULK_IMPORT:
            raise ValueError(f"Maximum {MAX_BULK_IMPORT} test cases per import (got {len(cases)})")

        Database = await _get_db()

        # Verify dataset ownership
        dataset = await self.get_dataset(dataset_id, user_id)
        if not dataset:
            raise ValueError("Dataset not found")

        now = datetime.now(UTC)
        imported = 0
        errors = []

        for i, case in enumerate(cases):
            input_text = case.get("input_text", "").strip()
            if not input_text:
                errors.append({"index": i, "error": "input_text is required"})
                continue

            case_id = str(uuid.uuid4())
            expected = case.get("expected_output")
            category = case.get("category")
            meta = case.get("metadata_json")
            if isinstance(meta, dict):
                meta = json.dumps(meta)

            try:
                await Database.execute(
                    """
                    INSERT INTO evaluation_test_cases
                        (id, dataset_id, user_id, input_text, expected_output, category, metadata_json, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    case_id,
                    dataset_id,
                    user_id,
                    input_text,
                    expected,
                    category,
                    meta,
                    now,
                )
                imported += 1
            except Exception as e:
                logger.warning("Failed to import test case %d: %s", i, e)
                errors.append({"index": i, "error": str(e)})

        # Update test case count
        if imported > 0:
            await Database.execute(
                """
                UPDATE evaluation_datasets
                SET test_case_count = test_case_count + $2, updated_at = $3
                WHERE id = $1
                """,
                dataset_id,
                imported,
                now,
            )

        return {
            "imported": imported,
            "errors": errors,
            "total_submitted": len(cases),
        }

    # -----------------------------------------------------------------------
    # Run execution
    # -----------------------------------------------------------------------

    async def start_run(
        self,
        dataset_id: str,
        user_id: str,
        model_id: str,
        scoring_method: str = "semantic_similarity",
        prompt_template: str | None = None,
        agent_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        Database = await _get_db()

        # Verify dataset ownership
        dataset = await self.get_dataset(dataset_id, user_id)
        if not dataset:
            raise ValueError("Dataset not found")

        # Validate scoring method
        valid_methods = {"exact_match", "contains", "semantic_similarity", "llm_judge"}
        if scoring_method not in valid_methods:
            raise ValueError(f"Invalid scoring method: {scoring_method}. Must be one of: {valid_methods}")

        # Count test cases
        count_row = await Database.fetchrow(
            "SELECT COUNT(*) as total FROM evaluation_test_cases WHERE dataset_id = $1",
            dataset_id,
        )
        total_cases = count_row["total"] if count_row else 0
        if total_cases == 0:
            raise ValueError("Dataset has no test cases")

        run_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        config_str = json.dumps(config) if config else None

        await Database.execute(
            """
            INSERT INTO evaluation_runs
                (id, dataset_id, user_id, model_id, prompt_template, agent_id,
                 status, total_cases, completed_cases, passed_cases,
                 scoring_method, config_json, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, 'pending', $7, 0, 0, $8, $9, $10)
            """,
            run_id,
            dataset_id,
            user_id,
            model_id,
            prompt_template,
            agent_id,
            total_cases,
            scoring_method,
            config_str,
            now,
        )

        return {
            "id": run_id,
            "dataset_id": dataset_id,
            "user_id": user_id,
            "model_id": model_id,
            "status": "pending",
            "total_cases": total_cases,
            "scoring_method": scoring_method,
            "created_at": now.isoformat(),
        }

    async def execute_run(self, run_id: str) -> dict[str, Any]:
        """Execute an evaluation run: iterate test cases, call LLM, score results."""
        Database = await _get_db()

        # Load run
        run_row = await Database.fetchrow("SELECT * FROM evaluation_runs WHERE id = $1", run_id)
        if not run_row:
            raise ValueError("Run not found")

        run = dict(run_row)
        dataset_id = run["dataset_id"]
        model_id = run["model_id"]
        scoring_method = run["scoring_method"]
        prompt_template = run.get("prompt_template")
        started_at = datetime.now(UTC)

        # Mark as running
        await Database.execute(
            "UPDATE evaluation_runs SET status = 'running', started_at = $2 WHERE id = $1",
            run_id,
            started_at,
        )

        # Load all test cases
        test_cases = await Database.fetch(
            """
            SELECT * FROM evaluation_test_cases
            WHERE dataset_id = $1
            ORDER BY created_at ASC
            """,
            dataset_id,
        )

        llm = self._get_llm()
        if llm is None:
            await Database.execute(
                "UPDATE evaluation_runs SET status = 'failed', completed_at = $2 WHERE id = $1",
                run_id,
                datetime.now(UTC),
            )
            raise RuntimeError("LLM service not available")

        completed = 0
        passed = 0
        total_tokens = 0
        total_cost = 0.0
        total_latency = 0.0
        scores = []

        for tc_row in test_cases:
            tc = dict(tc_row)
            result_id = str(uuid.uuid4())
            error_msg = None
            actual_output = None
            score = None
            score_passed = None
            latency_ms = None
            tokens = None
            cost = None
            scoring_details_str = None

            try:
                # Build prompt
                input_text = tc["input_text"]
                if prompt_template:
                    prompt = prompt_template.replace("{{input}}", input_text)
                else:
                    prompt = input_text

                messages = [{"role": "user", "content": prompt}]

                # Call LLM and measure latency
                t0 = time.monotonic()
                resp = await llm.chat_with_metadata(
                    messages=messages,
                    model=model_id,
                    max_tokens=1024,
                    temperature=0.3,
                )
                t1 = time.monotonic()
                latency_ms = (t1 - t0) * 1000.0

                if resp.error:
                    error_msg = resp.error
                    actual_output = ""
                else:
                    actual_output = resp.content or ""

                tokens = resp.total_tokens
                # Estimate cost (rough: $0.01 / 1k tokens)
                cost = (tokens / 1000.0) * 0.01 if tokens else 0.0

                # Score output
                expected_output = tc.get("expected_output")
                if expected_output and not error_msg:
                    score, details = await self._score_output(
                        method=scoring_method,
                        input_text=input_text,
                        expected=expected_output,
                        actual=actual_output,
                        model_id=model_id,
                    )
                    scoring_details_str = json.dumps(details)
                    score_passed = score >= PASS_THRESHOLD
                elif not expected_output:
                    # No expected output — cannot score, mark as None
                    score = None
                    score_passed = None
                    scoring_details_str = json.dumps({"note": "No expected_output provided"})

            except Exception as e:
                logger.warning(
                    "Evaluation failed for test case %s in run %s: %s",
                    tc["id"],
                    run_id,
                    e,
                )
                error_msg = str(e)

            # Save result
            try:
                await Database.execute(
                    """
                    INSERT INTO evaluation_results
                        (id, run_id, test_case_id, actual_output, score, passed,
                         latency_ms, tokens_used, cost_usd, scoring_details, error_message, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    """,
                    result_id,
                    run_id,
                    tc["id"],
                    actual_output,
                    score,
                    score_passed,
                    latency_ms,
                    tokens,
                    cost,
                    scoring_details_str,
                    error_msg,
                    datetime.now(UTC),
                )
            except Exception as e:
                logger.warning(
                    "Failed to save evaluation result for test case %s: %s",
                    tc["id"],
                    e,
                )

            completed += 1
            if score_passed:
                passed += 1
            if score is not None:
                scores.append(score)
            if tokens:
                total_tokens += tokens
            if cost:
                total_cost += cost
            if latency_ms:
                total_latency += latency_ms

            # Update run progress periodically (every 10 cases)
            if completed % 10 == 0:
                try:
                    await Database.execute(
                        "UPDATE evaluation_runs SET completed_cases = $2 WHERE id = $1",
                        run_id,
                        completed,
                    )
                except Exception as e:
                    logger.warning("Failed to update run progress: %s", e)

        # Compute aggregates
        avg_score = sum(scores) / len(scores) if scores else None
        avg_latency = total_latency / completed if completed > 0 else None
        completed_at = datetime.now(UTC)

        # Update run with final stats
        await Database.execute(
            """
            UPDATE evaluation_runs
            SET status = 'completed',
                completed_cases = $2,
                passed_cases = $3,
                avg_score = $4,
                avg_latency_ms = $5,
                total_tokens = $6,
                total_cost_usd = $7,
                completed_at = $8
            WHERE id = $1
            """,
            run_id,
            completed,
            passed,
            avg_score,
            avg_latency,
            total_tokens,
            total_cost,
            completed_at,
        )

        return {
            "id": run_id,
            "status": "completed",
            "completed_cases": completed,
            "passed_cases": passed,
            "avg_score": round(avg_score, 4) if avg_score is not None else None,
            "avg_latency_ms": round(avg_latency, 2) if avg_latency is not None else None,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 4),
            "completed_at": completed_at.isoformat(),
        }

    async def get_run(self, run_id: str, user_id: str) -> dict[str, Any] | None:
        Database = await _get_db()

        row = await Database.fetchrow(
            "SELECT * FROM evaluation_runs WHERE id = $1 AND user_id = $2",
            run_id,
            user_id,
        )
        return dict(row) if row else None

    async def list_runs(
        self,
        user_id: str,
        dataset_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        Database = await _get_db()

        if dataset_id:
            rows = await Database.fetch(
                """
                SELECT * FROM evaluation_runs
                WHERE user_id = $1 AND dataset_id = $2
                ORDER BY created_at DESC
                LIMIT $3 OFFSET $4
                """,
                user_id,
                dataset_id,
                limit,
                offset,
            )
        else:
            rows = await Database.fetch(
                """
                SELECT * FROM evaluation_runs
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                user_id,
                limit,
                offset,
            )
        return [dict(r) for r in rows]

    # -----------------------------------------------------------------------
    # Results
    # -----------------------------------------------------------------------

    async def get_run_results(
        self, run_id: str, user_id: str, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        Database = await _get_db()

        # Verify run ownership
        run = await self.get_run(run_id, user_id)
        if not run:
            raise ValueError("Run not found")

        rows = await Database.fetch(
            """
            SELECT r.*, tc.input_text, tc.expected_output, tc.category
            FROM evaluation_results r
            JOIN evaluation_test_cases tc ON r.test_case_id = tc.id
            WHERE r.run_id = $1
            ORDER BY tc.created_at ASC
            LIMIT $2 OFFSET $3
            """,
            run_id,
            limit,
            offset,
        )
        return [dict(r) for r in rows]

    async def compare_runs(self, run_ids: list[str], user_id: str) -> dict[str, Any]:
        """Compare multiple evaluation runs side-by-side."""
        Database = await _get_db()

        if not run_ids or len(run_ids) < 2:
            raise ValueError("At least 2 run IDs required for comparison")
        if len(run_ids) > 10:
            raise ValueError("Maximum 10 runs for comparison")

        runs = []
        for rid in run_ids:
            run = await self.get_run(rid, user_id)
            if not run:
                raise ValueError(f"Run {rid} not found")
            runs.append(run)

        # Build comparison
        comparison = {
            "runs": [],
            "summary": {
                "best_avg_score": None,
                "best_run_id": None,
                "best_model": None,
            },
        }

        best_score = -1.0
        for run in runs:
            run_summary = {
                "id": run["id"],
                "model_id": run["model_id"],
                "scoring_method": run["scoring_method"],
                "status": run["status"],
                "total_cases": run["total_cases"],
                "completed_cases": run["completed_cases"],
                "passed_cases": run["passed_cases"],
                "avg_score": run.get("avg_score"),
                "avg_latency_ms": run.get("avg_latency_ms"),
                "total_tokens": run.get("total_tokens", 0),
                "total_cost_usd": run.get("total_cost_usd", 0.0),
                "created_at": run.get("created_at"),
            }

            # Calculate pass rate
            if run["completed_cases"] and run["completed_cases"] > 0:
                run_summary["pass_rate"] = round((run["passed_cases"] or 0) / run["completed_cases"], 4)
            else:
                run_summary["pass_rate"] = None

            comparison["runs"].append(run_summary)

            avg = run.get("avg_score")
            if avg is not None and avg > best_score:
                best_score = avg
                comparison["summary"]["best_avg_score"] = round(avg, 4)
                comparison["summary"]["best_run_id"] = run["id"]
                comparison["summary"]["best_model"] = run["model_id"]

        return comparison

    # -----------------------------------------------------------------------
    # Scoring methods
    # -----------------------------------------------------------------------

    async def _score_exact_match(self, expected: str, actual: str) -> float:
        """1.0 if stripped strings are equal, else 0.0."""
        return 1.0 if expected.strip() == actual.strip() else 0.0

    async def _score_contains(self, expected: str, actual: str) -> float:
        """1.0 if expected output is a substring of actual output."""
        return 1.0 if expected.strip() in actual else 0.0

    async def _score_semantic_similarity(self, expected: str, actual: str) -> float:
        """Cosine similarity between embeddings via VectorStore."""
        vs = self._get_vector_store()
        if vs is None:
            logger.warning("VectorStore unavailable for semantic scoring — falling back to contains")
            return await self._score_contains(expected, actual)

        try:
            emb_expected = vs.embed_text(expected)
            emb_actual = vs.embed_text(actual)

            # Cosine similarity
            dot = float(np.dot(emb_expected, emb_actual))
            norm_a = float(np.linalg.norm(emb_expected))
            norm_b = float(np.linalg.norm(emb_actual))

            if norm_a == 0 or norm_b == 0:
                return 0.0

            similarity = dot / (norm_a * norm_b)
            # Clamp to [0, 1]
            return max(0.0, min(1.0, similarity))

        except Exception as e:
            logger.warning("Semantic similarity scoring failed: %s", e)
            return await self._score_contains(expected, actual)

    async def _score_llm_judge(self, input_text: str, expected: str, actual: str, model_id: str) -> float:
        """Use an LLM to grade the output on a 0.0-1.0 scale."""
        llm = self._get_llm()
        if llm is None:
            logger.warning("LLM unavailable for judge scoring — falling back to contains")
            return await self._score_contains(expected, actual)

        judge_prompt = f"""You are an evaluation judge. Score how well the actual output matches the expected output on a scale from 0.0 to 1.0.

Input: {input_text}

Expected Output: {expected}

Actual Output: {actual}

Scoring criteria:
- 1.0 = Perfect match in meaning and completeness
- 0.8 = Mostly correct with minor omissions
- 0.6 = Partially correct, captures main idea but misses details
- 0.4 = Some relevant content but significant gaps
- 0.2 = Minimally relevant
- 0.0 = Completely wrong or irrelevant

Respond with ONLY a single decimal number between 0.0 and 1.0. No explanation."""

        try:
            resp = await llm.chat_with_metadata(
                messages=[{"role": "user", "content": judge_prompt}],
                model=model_id,
                max_tokens=10,
                temperature=0.0,
            )

            if resp.error:
                logger.warning("LLM judge error: %s", resp.error)
                return await self._score_contains(expected, actual)

            # Parse the score
            score_text = resp.content.strip()
            score = float(score_text)
            return max(0.0, min(1.0, score))

        except (ValueError, TypeError) as e:
            logger.warning("Failed to parse LLM judge score: %s", e)
            return await self._score_contains(expected, actual)
        except Exception as e:
            logger.warning("LLM judge scoring failed: %s", e)
            return await self._score_contains(expected, actual)

    async def _score_output(
        self,
        method: str,
        input_text: str,
        expected: str,
        actual: str,
        model_id: str | None = None,
    ) -> tuple[float, dict[str, Any]]:
        """Score output using the specified method.

        Returns (score, details_dict).
        """
        details: dict[str, Any] = {"method": method}

        if method == "exact_match":
            score = await self._score_exact_match(expected, actual)
            details["exact_match"] = score == 1.0

        elif method == "contains":
            score = await self._score_contains(expected, actual)
            details["contains_expected"] = score == 1.0

        elif method == "semantic_similarity":
            score = await self._score_semantic_similarity(expected, actual)
            details["cosine_similarity"] = round(score, 4)

        elif method == "llm_judge":
            if not model_id:
                logger.warning("llm_judge requires model_id — falling back to contains")
                score = await self._score_contains(expected, actual)
                details["fallback"] = "contains (no model_id)"
            else:
                score = await self._score_llm_judge(input_text, expected, actual, model_id)
                details["llm_judge_score"] = round(score, 4)
        else:
            logger.warning("Unknown scoring method %s — using exact_match", method)
            score = await self._score_exact_match(expected, actual)
            details["fallback"] = "exact_match (unknown method)"

        details["score"] = round(score, 4)
        details["passed"] = score >= PASS_THRESHOLD
        return score, details


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_evaluation_service: EvaluationService | None = None


def get_evaluation_service() -> EvaluationService:
    global _evaluation_service
    if _evaluation_service is None:
        _evaluation_service = EvaluationService()
    return _evaluation_service
