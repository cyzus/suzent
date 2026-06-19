from suzent.tools.shell.permissions.command_classifier import classify_command
from suzent.tools.shell.permissions.command_parser import parse_command
from suzent.tools.shell.permissions.policy_models import CommandClass


def _classify(command: str) -> CommandClass:
    return classify_command(parse_command(command))


def test_plain_read_only_commands():
    assert _classify("ls -la") == CommandClass.READ_ONLY
    assert _classify("cat file.txt") == CommandClass.READ_ONLY
    assert _classify("grep -r foo src") == CommandClass.READ_ONLY


def test_safe_creation_commands_are_write_limited():
    assert _classify("mkdir build") == CommandClass.WRITE_LIMITED
    assert _classify("touch new.txt") == CommandClass.WRITE_LIMITED
    assert _classify("cp a.txt b.txt") == CommandClass.WRITE_LIMITED


def test_destructive_commands_are_not_trusted_on_name():
    # rm / rmdir / mv must fall through to the classifier (UNKNOWN -> ASK),
    # not be auto-allowed as write-limited.
    assert _classify("rm -rf build") == CommandClass.UNKNOWN
    assert _classify("rmdir build") == CommandClass.UNKNOWN
    assert _classify("mv a.txt b.txt") == CommandClass.UNKNOWN


def test_find_read_only_vs_mutating():
    assert _classify("find . -name '*.py'") == CommandClass.READ_ONLY
    assert _classify("find . -type f") == CommandClass.READ_ONLY
    # -delete / -exec make find mutating or code-executing.
    assert _classify("find . -name '*.tmp' -delete") == CommandClass.UNKNOWN
    assert _classify("find . -exec rm {} ;") == CommandClass.UNKNOWN
    assert _classify("find . -execdir cat {} +") == CommandClass.UNKNOWN


def test_sed_read_only_vs_editing():
    assert _classify("sed -n '1,5p' file.txt") == CommandClass.READ_ONLY
    # -e/--expression is the ordinary way to pass a script: still read-only.
    assert _classify("sed -e 's/a/b/' file.txt") == CommandClass.READ_ONLY
    assert _classify("sed -n -e 'p' file.txt") == CommandClass.READ_ONLY
    # In-place edit rewrites files.
    assert _classify("sed -i 's/a/b/' file.txt") == CommandClass.UNKNOWN
    assert _classify("sed -i.bak 's/a/b/' file.txt") == CommandClass.UNKNOWN
    assert _classify("sed --in-place 's/a/b/' file.txt") == CommandClass.UNKNOWN
    # The `e` command executes a shell.
    assert _classify("sed 's/a/b/e' file.txt") == CommandClass.UNKNOWN
    assert _classify("sed -e 's/x/y/e' file.txt") == CommandClass.UNKNOWN


def test_dangerous_commands_stay_dangerous():
    assert _classify("sudo rm -rf /") == CommandClass.DANGEROUS
    assert _classify("chmod 777 file") == CommandClass.DANGEROUS


def test_git_is_unknown():
    assert _classify("git status") == CommandClass.UNKNOWN
