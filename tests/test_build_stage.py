from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "build-stage.py"
SPEC = importlib.util.spec_from_file_location("build_stage", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
build_stage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_stage)


def _source_html() -> str:
    days = "\n".join(
        f"  {{ d:'2026-11-{day:02d}', n:{day}, game:'game{day}', "
        f"title:'Day {day}', emoji:'x', clue:'clue{day}' }},"
        for day in range(22, 29)
    )
    games = "\n\n".join(
        f"  /* {index} · game{index} */\n  game{index}: {{ run() {{ return {index}; }} }},"
        for index in range(1, 7)
    )
    return (
        "<html><script>\n"
        "const TEST = location.hash === '#prueba';\n"
        "const at8 = d => new Date(d+'T08:00:00-05:00').getTime();\n"
        "const DAYS = [\n"
        f"{days}\n"
        "];\n"
        "const isOpen = day => TEST || Date.now() >= at8(day.d);\n"
        "   Se abren a las 8:00 a. m. (UTC-5). #prueba abre todo.\n"
        "const GAMES = {\n"
        f"{games}\n"
        "};\n"
        "/* =========================================================\n"
        "   DÍA 28: cuestionario + regalo final\n"
        "const Q = [];\n"
        "showHome();\n</script>\n</body>\n</html>"
    )


import unittest


class BuildStageTests(unittest.TestCase):
    def test_build_opens_the_released_day_at_nine_in_montevideo(self) -> None:
        files = {f"img/{name}": b"image" for name in build_stage.MEMORY_IMAGES}
        html, _assets = build_stage.build(_source_html(), files, date(2026, 11, 26))

        self.assertIn("T07:00:00-05:00", html)
        self.assertIn("at7(day.d)", html)
        self.assertIn("RELEASED_THROUGH = 26;", html)
        self.assertIn("2026-11-27', n:27, game:'locked'", html)
        self.assertNotIn("clue27", html)
        self.assertNotIn("location.hash", html)
