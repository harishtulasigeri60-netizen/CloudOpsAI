import re
import unittest
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]

class FrontendIntegrityTests(unittest.TestCase):
    def test_all_templates_parse(self):
        env = Environment(loader=FileSystemLoader(ROOT / 'templates'), undefined=StrictUndefined)
        templates = sorted((ROOT / 'templates').glob('*.html'))
        self.assertGreaterEqual(len(templates), 1)
        for template in templates:
            env.get_template(template.name)

    def test_no_external_runtime_dependencies(self):
        text = '\n'.join(p.read_text(encoding='utf-8') for p in (ROOT / 'templates').glob('*.html'))
        text += (ROOT / 'static' / 'js' / 'dashboard.js').read_text(encoding='utf-8')
        self.assertNotRegex(text, r'cdn\.jsdelivr\.net|unpkg\.com|fonts\.googleapis\.com|fonts\.gstatic\.com')
        self.assertNotRegex(text, r'\bonclick\s*=|\bonload\s*=|\bonerror\s*=|\bonchange\s*=')

    def test_aws_only_wording(self):
        text = '\n'.join(p.read_text(encoding='utf-8').lower() for p in ROOT.rglob('*') if p.is_file() and p.parent.name != 'tests' and p.suffix in {'.py','.html','.md','.example'})
        self.assertNotRegex(text, r'azure|gcp|google cloud|multi-cloud')
        self.assertNotIn('cloudopsaI_demo_mode'.lower(), text)

if __name__ == '__main__':
    unittest.main()
