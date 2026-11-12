"""Credential startup contracts; synthetic secrets, no network or models."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import evals_web


class OrqCredentialTest(unittest.TestCase):
    def start_eval(self, environment, extra=()):
        server = MagicMock(); server.server_port = 12345
        with patch.dict(os.environ, environment, clear=True), \
                patch('sys.argv', ['evals_web.py', '--port', '0', *extra]), \
                patch.object(evals_web, 'handler_class', return_value=object()) as handler, \
                patch.object(evals_web, 'ThreadingHTTPServer', return_value=server), \
                patch.object(evals_web.getpass, 'getpass', side_effect=AssertionError('Do not prompt when a configured file supplies the key.')), \
                contextlib.redirect_stdout(io.StringIO()):
            evals_web.main()
            return handler.call_args.args[0]

    def test_eval_uses_the_same_private_key_file_as_mike_without_prompting(self):
        with tempfile.TemporaryDirectory() as temporary:
            key_file = Path(temporary) / 'private-key'; key_file.write_text('synthetic-file-key\n')
            config = self.start_eval({'ORQ_API_KEY_FILE': str(key_file)})
            self.assertEqual(config['key'], 'synthetic-file-key')
            config = self.start_eval({'ORQ_API_KEY_FILE': str(key_file)}, ['--ask-key'])
            self.assertEqual(config['key'], 'synthetic-file-key')

    def test_environment_precedes_file_and_keyless_local_mode_remains_available(self):
        config = self.start_eval({'ORQ_API_KEY': ' synthetic-env-key ', 'ORQ_API_KEY_FILE': '/missing/file'})
        self.assertEqual(config['key'], 'synthetic-env-key')
        self.assertEqual(self.start_eval({})['key'], '')

    def test_invalid_explicit_key_file_fails_without_leaking_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            for content in (b'', b'\xffprivate-bytes'):
                key_file = Path(temporary) / 'private-key'; key_file.write_bytes(content)
                errors = io.StringIO()
                with contextlib.redirect_stderr(errors), self.assertRaises(SystemExit):
                    self.start_eval({'ORQ_API_KEY_FILE': str(key_file)})
                self.assertNotIn('private-bytes', errors.getvalue())
