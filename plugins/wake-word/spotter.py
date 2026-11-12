"""Wake-word spotting, entirely on this machine.

The desktop app streams 16 kHz microphone audio to
``/plugins/wake-word/ws/listen`` while the wake word is on; a small sherpa-onnx
keyword spotter listens for the phrases in the voice settings and tells the app
when it hears one. Nothing reaches a model provider until the app then starts
an ordinary voice call.

The packages (sherpa-onnx, pypinyin) come with this plugin's ``wake`` extra. The
model (about 9 MB of the 33 MB release) is downloaded on first use and each
file is checked against the hash pinned here, whichever source served it.
"""

from __future__ import annotations

import hashlib
import io
import re
import shutil
import tarfile
import threading
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from suzent.logger import get_logger

logger = get_logger(__name__)

SAMPLE_RATE = 16000
MODEL_NAME = "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20"
# Only the files the spotter loads, each pinned (checked 2026-11-07 against
# the k2-fsa release tarball, sha256 68447f4f...16a6).
MODEL_FILES = {
    "encoder.onnx": (
        "encoder-epoch-13-avg-2-chunk-16-left-64.int8.onnx",
        "408bbd740838c42d5bf6d1c5b80b3c88b616c7860b92d980328b5b068c76ae48",
    ),
    "decoder.onnx": (
        "decoder-epoch-13-avg-2-chunk-16-left-64.onnx",
        "63a22dd60f40fff082ac3e09afa507f6787da36df76ded2fbe145fa233e22c21",
    ),
    "joiner.onnx": (
        "joiner-epoch-13-avg-2-chunk-16-left-64.int8.onnx",
        "190d4067b4cc20b72a42a1916e69d92052000fb7051a427ebb1bc72a69207dc1",
    ),
    "tokens.txt": (
        "tokens.txt",
        "2d3f32311f9b692b964da3c90e830258d3e78e013cb0c992dbfb15cd5a1a71b0",
    ),
    "en.phone": (
        "en.phone",
        "f7000ec3a90544c0c7c16090d8951779c2b322e14dad5006290f498567d439ea",
    ),
}
MODEL_TARBALL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/"
    f"{MODEL_NAME}.tar.bz2"
)
# Per-file mirrors, tried when GitHub is out of reach (mainland China).
MODEL_FILE_MIRRORS = (
    f"https://hf-mirror.com/csukuangfj/{MODEL_NAME}/resolve/main",
    f"https://huggingface.co/csukuangfj/{MODEL_NAME}/resolve/main",
)
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024

# Words the CMU lexicon cannot know. "Suzent" has no settled pronunciation,
# so both stresses people use are accepted.
EXTRA_LEXICON: dict[str, list[list[str]]] = {
    "SUZENT": [["S", "UW1", "Z", "EH1", "N", "T"], ["S", "UW0", "Z", "EH1", "N", "T"]],
}

_CJK = re.compile(r"[一-鿿]+")
_WORD = re.compile(r"[一-鿿]+|[A-Za-z']+")


class WakeUnavailable(Exception):
    """The wake word cannot run here; ``code`` says why."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


def model_dir() -> Path:
    from suzent.config.paths import DATA_DIR

    return DATA_DIR / "models" / "wake" / MODEL_NAME


def packages_installed() -> bool:
    try:
        import pypinyin  # noqa: F401
        import sherpa_onnx  # noqa: F401
    except ImportError:
        return False
    return True


def model_installed(directory: Path | None = None) -> bool:
    directory = directory or model_dir()
    return all((directory / name).is_file() for name in MODEL_FILES)


def status(phrases: Iterable[str] = ()) -> dict[str, Any]:
    """What is installed, and which words of ``phrases`` cannot be spotted."""
    result: dict[str, Any] = {
        "packages": packages_installed(),
        "model": model_installed(),
        "unknown_words": [],
    }
    if result["packages"] and result["model"]:
        directory = model_dir()
        try:
            keyword_lines(
                phrases, _load_lexicon(directory / "en.phone"), _vocabulary(directory)
            )
        except WakeUnavailable as exc:
            result["unknown_words"] = str(exc).split(", ")
    return result


def _vocabulary(directory: Path) -> set[str]:
    return {
        line.split()[0]
        for line in (directory / "tokens.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


# --- model download ---------------------------------------------------------


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "suzent"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise ValueError(f"{url} is larger than {MAX_DOWNLOAD_BYTES} bytes")
    return data


def _files_from_tarball(payload: bytes) -> dict[str, bytes]:
    wanted = {
        f"{MODEL_NAME}/{member}": name for name, (member, _) in MODEL_FILES.items()
    }
    found: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as archive:
        for info in archive:
            name = wanted.get(info.name)
            if name and info.isfile():
                handle = archive.extractfile(info)
                if handle is not None:
                    found[name] = handle.read()
    return found


def _verified(files: dict[str, bytes], source: str) -> dict[str, bytes]:
    for name, (_, digest) in MODEL_FILES.items():
        data = files.get(name)
        if data is None:
            raise ValueError(f"{source} has no {MODEL_FILES[name][0]}")
        if _sha256(data) != digest:
            raise ValueError(
                f"checksum mismatch for {MODEL_FILES[name][0]} from {source}"
            )
    return files


_install_lock = threading.Lock()


def install_model(fetch: Callable[[str], bytes] = _fetch) -> Path:
    """Download the model unless it is already here; returns its directory."""
    target = model_dir()
    with _install_lock:
        if model_installed(target):
            return target
        failures: list[str] = []
        files: dict[str, bytes] | None = None
        try:
            files = _verified(_files_from_tarball(fetch(MODEL_TARBALL)), MODEL_TARBALL)
        except Exception as exc:  # noqa: BLE001 - every failure means "try a mirror"
            logger.warning("Wake-word model download from GitHub failed: {}", exc)
            failures.append(f"{MODEL_TARBALL}: {exc}")
        for base in () if files else MODEL_FILE_MIRRORS:
            try:
                files = _verified(
                    {
                        name: fetch(f"{base}/{member}")
                        for name, (member, _) in MODEL_FILES.items()
                    },
                    base,
                )
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("Wake-word model download from {} failed: {}", base, exc)
                failures.append(f"{base}: {exc}")
        if files is None:
            raise WakeUnavailable("download_failed", "; ".join(failures))
        staging = target.with_name(target.name + ".partial")
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        for name, data in files.items():
            (staging / name).write_bytes(data)
        shutil.rmtree(target, ignore_errors=True)
        staging.rename(target)
        return target


# --- keywords ---------------------------------------------------------------


def _load_lexicon(path: Path) -> dict[str, list[str]]:
    lexicon: dict[str, list[str]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            word, *phones = line.split()
            if phones:
                lexicon.setdefault(word.upper(), phones)
    return lexicon


def _pinyin_tokens(text: str) -> list[str]:
    """Initials and toned finals, as the zh-en model spells Chinese."""
    from pypinyin import pinyin
    from pypinyin.contrib.tone_convert import to_finals_tone, to_initials

    tokens: list[str] = []
    for (syllable,) in pinyin(text):
        initial = to_initials(syllable, strict=False)
        final = to_finals_tone(syllable, strict=False)
        parts = [part for part in (initial, final) if part]
        tokens.extend(parts or [syllable])
    return tokens


def keyword_lines(
    phrases: Iterable[str], lexicon: dict[str, list[str]], vocabulary: set[str]
) -> list[str]:
    """The spotter's keywords file: one line per pronunciation, tagged by phrase.

    Raises ``WakeUnavailable("unknown_words")`` naming any English word with no
    known pronunciation, so the settings page can say which one to change.
    """
    lines: list[str] = []
    unknown: list[str] = []
    for phrase in phrases:
        phrase = " ".join(phrase.split())
        if not phrase:
            continue
        variants: list[list[str]] = [[]]
        for word in _WORD.findall(phrase):
            if _CJK.fullmatch(word):
                options = [_pinyin_tokens(word)]
            else:
                key = word.upper()
                options = EXTRA_LEXICON.get(key) or (
                    [lexicon[key]] if key in lexicon else []
                )
                if not options:
                    unknown.append(word)
                    continue
            variants = [head + option for head in variants for option in options]
        tag = phrase.replace(" ", "_")
        for tokens in variants:
            if tokens and all(token in vocabulary for token in tokens):
                lines.append(f"{' '.join(tokens)} @{tag}")
    if unknown:
        raise WakeUnavailable("unknown_words", ", ".join(dict.fromkeys(unknown)))
    return lines


def threshold_for(sensitivity: float) -> float:
    """Map the 0..1 sensitivity slider onto sherpa-onnx's trigger threshold.

    0.5 gives the model's recommended 0.25; higher sensitivity wakes more
    readily (and more often by mistake).
    """
    sensitivity = min(1.0, max(0.0, sensitivity))
    return round(0.45 - 0.4 * sensitivity, 3)


# --- spotter ----------------------------------------------------------------


@dataclass(frozen=True)
class SpotterConfig:
    phrases: tuple[str, ...]
    sensitivity: float


class WakeSpotter:
    """One listener: feed 16 kHz int16 PCM, get the phrase it heard (if any)."""

    def __init__(self, config: SpotterConfig, directory: Path | None = None) -> None:
        if not packages_installed():
            raise WakeUnavailable("not_installed")
        directory = directory or model_dir()
        if not model_installed(directory):
            raise WakeUnavailable("no_model")
        import sherpa_onnx

        lines = keyword_lines(
            config.phrases,
            _load_lexicon(directory / "en.phone"),
            _vocabulary(directory),
        )
        if not lines:
            raise WakeUnavailable("no_keywords")
        keywords = (
            directory / f"keywords-{_sha256(chr(10).join(lines).encode())[:16]}.txt"
        )
        if not keywords.exists():
            keywords.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._spotter = sherpa_onnx.KeywordSpotter(
            tokens=str(directory / "tokens.txt"),
            encoder=str(directory / "encoder.onnx"),
            decoder=str(directory / "decoder.onnx"),
            joiner=str(directory / "joiner.onnx"),
            keywords_file=str(keywords),
            keywords_threshold=threshold_for(config.sensitivity),
            keywords_score=1.0,
            num_threads=1,
            provider="cpu",
        )
        self._stream = self._spotter.create_stream()

    def accept(self, pcm: bytes) -> str | None:
        import numpy as np

        samples = np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype="<i2")
        self._stream.accept_waveform(SAMPLE_RATE, samples.astype(np.float32) / 32768.0)
        heard: str | None = None
        while self._spotter.is_ready(self._stream):
            self._spotter.decode_stream(self._stream)
            keyword = self._spotter.get_result(self._stream)
            if keyword:
                heard = keyword.replace("_", " ")
                self._spotter.reset_stream(self._stream)
        return heard
