"""Config + XDG paths. `~/.config/tilawah/config.toml` (tomllib read, manual write)."""

import os
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 fallback (kept tiny, stdlib only)
    tomllib = None

APP = "tilawah"

DEFAULTS = {
    "default_reciter": "Mishary Alafasi",
    "default_moshaf": 0,
    "theme": "night",
    "download_dir": "~/Tilawah",
    "youtube_playlist_url": "",
    "offline": False,
    "sleep_timer_minutes": 30,
    "volume": 80,
    "reduced_motion": False,
    "fps": 12,
    "show_all_reciters": False,
    "anim": "orbit",
    "play_mode": "download",
}


def _xdg(var, default):
    return Path(os.environ.get(var, str(Path.home() / default))).expanduser()


def config_dir():
    return _xdg("XDG_CONFIG_HOME", ".config") / APP


def data_dir():
    return _xdg("XDG_DATA_HOME", ".local/share") / APP


def cache_dir():
    return _xdg("XDG_CACHE_HOME", ".cache") / APP


def config_path():
    return config_dir() / "config.toml"


def db_path():
    return data_dir() / "tilawah.db"


def ensure_dirs():
    for d in (config_dir(), data_dir(), cache_dir(),
              Path(load().get("download_dir", "~/Tilawah")).expanduser()):
        d.mkdir(parents=True, exist_ok=True)


def _parse_toml(text):
    if tomllib is not None:
        return tomllib.loads(text)
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1]
            elif v.lower() in ("true", "false"):
                v = v.lower() == "true"
            else:
                try:
                    v = int(v)
                except ValueError:
                    pass
            out[k] = v
    return out


def load():
    cfg = dict(DEFAULTS)
    p = config_path()
    if p.exists():
        try:
            cfg.update(_parse_toml(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def save(cfg):
    config_dir().mkdir(parents=True, exist_ok=True)
    lines = ["# Tilawah configuration — edit freely, reloaded on each launch.\n"]
    for k in DEFAULTS:
        v = cfg.get(k, DEFAULTS[k])
        if isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, int):
            lines.append(f"{k} = {v}")
        else:
            lines.append(f'{k} = "{v}"')
    lines.append("")
    config_path().write_text("\n".join(lines), encoding="utf-8")


def expand_download_dir(cfg):
    return Path(str(cfg.get("download_dir", "~/Tilawah"))).expanduser()
