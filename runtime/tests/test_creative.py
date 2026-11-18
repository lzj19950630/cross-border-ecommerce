import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from runtime.api import create_app
from runtime.creative import build_creative_registry
from runtime.engine import RuntimeEngine
from runtime.executors import SequentialLayerExecutor
from runtime.llm import FakeLLM
from runtime.storage import InMemoryStore

LISTING = {
    "title": "Carregador Portátil 20000mAh 45W 3 Saídas",
    "description": "Carregador portátil de 20000mAh com saída de 45W.",
    "secondary_points": ["Display digital", "3 saídas"],
}
IMAGE = {
    "image_plan": [{"slot": i, "role": str(i), "message": "x"} for i in range(1, 10)],
    "prompts": [{"slot": i, "prompt": "studio packshot"} for i in range(1, 10)],
}
VIDEO = {
    "script": [
        "Sua air fryer demora uma eternidade para esquentar?",
        "Esta chega a duzentos graus em tres minutos.",
        "Cesto de cinco litros para toda a familia.",
        "Oito programas prontos, so girar o botao.",
        "Frita sem oleo e a louca sai facil.",
        "Traz receitas em portugues e um ano de garantia.",
        "Air Fryer cinco litros, cento e cinquenta a duzentos graus.",
        "Compre agora e transforme sua cozinha.",
    ],
    "storyboard": [{"shot": 1}],
    "subtitles": "...",
}
REVIEW = {
    "patch_suggestions": ["Confira o tamanho antes de comprar."],
    "selling_points_ranked": ["Capacidade", "Display"],
}


def engine_with(responses):
    fake = FakeLLM(responses)
    return RuntimeEngine(
        runners=build_creative_registry(fake),
        executor=SequentialLayerExecutor(),
        store=InMemoryStore(),
    )


class CreativeTest(unittest.TestCase):
    def test_listing_creative(self):
        task = engine_with([LISTING]).run("帮我写一个商品标题")
        self.assertEqual(task.status, "completed", task.error)
        artifact = task.artifacts["listing_creative"]
        self.assertEqual(artifact["creative_source"], "llm")
        self.assertEqual(artifact["title_final"], LISTING["title"])

    def test_image_creative(self):
        task = engine_with([IMAGE]).run("帮我做主图")
        self.assertEqual(task.status, "completed", task.error)
        artifact = task.artifacts["product_image"]
        self.assertEqual(len(artifact["image_plan"]), 9)
        self.assertEqual(len(artifact["prompts"]), 9)

    def test_video_creative(self):
        task = engine_with([VIDEO]).run("帮我做视频")
        self.assertEqual(task.status, "completed", task.error)
        artifact = task.artifacts["product_video"]
        self.assertEqual(artifact["creative_source"], "llm")
        self.assertIn("llm_timing", artifact)

    def test_review_creative(self):
        task = engine_with([REVIEW]).run("帮我分析差评")
        self.assertEqual(task.status, "completed", task.error)
        artifact = task.artifacts["review_analysis"]
        self.assertEqual(artifact["patch_suggestions"], REVIEW["patch_suggestions"])

    def test_llm_failure_falls_back(self):
        fake = FakeLLM([])
        engine = RuntimeEngine(
            runners=build_creative_registry(fake),
            executor=SequentialLayerExecutor(),
            store=InMemoryStore(),
        )
        task = engine.run("帮我写一个商品标题")
        self.assertEqual(task.status, "completed")
        self.assertNotIn("creative_source", task.artifacts["listing_creative"])
        self.assertTrue(any("LLM 创意层失败" in m for m in task.messages))

    def test_retry_after_bad_title(self):
        bad = dict(LISTING, title="X" * 200)
        task = engine_with([bad, LISTING]).run("帮我写一个商品标题")
        self.assertEqual(task.status, "completed", task.error)
        self.assertEqual(task.slices[0]["retries"], 1)
        self.assertTrue(task.artifacts["listing_creative"]["compliance_report"]["passed"])

    def test_compliance_retry(self):
        bad = dict(LISTING, description="Produto 100% original e garantido.")
        task = engine_with([bad, LISTING]).run("帮我写一个商品标题")
        self.assertEqual(task.status, "completed", task.error)
        self.assertEqual(task.slices[0]["retries"], 1)

    def test_compliance_hard_block_after_retries(self):
        bad = dict(LISTING, description="Produto 100% original e garantido.")
        task = engine_with([bad, bad, bad]).run("帮我写一个商品标题")
        self.assertEqual(task.status, "failed")
        self.assertIn("合规硬阻断", task.error)
        self.assertEqual(task.slices[0]["retries"], 2)

    def test_bad_llm_title_fails(self):
        bad = dict(LISTING, title="X" * 200)
        task = engine_with([bad]).run("帮我写一个商品标题")
        self.assertEqual(task.status, "failed")
        self.assertIn("字符", task.error)

    def test_api_creative(self):
        with patch("runtime.api.load_llm_from_env", return_value=FakeLLM([LISTING])):
            client = TestClient(create_app(
                store=InMemoryStore(), executor="sequential", creative=True,
                engine_type="simple",
            ))
            response = client.post("/api/tasks", json={"request": "帮我写一个商品标题"})
        self.assertEqual(response.status_code, 200)
        task = response.json()
        self.assertEqual(task["status"], "completed")
        self.assertEqual(
            task["artifacts"]["listing_creative"]["title_final"],
            LISTING["title"],
        )


if __name__ == "__main__":
    unittest.main()
