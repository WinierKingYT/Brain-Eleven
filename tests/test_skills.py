"""Skill trio installed by `install` (2026-10-14)."""

import re

from brain_eleven.runtime.install import SKILLS, SKILL_TEMPLATES, install, render_skill, uninstall
from tests.test_pre13_runtime import runtime  # noqa: F401  (fixture)


def _skill(home, name):
    return home / '.claude' / 'skills' / name / 'SKILL.md'


def test_templates_have_frontmatter_and_only_known_placeholders():
    for name in SKILLS:
        text = (SKILL_TEMPLATES / name / 'SKILL.md').read_text(encoding='utf-8')
        assert text.startswith('---\nname: ' + name + '\ndescription: ')
        assert set(re.findall(r'{{[A-Z_]+}}', text)) <= {'{{PYTHON}}', '{{VAULT_PATH}}'}


def test_install_writes_skills_and_uninstall_removes_them(runtime, tmp_path):  # noqa: F811
    vault, _ = runtime
    home = tmp_path / 'home'
    result = install(vault, home=home)
    assert result['skills'] == sorted(SKILLS) and result['skills_skipped_modified'] == []
    text = _skill(home, 'beyin').read_text(encoding='utf-8')
    assert '{{' not in text and str(vault.resolve()) in text
    assert install(vault, home=home)['skills_skipped_modified'] == []  # repeat is harmless
    uninstall(vault)
    assert not any(_skill(home, name).exists() for name in SKILLS)


def test_a_skill_the_owner_changed_is_never_overwritten_or_removed(runtime, tmp_path):  # noqa: F811
    vault, _ = runtime
    home = tmp_path / 'home'
    install(vault, home=home)
    path = _skill(home, 'beyin-doktor')
    path.write_text('benim notlarım', encoding='utf-8')
    assert install(vault, home=home)['skills_skipped_modified'] == ['beyin-doktor']
    assert path.read_text(encoding='utf-8') == 'benim notlarım'
    uninstall(vault)
    assert path.read_text(encoding='utf-8') == 'benim notlarım'
    assert not _skill(home, 'beyin').exists()


def test_a_foreign_skill_with_the_same_name_is_left_alone(runtime, tmp_path):  # noqa: F811
    vault, _ = runtime
    home = tmp_path / 'home'
    path = _skill(home, 'beyin')
    path.parent.mkdir(parents=True)
    path.write_text('başka bir beyin skill', encoding='utf-8')
    assert install(vault, home=home)['skills_skipped_modified'] == ['beyin']
    assert path.read_text(encoding='utf-8') == 'başka bir beyin skill'


def test_render_fills_paths(tmp_path):
    text = render_skill('beyin-guncelle', tmp_path)
    assert str(tmp_path.resolve()) in text and '{{' not in text
