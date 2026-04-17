"""Build a sample vault directory for E2E tests."""
from pathlib import Path


TEMPLATE = """---
source: apple_notes
note_id: fake-uuid-{idx}
title: {title}
created: '2026-04-17T09:00:00Z'
modified: '2026-04-17T09:00:00Z'
synced: '2026-04-17T09:00:00Z'
tags: []
classification:
  folder: {folder}
  confidence: 0.9
  reasoning: test fixture
  likely_sensitive: false
---

# {title}

<!-- APPLE-NOTES-START -->
{body}
<!-- APPLE-NOTES-END -->

## TODO

## Powiązane
"""


NOTES = [
    ("APP-Dev", "CosmicForge Bug", "Deploy crash on production. Race condition in auth flow."),
    ("APP-Dev", "Smart Home Integration", "HomeKit accessory auto-discovery and pairing issues."),
    ("APP-Dev", "API Endpoint Design", "REST vs gRPC trade-offs for internal microservices."),
    ("Ideas", "PoC Contract Testing Konkurs AILAB", "Koncepcja PoC contract testing z embeddings dla AI LAB 2."),
    ("Ideas", "Blog Post Pomysl", "Pomysl na artykul o test-driven development w Pythonie."),
    ("Work", "Retro Sprint", "Retrospective sprint 2026-Q2. Team did great on feature X."),
    ("Work", "Meeting Q4 Planning", "Q4 planning session. OKRs for infra team."),
    ("Personal", "Lista Zakupow", "Kup chleb, mleko, maslo. Zadzwon do mechanika po opony."),
    ("Personal", "Serwis Auta", "Auto ma przeglad w piatek. Sprawdzic cisnienie w oponach."),
    ("Inbox", "Random thought", "Cos o czyms, brak kontekstu, niska pewnosc klasyfikacji."),
]


def _slugify(title: str) -> str:
    s = title.lower().replace(" ", "-").replace(",", "")
    for pl, ascii_ in [("ó", "o"), ("ś", "s"), ("ł", "l"), ("ą", "a"),
                       ("ę", "e"), ("ż", "z"), ("ć", "c"), ("ń", "n"), ("ź", "z")]:
        s = s.replace(pl, ascii_)
    return s[:60]


def build_vault(vault_path: Path) -> None:
    vault_path.mkdir(parents=True, exist_ok=True)
    (vault_path / "_Reports").mkdir(exist_ok=True)
    (vault_path / "_Sensitive-flagged").mkdir(exist_ok=True)
    for idx, (folder, title, body) in enumerate(NOTES):
        folder_dir = vault_path / folder
        folder_dir.mkdir(exist_ok=True)
        slug = _slugify(title)
        f = folder_dir / f"2026-04-17-{slug}.md"
        f.write_text(TEMPLATE.format(idx=idx, title=title, folder=folder, body=body))


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: build_vault_fixture.py <dest>")
        sys.exit(1)
    build_vault(Path(sys.argv[1]))
    print(f"Vault fixture created at {sys.argv[1]}")
