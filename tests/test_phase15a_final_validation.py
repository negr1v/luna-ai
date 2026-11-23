"""
ACCIO JARVIS V15 - PHASE 15A FINAL VALIDATION TEST SUITE
Runs targeted checks across 15A.1 - 15A.4:
1. Paid API protection (single-use token, 402 block)
2. Free-first routing (zero-price preference, anti-silent-fallback)
3. Terminal permission denial (irreversible block, bypass prevention)
4. Smart rate limiting (concurrency, 429, no duplicate billed requests)
5. Normal chat & SSE streaming pipeline
6. Existing Approval Center workflow
7. Memory and task data file integrity
"""

import os
import sys
import json
import time
import asyncio
import unittest
from unittest.mock import patch, MagicMock
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jarvis_server
from jarvis_server import (
    handle_chat,
    handle_chat_stream,
    handle_request_paid_auth,
    get_model_cost_category,
    create_paid_model_authorization,
    validate_and_consume_paid_authorization,
    select_free_first_model,
    SMART_PROVIDER_LIMITER,
    PAID_MODEL_AUTHORIZATIONS
)
from jarvis_agent_engine import (
    AgentController,
    TaskState,
    PermissionLevel,
    TaskStep
)


class Phase15AFinalValidation(AioHTTPTestCase):

    async def get_application(self):
        app = web.Application()
        app.router.add_post("/api/chat", handle_chat)
        app.router.add_post("/api/chat/stream", handle_chat_stream)
        app.router.add_post("/api/models/paid_auth/request", handle_request_paid_auth)
        return app

    def setUp(self):
        super().setUp()
        PAID_MODEL_AUTHORIZATIONS.clear()

    # 1. Paid API Protection
    async def test_01_paid_api_protection(self):
        """Paid model without authorization must return HTTP 402; valid token allows consumption once."""
        # Unapproved request -> 402
        resp = await self.client.post("/api/chat", json={
            "message": "Analiz yap",
            "config": {"model": "openai/gpt-4o"}
        })
        self.assertEqual(resp.status, 402)
        data = await resp.json()
        self.assertEqual(data["error_code"], "PAID_MODEL_CONFIRMATION_REQUIRED")
        self.assertTrue(data["auth_token"].startswith("pauth_"))

        # Single-use consumption
        token = create_paid_model_authorization("openai/gpt-4o", "openrouter")
        valid, err = validate_and_consume_paid_authorization(token, "openai/gpt-4o", "openrouter")
        self.assertTrue(valid)

        # Replay attempt must fail
        valid2, err2 = validate_and_consume_paid_authorization(token, "openai/gpt-4o", "openrouter")
        self.assertFalse(valid2)

    # 2. Free-First Routing
    def test_02_free_first_routing(self):
        """Auto routing must select a verified free model and never select paid models."""
        cfg = {"openrouter_api_key": "sk-or-test", "groq_api_key": "gsk-test"}
        model_id, meta, reason = select_free_first_model(cfg=cfg)
        self.assertIsNotNone(model_id)
        cost_cat, _ = get_model_cost_category(model_id)
        self.assertEqual(cost_cat, "free")

    # 3. Terminal Permission Denial
    async def test_03_terminal_permission_denial(self):
        """Rejected step halts task permanently; cannot be retried or bypassed."""
        controller = AgentController(os.path.dirname(os.path.abspath(__file__)))
        task = controller.create_task("ekran görüntüsü al")
        await controller.execute_task(task.task_id)

        # Reject
        ok = controller.reject_step(task.task_id, step_id=1, reason="Güvenlik reddi")
        self.assertTrue(ok)
        self.assertEqual(task.state, TaskState.TERMINAL_DENIED)

        # Retry must immediately stop
        retried = await controller.execute_task(task.task_id)
        self.assertEqual(retried.state, TaskState.TERMINAL_DENIED)
        self.assertIn("Terminal Reddi", retried.error)

    # 4. Rate Limiting & No Billed Duplication
    async def test_04_rate_limiting_and_no_billed_duplication(self):
        """Smart rate limiter throttles provider and refuses automatic retries for billed calls."""
        # Billed request 429
        can_retry_billed, cooldown = SMART_PROVIDER_LIMITER.record_response("openrouter", 429, retry_after_header="3", is_billed=True)
        self.assertFalse(can_retry_billed)
        self.assertEqual(cooldown, 3.0)

        # Provider is now in cooldown
        allowed, reason, _ = await SMART_PROVIDER_LIMITER.acquire_slot("openrouter")
        self.assertFalse(allowed)
        self.assertEqual(reason, "COOLDOWN_ACTIVE")
        SMART_PROVIDER_LIMITER.get_state("openrouter").cooldown_until = 0.0

    # 5. Normal Chat & SSE Streaming Pipeline
    async def test_05_chat_and_sse_pipeline(self):
        """Normal chat handles valid requests cleanly; SSE streams structured events."""
        # Chat without Groq key returns graceful prompt response
        resp = await self.client.post("/api/chat", json={
            "message": "Naber JARVIS",
            "config": {"model": "llama-3.3-70b-versatile"}
        })
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertIn("reply", data)

        # SSE endpoint responds with text/event-stream
        sse_resp = await self.client.post("/api/chat/stream", json={
            "message": "Durum kontrolü",
            "config": {"model": "llama-3.3-70b-versatile"}
        })
        self.assertEqual(sse_resp.status, 200)
        self.assertIn("text/event-stream", sse_resp.headers.get("Content-Type", ""))

    # 6. Existing Approval Center Workflow
    async def test_06_approval_center_workflow(self):
        """Legitimate user approval resumes execution to completion."""
        controller = AgentController(os.path.dirname(os.path.abspath(__file__)))
        task = controller.create_task("ekran görüntüsü al")
        await controller.execute_task(task.task_id)
        self.assertEqual(task.state, TaskState.AWAITING_APPROVAL)

        # Approve step
        step = next((s for s in task.steps if s.step_id == 1), None)
        approval_id = step.approval_id if step else None
        approved = controller.approve_step(task.task_id, step_id=1, approval_id=approval_id)
        self.assertTrue(approved)
        self.assertEqual(task.state, TaskState.APPROVED)

    # 7. Memory and Task Data Integrity
    def test_07_data_integrity(self):
        """JSON storage files exist, parse correctly, and have valid schemas."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        mem_file = os.path.join(base_dir, "jarvis_memory.json")
        tasks_file = os.path.join(base_dir, "jarvis_tasks.json")

        self.assertTrue(os.path.exists(mem_file))
        self.assertTrue(os.path.exists(tasks_file))

        with open(mem_file, "r", encoding="utf-8") as f:
            mem = json.load(f)
            self.assertIsInstance(mem, dict)
            self.assertIn("revision", mem)

        with open(tasks_file, "r", encoding="utf-8") as f:
            tasks = json.load(f)
            self.assertTrue(isinstance(tasks, (dict, list)))


if __name__ == "__main__":
    unittest.main()
