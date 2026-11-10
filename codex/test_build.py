"""Exercise packaging and install/update/removal in disposable homes (no AI calls)."""
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("codex_build", ROOT / "codex/build.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class CodexPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.codex_home = self.home / "codex config with spaces"
        self.env = dict(os.environ, HOME=str(self.home), CODEX_HOME=str(self.codex_home))

    def run_script(self, script, *args, success=True):
        result = subprocess.run(["bash", str(ROOT / script), *args], env=self.env,
                                capture_output=True, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def test_build_preserves_all_ten_role_templates_and_handoffs(self):
        output = self.home / "bundle"
        builder.build(output)
        roles = output / "references/roles"
        self.assertEqual(len(list(roles.glob("*.md"))), 10)
        for name in builder.ROLES:
            source = (builder.SOURCES / f"{name}.md").read_text()
            generated = (roles / f"{name}.md").read_text()
            # The substantive role headings/output template survive runtime conversion.
            self.assertEqual(re.findall(r"^#{1,3} .*$", source, re.M),
                             re.findall(r"^#{1,3} .*$", generated, re.M))
            self.assertIn("**Status:**", generated)
        self.assertTrue((output / "LICENSE").is_file())
        self.assertFalse((output / "references/roles/solution-architect.md").read_text().startswith("---"))

    def test_install_update_backup_and_uninstall_leave_other_files_alone(self):
        claude_file = self.home / ".claude/agents/existing.md"
        claude_file.parent.mkdir(parents=True)
        claude_file.write_text("original Claude agent")
        other_skill = self.codex_home / "skills/other/SKILL.md"
        other_skill.parent.mkdir(parents=True)
        other_skill.write_text("unrelated skill")
        self.run_script("install.sh", "--codex")
        dest = self.codex_home / "skills/idea-team"
        builder.validate(dest)
        (dest / "local-note.md").write_text("preserve this local edit")
        self.run_script("install.sh", "--codex")
        backups = list((self.codex_home / "backups").glob("*/idea-team/local-note.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "preserve this local edit")
        self.run_script("uninstall.sh", "--codex")
        self.assertFalse(dest.exists())
        self.assertEqual(other_skill.read_text(), "unrelated skill")
        self.assertEqual(claude_file.read_text(), "original Claude agent")
        self.assertTrue(backups[0].exists())
        self.run_script("uninstall.sh", "--codex")

    def test_refuses_unmanaged_install_and_uninstall(self):
        dest = self.codex_home / "skills/idea-team"
        dest.mkdir(parents=True)
        note = dest / "SKILL.md"
        note.write_text("a skill the user already had")
        for script in ("install.sh", "uninstall.sh"):
            self.run_script(script, "--codex", success=False)
            self.assertEqual(note.read_text(), "a skill the user already had")

    def test_refuses_symlink_install_and_uninstall(self):
        elsewhere = self.home / "another skill"
        elsewhere.mkdir()
        note = elsewhere / "SKILL.md"
        note.write_text("do not touch")
        dest = self.codex_home / "skills/idea-team"
        dest.parent.mkdir(parents=True)
        dest.symlink_to(elsewhere, target_is_directory=True)
        for script in ("install.sh", "uninstall.sh"):
            self.run_script(script, "--codex", success=False)
            self.assertEqual(note.read_text(), "do not touch")
            self.assertTrue(dest.is_symlink())

    def test_build_refuses_existing_directory(self):
        output = self.home / "existing"
        output.mkdir()
        note = output / "keep.txt"
        note.write_text("keep")
        with self.assertRaises(FileExistsError):
            builder.build(output)
        self.assertEqual(note.read_text(), "keep")

    def test_every_replacement_still_matches_the_sources(self):
        builder.check_replacements()
        shared = (builder.SOURCES / "_shared.md").read_text()
        self.assertNotIn("such as Codex.", builder.adapt(shared))

    def test_invalid_cli_flags_do_not_install(self):
        self.run_script("install.sh", "--unknown", success=False)
        self.run_script("install.sh", "--codex", "--output", str(self.home / "bad"), success=False)
        self.assertFalse((self.codex_home / "skills/idea-team").exists())


if __name__ == "__main__":
    unittest.main()
