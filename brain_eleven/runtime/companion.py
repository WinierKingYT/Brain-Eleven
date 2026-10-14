"""Who the owner is and how they want to work, in every session.

Two owner notes in ``🔮 Companion/``: ``Core.md`` (who the owner is, how we
work together) and ``Kurallar.md`` (corrections the owner made, one rule per
line with its reason). Both are owner-level, not per project. They open every
native SessionStart context before anything else, and a prompt that asks
"where were we / do you know me" gets them too, so continuity never depends on
a keyword search hitting.

These are the owner's notes, not canonical memory: the agent may add a
correction to ``Kurallar.md`` when the owner corrects it (the beyin skill says
how), and the owner edits both freely. Lines that look like secrets are never
injected. The question patterns follow avenoxbeyin's companion module (MIT).
"""
from pathlib import Path
import re
import unicodedata

COMPANION_DIR = Path('🔮 Companion')
CORE, RULES = 'Core.md', 'Kurallar.md'
LIMITS = {RULES: 1500, CORE: 1200}
HEADING = '## Seni tanıma (sahibin notları)'
STARTERS = {
    CORE: ('# Core\n\n'
           '<!-- Sahibin kendisi ve birlikte çalışma biçimi. Brain-Eleven her oturum başında bunu okur. '
           'Kısa tut; uzun anlatım ayrı nota gider. -->\n\n'
           '## Ben\n\n- (adın, hitap, ne üzerinde çalıştığın; eski profil: `Jane - Core.md`)\n\n'
           '## Birlikte çalışma\n\n- (nasıl cevap istersin: dil, uzunluk, ton)\n\n'
           '## Asla unutulmaması gerekenler\n\n- (henüz yok)\n'),
    RULES: ('# Kurallar\n\n'
            '<!-- Sahip ajanı düzelttiğinde buraya bir madde eklenir: kural ne, tek cümleyle neden. '
            'Geçici istekler kural değildir. Geçerliliğini yitiren kural silinir. -->\n\n'
            '- (henüz kural yok)\n'),
}
_COMMENT = re.compile(r'<!--.*?-->', re.S)
_FRONTMATTER = re.compile(r'\A---\n.*?\n---\n', re.S)
_FOLD = str.maketrans('ıİ', 'iI')
_RETURNING = re.compile(
    r'\b(?:ne(?:ler)? (?:yaptik|yapmistik|yapiyorduk)|nere?deydik|nerede kal(?:dik|mistik|diydik)|kaldigimiz (?:yer|konu)'
    r'|son durum(?:umuz)? (?:ne|nedir|neydi)\b|ne olmustu|(?:tatil|izin)den don(?:dum|duk)\b'
    r'|son (?:oturum|konusma)|gecen (?:sefer|oturum|konusma)|beni (?:tani|hatirla)|kisilig|tercihlerim|sen kimsin'
    r'|what (?:did|have) we (?:do|done|work(?:ed)? on)|what were we (?:doing|working on)|where were we'
    r'|catch me up|remember me|who am i|my preferences)')


def _fold(text):
    decomposed = unicodedata.normalize('NFKD', text.translate(_FOLD))
    return ''.join(c for c in decomposed if not unicodedata.combining(c)).lower()


def returning(prompt):
    """Whether a prompt asks where the work stood or who the owner is."""
    return isinstance(prompt, str) and bool(_RETURNING.search(_fold(prompt)))


def ensure_starters(vault):
    """Create the two notes once; an existing note is never touched."""
    created = []
    for name, text in STARTERS.items():
        path = Path(vault) / COMPANION_DIR / name
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
            created.append(name)
    return created


def _clean(text):
    text = _COMMENT.sub('', _FRONTMATTER.sub('', text.replace('\r\n', '\n')))
    return text


def _starter_body(name):
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(l.rstrip() for l in _clean(STARTERS[name]).split('\n'))).strip()


def _body(vault, name):
    from context_compiler_v2.safety import contains_secret
    path = Path(vault) / COMPANION_DIR / name
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return ''
    text = _clean(text)
    lines = [line.rstrip() for line in text.split('\n') if not contains_secret(line)]
    body = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()
    if body == _starter_body(name):
        return ''  # untouched starter: nothing personal to tell yet
    limit = LIMITS[name]
    if len(body) > limit:
        cut = body.rfind('\n', 0, limit)
        body = body[:cut if cut > limit // 2 else limit].rstrip() + f'\n… (kısaltıldı; tamamı `🔮 Companion/{name}`)'
    return body


EMPTY_HINT = ('`🔮 Companion/Core.md` henüz boş: sahibi tanıdıkça (ad, çalışma biçimi, kalıcı tercihler) '
              'kısa maddelerle doldur; uydurma.')
RULE_HINT = ('Sahip seni düzeltirse aynı oturumda `🔮 Companion/Kurallar.md` dosyasına bir madde ekle: '
             'kural ve tek cümlelik nedeni.')


def section(vault, *, hints=False):
    """The owner notes for a context, rules first. With ``hints`` the agent is told how they grow."""
    rules, core = _body(vault, RULES), _body(vault, CORE)
    parts = [part for part in (rules, core) if part]
    if hints:
        parts.append(RULE_HINT if core else EMPTY_HINT + ' ' + RULE_HINT)
    if not parts:
        return ''
    return HEADING + '\n\n' + '\n\n'.join(parts)
