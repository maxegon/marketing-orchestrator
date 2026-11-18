import datetime as dt
import unittest

import tick

UTC = dt.timezone.utc


class Slot(unittest.TestCase):
    def test_inverno_e_estate(self):
        self.assertEqual(tick.slot(dt.datetime(2026, 11, 19, 9, 15, 3, tzinfo=UTC)), "10:15")   # CET
        self.assertEqual(tick.slot(dt.datetime(2027, 7, 1, 8, 15, 3, tzinfo=UTC)), "10:15")     # CEST

    def test_arrotonda_anticipo_e_ritardo(self):
        self.assertEqual(tick.slot(dt.datetime(2026, 11, 19, 9, 14, 40, tzinfo=UTC)), "10:15")
        self.assertEqual(tick.slot(dt.datetime(2026, 11, 19, 9, 17, 20, tzinfo=UTC)), "10:15")
        self.assertEqual(tick.slot(dt.datetime(2026, 11, 19, 9, 17, 40, tzinfo=UTC)), "10:20")

    def test_mezzanotte(self):
        self.assertEqual(tick.slot(dt.datetime(2026, 11, 19, 22, 58, 0, tzinfo=UTC)), "00:00")


class Orari(unittest.TestCase):
    def test_file_valido(self):
        self.assertEqual(tick.validate(tick.load()), [])

    def test_errori(self):
        cfg = {"owner": "x", "jobs": [{"ora": "10:12", "repo": "a", "workflow": "w.yml"},
                                       {"ora": "25:00", "repo": "a", "workflow": "w.yml"},
                                       {"ora": "10:15", "repo": "a", "workflow": "w.yml", "inputs": {"x": True}},
                                       {"ora": "10:20", "repo": "a", "workflow": "w.yml"},
                                       {"ora": "10:20", "repo": "A", "workflow": "w.yml"}]}
        errs = " | ".join(tick.validate(cfg))
        for frag in ("multipla di 5", "non valida", "oggetto di stringhe", "doppione"):
            self.assertIn(frag, errs)

    def test_render_podcast_alle_20(self):
        giri = tick.due(tick.load(), "20:00")
        pvl = [j for j in giri if j["repo"] == "PodcastViewLens"]
        self.assertEqual(pvl, [{"ora": "20:00", "repo": "PodcastViewLens", "workflow": "marketing-render.yml",
                                "inputs": {"azione": "genera", "publish_assets": "true", "anteprima": "true"}}])


class Dispatch(unittest.TestCase):
    J = {"repo": "r", "workflow": "w.yml", "inputs": {"azione": "oggi"}}

    def test_ok_e_body(self):
        calls = []
        ok = tick.dispatch("o", self.J, "t", http=lambda u, b, t: calls.append((u, b)) or (204, ""), sleep=lambda s: 0)
        self.assertTrue(ok)
        self.assertEqual(calls, [("https://api.github.com/repos/o/r/actions/workflows/w.yml/dispatches",
                                  {"ref": "main", "inputs": {"azione": "oggi"}})])

    def test_senza_inputs_niente_campo(self):
        calls = []
        tick.dispatch("o", {"repo": "r", "workflow": "w.yml"}, "t",
                      http=lambda u, b, t: calls.append(b) or (204, ""), sleep=lambda s: 0)
        self.assertEqual(calls, [{"ref": "main"}])

    def test_5xx_riprova_4xx_no(self):
        n = []
        self.assertFalse(tick.dispatch("o", self.J, "t", http=lambda u, b, t: n.append(1) or (502, "x"), sleep=lambda s: 0))
        self.assertEqual(len(n), 3)
        n.clear()
        self.assertFalse(tick.dispatch("o", self.J, "t", http=lambda u, b, t: n.append(1) or (401, "x"), sleep=lambda s: 0))
        self.assertEqual(len(n), 1)

    def test_rete_poi_ok(self):
        seq = iter([OSError("rete"), (204, "")])

        def http(u, b, t):
            r = next(seq)
            if isinstance(r, Exception):
                raise r
            return r
        self.assertTrue(tick.dispatch("o", self.J, "t", http=http, sleep=lambda s: 0))


class Main(unittest.TestCase):
    # stdout silenziato: il messaggio ::error:: del test senza token diventerebbe un'annotazione di errore su GitHub
    def run(self, result=None):
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            return super().run(result)

    def test_dry_run_senza_token(self):
        self.assertEqual(tick.main(["--dry-run", "--ora", "20:00"]), 0)

    def test_senza_token_errore(self):
        import os
        os.environ.pop("ORCH_TOKEN", None)
        self.assertEqual(tick.main(["--ora", "20:00"]), 1)

    def test_slot_vuoto_ok(self):
        self.assertEqual(tick.main(["--ora", "03:00"]), 0)


if __name__ == "__main__":
    unittest.main()
