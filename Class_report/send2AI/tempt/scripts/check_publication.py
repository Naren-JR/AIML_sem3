"""Scan publishable Git candidates; never print matched credential values."""
from pathlib import Path
import re
import subprocess
from backend.data import ROOT

PATTERNS = {
    'private_key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'github_token': r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b',
    'aws_access_key': r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'api_key': r'\bsk-(?:proj-)?[A-Za-z0-9_-]{35,}\b',
    'personal_path': r'(?i)(?:[A-Z]:[/\\](?:Users|codes)[/\\]|/Users/|/home/)',
}


def main():
    output = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT)
    paths = sorted(set(p.decode('utf-8') for p in output.split(b'\0') if p))
    findings = []
    for name in paths:
        path = ROOT / name
        if not path.is_file():
            continue
        if path.name.startswith('.env') and not path.name.endswith('.example'):
            findings.append((name, 1, 'environment_file'))
        if path.suffix.lower() in {'.pem', '.key', '.pfx', '.p12'}:
            findings.append((name, 1, 'credential_file'))
        try:
            text = path.read_text(encoding='utf-8-sig')
        except UnicodeError:
            continue
        # Pattern definitions are not actual credentials or identifying paths.
        if name == 'scripts/check_publication.py':
            continue
        for kind, pattern in PATTERNS.items():
            for match in re.finditer(pattern, text):
                findings.append((name, text.count('\n', 0, match.start()) + 1, kind))
    for name, line, kind in findings:
        print(f'{name}:{line}: {kind}')
    print(f'Scanned {len(paths)} publishable files; {len(findings)} findings. Review staged content before pushing.')
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())
