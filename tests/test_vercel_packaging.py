"""Offline checks for the Vercel function packaging contract."""
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_PATTERN_LENGTH = 256
# Independent packaging contract: enumerate individual required files; only
# resource families (templates, fonts and illustrations) use directory globs.
REQUIRED_FILES = {
    'templates/index.html', 'templates/404.html',
    'public/styles.css', 'public/fonts.css', 'public/polish.css',
    'public/app.js', 'public/error-page.js', 'public/social-ui.js',
    'public/santa-ui.js', 'public/password-strength-worker.js',
    'public/zxcvbn-4.4.2.js', 'public/favicon.svg', 'public/favicon.ico',
    'public/pwa.js', 'public/manifest.webmanifest', 'public/service-worker.js',
    'public/pwa-180.png', 'public/pwa-192.png', 'public/pwa-512.png',
}
RESOURCE_FAMILIES = ('templates/*.html', 'public/fonts/*.woff2',
                     'public/art/crayon/*.webp')


def expand_braces(pattern):
    """Expand the nested comma-separated braces used by vercel.json."""
    match = re.search(r'\{([^{}]+)\}', pattern)
    if match is None:
        if '{' in pattern or '}' in pattern:
            raise ValueError(f'Unbalanced braces: {pattern}')
        yield pattern
        return
    for part in match.group(1).split(','):
        yield from expand_braces(pattern[:match.start()] + part + pattern[match.end():])


def matching_files(pattern):
    return {path.relative_to(ROOT).as_posix()
            for glob in expand_braces(pattern)
            for path in ROOT.glob(glob) if path.is_file()}


class VercelPackagingTest(unittest.TestCase):
    def setUp(self):
        config = json.loads((ROOT / 'vercel.json').read_text(encoding='utf-8'))
        self.function = config['functions']['app.py']

    def test_function_patterns_fit_vercel_limit(self):
        for key in ('includeFiles', 'excludeFiles'):
            with self.subTest(key=key):
                value = self.function[key]
                self.assertIsInstance(value, str)
                self.assertLessEqual(len(value), MAX_PATTERN_LENGTH,
                                     f'{key}: {len(value)} > {MAX_PATTERN_LENGTH}')

    def test_exact_required_resource_inventory(self):
        for path in REQUIRED_FILES:
            self.assertTrue((ROOT / path).is_file(), f'Missing required file: {path}')
        expected = set(REQUIRED_FILES)
        for family in RESOURCE_FAMILIES:
            matches = matching_files(family)
            self.assertTrue(matches, f'Empty resource family: {family}')
            expected.update(matches)
        included = matching_files(self.function['includeFiles'])
        self.assertSetEqual(included, expected)
        excluded = matching_files(self.function['excludeFiles'])
        self.assertFalse(included & excluded,
                         f'Required resources excluded: {sorted(included & excluded)}')

    def test_preview_resources_stay_excluded(self):
        included = matching_files(self.function['includeFiles'])
        excluded = matching_files(self.function['excludeFiles'])
        preview = {'public/shursh-preview.html', 'public/preview-store.js'}
        self.assertTrue(preview <= excluded)
        self.assertFalse(preview & included)

    def test_nested_brace_expansion(self):
        self.assertEqual(list(expand_braces('{a/{b,c},d}')), ['a/b', 'd', 'a/c', 'd'])


if __name__ == '__main__':
    unittest.main()
