#!/usr/bin/env python3
"""Регрессия аудита дыр захвата 04.08.2026 (H1, H2, H3, H4, H6, H7).

Инварианты:
- H1: падение модели = честный ответ с контактами, ход в логе, алерт (не голый 500).
- H2: сбой дистилляции НЕ помечает беседу обработанной (карточка не теряется навсегда).
- H3: неизвестный session_id восстанавливает историю из durable-лога (рестарт без амнезии).
- H4: «передам команде» без create_lead перегенерируется.
- H6: дневной потолок расхода реально останавливает и отвечает fallback-ом.
- H7: цикл инструментов ограничен 8 ходами и заканчивается честным ответом.

Запуск: python3 test_chat_resilience.py (офлайн, модель замокана).
"""
import json
import os
import tempfile
import time
import types
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import app as appmod
import distill


def text_resp(text):
    block = types.SimpleNamespace(type="text", text=text)
    return types.SimpleNamespace(content=[block], stop_reason="end_turn",
                                 usage=types.SimpleNamespace(input_tokens=100, output_tokens=50))


def tool_resp():
    block = types.SimpleNamespace(type="tool_use", name="search_products",
                                  input={"constraints": []}, id="tu_1")
    return types.SimpleNamespace(content=[block], stop_reason="tool_use",
                                 usage=types.SimpleNamespace(input_tokens=100, output_tokens=50))


class Base(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(appmod.app)
        self.tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
        self.tmp.close()
        self._patches = [
            mock.patch.object(appmod, "LOG_PATH", self.tmp.name),
            mock.patch.object(appmod, "_send_problem_alert"),
        ]
        self.alert = None
        started = [p.start() for p in self._patches]
        self.alert = started[1]
        appmod._last_problem_alert["ts"] = 0.0
        appmod._spend.update({"day": None, "eur": 0.0, "alerted": False})
        appmod.sessions.clear()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        os.unlink(self.tmp.name)


class H1ModelDown(Base):
    def test_model_error_gives_contacts_logs_and_alerts(self):
        with mock.patch.object(appmod.ai.messages, "create", side_effect=RuntimeError("credit low")):
            r = self.client.post("/chat", json={"message": "Hallo"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("02131 2917676", r.json()["reply"])
        logged = open(self.tmp.name).read()
        self.assertIn("Hallo", logged)
        self.assertTrue(self.alert.called)


class H6SpendCeiling(Base):
    def test_ceiling_switches_to_fallback(self):
        appmod._spend.update({"day": time.strftime("%Y-%m-%d", time.gmtime()), "eur": 10_000.0})
        with mock.patch.object(appmod.ai.messages, "create") as m:
            r = self.client.post("/chat", json={"message": "Hallo"})
            m.assert_not_called()
        self.assertIn("kontaktieren Sie uns", r.json()["reply"])

    def test_usage_accumulates(self):
        with mock.patch.object(appmod.ai.messages, "create", return_value=text_resp("Hallo!")):
            self.client.post("/chat", json={"message": "Hi"})
        self.assertGreater(appmod._spend["eur"], 0)


class H7ToolLoopCap(Base):
    def test_loop_capped_with_honest_fallback(self):
        with mock.patch.object(appmod.ai.messages, "create", return_value=tool_resp()) as m, \
             mock.patch.object(appmod, "_dispatch_tool", return_value={"ok": True}):
            r = self.client.post("/chat", json={"message": "Hallo"})
        self.assertEqual(m.call_count, 8)
        self.assertIn("02131 2917676", r.json()["reply"])


class H3SessionRebuild(Base):
    def test_unknown_sid_rebuilds_from_log(self):
        recs = [{"ts": "2026-08-04T10:00:00Z", "session_id": "restored-1",
                 "user": "Ich suche Vinyl", "assistant": "Gerne! Welche Optik?", "options": [], "tools": []}]
        with open(self.tmp.name, "w") as f:
            for rec in recs:
                f.write(json.dumps(rec) + "\n")
        seen = {}

        def fake_create(**kw):
            seen["messages"] = list(kw["messages"])
            return text_resp("Weiter geht's.")

        with mock.patch.object(appmod.ai.messages, "create", side_effect=fake_create):
            r = self.client.post("/chat", json={"message": "Holzoptik bitte", "session_id": "restored-1"})
        self.assertEqual(r.status_code, 200)
        msgs = seen["messages"]
        self.assertEqual(len(msgs), 3)  # восстановленная пара + новое сообщение
        self.assertIn("Ich suche Vinyl", msgs[0]["content"])
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[1]["role"], "assistant")


class H4HandoffGuard(Base):
    def test_promised_handoff_without_lead_regenerates(self):
        replies = [text_resp("Ich leite Ihre Anfrage an unser Team weiter."),
                   text_resp("Gerne! Darf ich dafür Ihren Namen und eine Telefonnummer aufnehmen?")]
        with mock.patch.object(appmod.ai.messages, "create", side_effect=replies) as m:
            r = self.client.post("/chat", json={"message": "Haben Sie weissen Supermatt-Boden?"})
        self.assertEqual(m.call_count, 2)
        self.assertIn("Namen", r.json()["reply"])

    def test_handoff_ok_when_lead_created_earlier(self):
        appmod.sessions["s-lead"] = {"messages": [], "last_active": time.time(), "lead_done": True}
        with mock.patch.object(appmod.ai.messages, "create",
                               return_value=text_resp("Unser Team meldet sich bei Ihnen.")) as m:
            r = self.client.post("/chat", json={"message": "Danke", "session_id": "s-lead"})
        self.assertEqual(m.call_count, 1)
        self.assertIn("Team meldet sich", r.json()["reply"])


class H2DistillRetry(unittest.TestCase):
    def _run(self, last_age_secs):
        now = time.time()
        tmpd = tempfile.mkdtemp()
        log = os.path.join(tmpd, "conv.jsonl")
        cards = os.path.join(tmpd, "cards.jsonl")
        marker = os.path.join(tmpd, "marker.json")
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - last_age_secs))
        with open(log, "w") as f:
            f.write(json.dumps({"ts": ts, "session_id": "conv-1",
                                "user": "Hallo", "assistant": "Guten Tag"}) + "\n")
        failing = types.SimpleNamespace(messages=types.SimpleNamespace(
            create=mock.Mock(side_effect=RuntimeError("api down"))))
        distill.run_distill(log, cards, marker, failing, "model-x", now=now)
        try:
            marked = json.load(open(marker))
        except FileNotFoundError:
            marked = {}
        return "conv-1" in marked

    def test_fresh_failure_is_retried_not_marked(self):
        self.assertFalse(self._run(last_age_secs=10 * 3600))

    def test_giving_up_only_near_purge(self):
        self.assertTrue(self._run(last_age_secs=45 * 3600))


if __name__ == "__main__":
    unittest.main(verbosity=1)
