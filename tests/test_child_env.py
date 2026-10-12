import unittest

from utils.child_env import restore_library_path


class RestoreLibraryPathTest(unittest.TestCase):
    def test_original_value_is_restored(self):
        env = {"LD_LIBRARY_PATH": "/opt/overlingo/_internal", "LD_LIBRARY_PATH_ORIG": "/usr/local/lib"}
        restore_library_path(env, frozen=True, platform="linux")
        self.assertEqual(env["LD_LIBRARY_PATH"], "/usr/local/lib")

    def test_removed_when_the_user_had_none(self):
        env = {"LD_LIBRARY_PATH": "/opt/overlingo/_internal"}
        restore_library_path(env, frozen=True, platform="linux")
        self.assertNotIn("LD_LIBRARY_PATH", env)

    def test_untouched_when_running_from_source(self):
        env = {"LD_LIBRARY_PATH": "/custom"}
        restore_library_path(env, frozen=False, platform="linux")
        self.assertEqual(env, {"LD_LIBRARY_PATH": "/custom"})

    def test_untouched_on_windows_and_macos(self):
        for platform in ("win32", "darwin"):
            env = {"LD_LIBRARY_PATH": "/x"}
            restore_library_path(env, frozen=True, platform=platform)
            self.assertEqual(env, {"LD_LIBRARY_PATH": "/x"})


if __name__ == "__main__":
    unittest.main()
