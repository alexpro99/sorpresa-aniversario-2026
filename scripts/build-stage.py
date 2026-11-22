#!/usr/bin/env python3
"""Build only the calendar content that is allowed to be public on a given day."""
from __future__ import annotations

import argparse
import re
import shutil
import stat
import zipfile
from datetime import date
from pathlib import Path, PurePosixPath

START = date(2026, 11, 22)
END = date(2026, 11, 28)
MEMORY_IMAGES = ('gym.jpg', 'helado.jpg', 'piscina.jpg', 'playa.jpg', 'delfines.jpg', 'urraca.jpg')
TEST_BYPASS = "const TEST = location.hash === '#prueba';"


def read_safe_archive(archive: zipfile.ZipFile) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        mode = (info.external_attr >> 16) & 0xFFFF
        if path.is_absolute() or '..' in path.parts or stat.S_ISLNK(mode):
            raise ValueError(f'Unsafe archive entry: {info.filename}')
        if info.is_dir():
            continue
        key = path.as_posix()
        if key in files:
            raise ValueError(f'Duplicate archive entry: {key}')
        files[key] = archive.read(info)
    return files


def trim_days(html: str, release_day: int) -> str:
    start = html.index('const DAYS = [')
    end = html.index('\n];\nconst isOpen', start)
    inner_start = html.index('\n', start) + 1
    inner = html[inner_start:end]
    entry_starts = list(re.finditer(r"(?m)^  \{ d:'(2026-11-\d{2})',", inner))
    if len(entry_starts) != 7:
        raise ValueError(f'Expected 7 calendar entries, found {len(entry_starts)}')
    entries = []
    for index, match in enumerate(entry_starts):
        entry_end = entry_starts[index + 1].start() if index + 1 < len(entry_starts) else len(inner)
        entry = inner[match.start():entry_end].strip().rstrip(',')
        entry_date = date.fromisoformat(match.group(1))
        if entry_date.day <= release_day:
            entries.append(entry)
        else:
            entries.append(
                f"{{ d:'{entry_date.isoformat()}', n:{entry_date.day}, game:'locked', "
                "title:'Sorpresa diaria', emoji:'🔒', clue:'' }"
            )
    replacement = 'const DAYS = [\n  ' + ',\n  '.join(entries) + '\n];'
    replacement += f'\nconst RELEASED_THROUGH = {release_day};'
    replacement += '\nconst isOpen = day => TEST || (day.n <= RELEASED_THROUGH && Date.now() >= at8(day.d));'
    original_is_open = '\n];\nconst isOpen = day => TEST || Date.now() >= at8(day.d);'
    return html[:start] + replacement + html[end + len(original_is_open):]


def trim_games(html: str, game_count: int) -> str:
    start = html.index('const GAMES = {')
    body_start = html.index('\n', start) + 1
    end = html.index('\n};', body_start)
    body = html[body_start:end]
    headers = list(re.finditer(r'(?m)^  /\* (\d+) · [^\n]*\*/', body))
    if len(headers) != 6:
        raise ValueError(f'Expected 6 mini-games, found {len(headers)}')
    kept = []
    for i, header in enumerate(headers):
        section_end = headers[i + 1].start() if i + 1 < len(headers) else len(body)
        if int(header.group(1)) <= game_count:
            kept.append(body[header.start():section_end].rstrip())
    if len(kept) != game_count:
        raise ValueError(f'Expected {game_count} game implementations, found {len(kept)}')
    replacement = 'const GAMES = {\n  ' + '\n\n  '.join(kept) + '\n};'
    return html[:start] + replacement + html[end + 3:]


def remove_final_payload(html: str) -> str:
    marker = '/* =========================================================\n   DÍA 28: cuestionario + regalo final'
    start = html.index(marker)
    end_marker = '\nshowHome();\n</script>\n</body>\n</html>'
    end = html.rfind(end_marker)
    if end < start:
        raise ValueError('Could not locate the final-page script boundary.')
    return html[:start] + '\nshowHome();\n</script>\n</body>\n</html>'


def build(html: str, files: dict[str, bytes], release_date: date) -> tuple[str, dict[str, bytes]]:
    if release_date < START or release_date > END:
        raise ValueError('Release date must be from 2026-11-22 through 2026-11-28.')
    day = release_date.day
    html = html.replace(TEST_BYPASS, 'const TEST = false;')
    html = html.replace('   Se abren a las 8:00 a. m. (UTC-5). #prueba abre todo.',
                        '   Cada juego aparece en la fecha programada. El modo de prueba está desactivado.')
    if "#prueba" in html or TEST_BYPASS in html:
        raise ValueError('The #prueba bypass was not removed.')
    html = trim_days(html, day)
    game_count = min(day - 21, 6)
    html = trim_games(html, game_count)
    html = html.replace("if(s<=0){ showHome(); return; }", "if(s<=0){ el.textContent='Recarga esta página para ver el nuevo juego.'; return; }")
    if day < 28:
        html = remove_final_payload(html)
    if day < 28 and 'const Q = [' in html:
        raise ValueError('Final-stage code leaked into a pre-final stage.')
    if 'location.hash' in html:
        raise ValueError('Hash-based bypass remains in the released page.')

    if day == 28:
        expected_assets = [name for name in files if name.startswith('img/')]
    else:
        expected_assets = [f'img/{name}' for name in MEMORY_IMAGES]
    missing = [name for name in expected_assets if name not in files]
    if missing:
        raise ValueError(f'Release images missing from uploaded package: {missing}')
    assets = {name: files[name] for name in expected_assets}
    return html, assets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path, help='Original anniversary ZIP')
    parser.add_argument('--date', required=True, type=date.fromisoformat, help='UTC calendar date')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()

    with zipfile.ZipFile(args.input) as archive:
        files = read_safe_archive(archive)
    if 'index.html' not in files:
        raise ValueError('Uploaded package has no index.html')
    html, assets = build(files['index.html'].decode('utf-8'), files, args.date)

    if args.output.exists():
        shutil.rmtree(args.output)
    (args.output / 'img').mkdir(parents=True)
    (args.output / 'index.html').write_text(html, encoding='utf-8')
    for name, data in assets.items():
        (args.output / name).write_bytes(data)
    print(f'stage={args.date.isoformat()} games={min(args.date.day - 21, 6)} final={args.date.day == 28} assets={len(assets)}')


if __name__ == '__main__':
    main()
