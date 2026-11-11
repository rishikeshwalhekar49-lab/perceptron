"""Hyperplane Heist: the save file.

Settings, campaign stars, endless and daily records, the leaderboard,
Academy progress, achievements, XP / ranks and laser skins live in one JSON
file, by default ~/.hyperplane_heist/save.json (override with the
HYPERPLANE_HEIST_SAVE environment variable).  Writes are atomic; a corrupt
file is set aside as .bak and the game starts fresh.
"""
import copy
import datetime
import json
import os
import tempfile

SAVE_ENV = "HYPERPLANE_HEIST_SAVE"
VERSION = 1
CAMPAIGN_SIZE = 12
LESSON_IDS = ("neuron", "sum", "boundary", "gates", "learning", "convergence", "rate", "beyond")
LEADERBOARD_SIZE = 10
DAILY_EPOCH = datetime.date(2026, 1, 1)

RANKS = ((0, "Rookie"), (300, "Lookout"), (900, "Safecracker"), (2000, "Infiltrator"), (4000, "Phantom"),
         (7000, "Mastermind"), (12000, "Legend"))

ACHIEVEMENTS = (
    # id, title, description, xp
    ("first_crack", "First Crack", "Crack your first vault.", 50),
    ("ghost", "Ghost", "Clear a campaign vault without tripping an alarm.", 75),
    ("stars_15", "Rising Star", "Earn 15 campaign stars.", 100),
    ("campaign", "Mastermind", "Clear all 12 campaign vaults.", 250),
    ("stars_all", "Constellation", "Earn all 36 campaign stars.", 400),
    ("and_gate", "Logic Bomb", "Build an AND gate out of a single perceptron.", 75),
    ("minsky", "Minsky Was Right", "Prove the XOR vault impossible.", 150),
    ("wave5", "Sector Cleared", "Reach wave 5 in Endless.", 75),
    ("wave10", "Deep Infiltration", "Reach wave 10 in Endless.", 150),
    ("wave20", "Legend of the Vault", "Reach wave 20 in Endless.", 300),
    ("combo20", "Combo Artist", "Classify 20 units in a row without a mistake.", 75),
    ("combo50", "Unstoppable", "Classify 50 units in a row without a mistake.", 200),
    ("score10k", "Big Score", "Score 10,000 in one Endless run.", 100),
    ("score50k", "The Big One", "Score 50,000 in one Endless run.", 300),
    ("proof", "Q.E.D.", "Prove a boss vault is not linearly separable.", 100),
    ("trainer", "Let the Machine Learn", "Use the Auto-Trainer.", 40),
    ("wide", "Wide Berth", "Crack a vault with a margin of 2.0 or more.", 60),
    ("close", "Close Shave", "Get a unit right that sits within 0.05 of the laser.", 60),
    ("daily", "Creature of Habit", "Finish a Daily Heist.", 100),
    ("first_lesson", "Student", "Finish your first Academy lesson.", 40),
    ("scholar", "Scholar", "Finish every Academy lesson.", 200),
    ("quiz10", "Certified Hyperplane Hacker", "Score 10 / 10 on the Academy quiz.", 200),
)
ACHIEVEMENT_INFO = {a[0]: a for a in ACHIEVEMENTS}

SKIN_ORDER = ("cyan", "emerald", "ruby", "violet", "gold", "prism")
SKIN_RULES = {
    "cyan": "Always yours",
    "emerald": "Reach the rank of Lookout",
    "ruby": "Reach the rank of Safecracker",
    "violet": "Finish every Academy lesson",
    "gold": "Clear all 12 campaign vaults",
    "prism": "Reach Legend, or 25,000 in Endless",
}

DEFAULT_SETTINGS = {"music": 0.5, "sfx": 0.7, "muted": False, "shake": True, "flashes": True,
                    "fullscreen": False, "skin": "cyan"}


def default_path():
    override = os.environ.get(SAVE_ENV)
    if override is not None:
        return override or None             # an empty value means "do not save"
    return os.path.join(os.path.expanduser("~"), ".hyperplane_heist", "save.json")


def today():
    return datetime.date.today()


def daily_key(date=None):
    return (date or today()).isoformat()


def daily_number(date=None):
    return ((date or today()) - DAILY_EPOCH).days + 1


def daily_seed(date=None):
    return int((date or today()).strftime("%Y%m%d"))


def rank_index(xp):
    index = 0
    for i, (threshold, _) in enumerate(RANKS):
        if xp >= threshold:
            index = i
    return index


class Profile:
    def __init__(self, path="default", autosave=True):
        self.path = default_path() if path == "default" else path
        self.autosave = autosave
        self.events = []            # (kind, title, detail) waiting to be shown as toasts
        self.save_error = None
        self.data = self._load()
        self._skins_known = set(self.unlocked_skins())

    # ---------------------------------------------------------------- storage
    @staticmethod
    def _defaults():
        return {
            "version": VERSION,
            "xp": 0,
            "settings": dict(DEFAULT_SETTINGS),
            "campaign": {},
            "endless": {"best": 0, "best_wave": 0, "runs": 0, "scores": []},
            "daily": {},
            "lessons": [],
            "quiz_best": 0,
            "achievements": [],
            "stats": {},
            "last_name": "ACE",
        }

    def _load(self):
        data = self._defaults()
        if not self.path or not os.path.exists(self.path):
            return data
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            if not isinstance(stored, dict):
                raise ValueError("save file is not an object")
        except (OSError, ValueError):
            try:
                os.replace(self.path, self.path + ".bak")
            except OSError:
                pass
            return data
        for key, value in stored.items():
            if key in data and isinstance(data[key], dict) and isinstance(value, dict):
                merged = copy.deepcopy(data[key])
                merged.update(value)
                data[key] = merged
            elif key in data and type(value) is type(data[key]):
                data[key] = value
        return data

    def save(self):
        if not self.path:
            return
        try:
            folder = os.path.dirname(self.path) or "."
            os.makedirs(folder, exist_ok=True)
            fd, temp = tempfile.mkstemp(prefix=".save-", suffix=".json", dir=folder)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, indent=1, sort_keys=True)
            os.replace(temp, self.path)
            self.save_error = None
        except OSError as error:
            self.save_error = str(error)

    def _changed(self):
        self._check_skins()
        if self.autosave:
            self.save()

    def pop_events(self):
        events, self.events = self.events, []
        return events

    # --------------------------------------------------------------- settings
    @property
    def settings(self):
        return self.data["settings"]

    def set_setting(self, key, value):
        self.settings[key] = value
        if self.autosave:
            self.save()

    # -------------------------------------------------------------- xp, ranks
    @property
    def xp(self):
        return self.data["xp"]

    @property
    def rank(self):
        return RANKS[rank_index(self.xp)][1]

    def rank_progress(self):
        """(rank name, xp into this rank, xp needed for the next one or None)."""
        i = rank_index(self.xp)
        base = RANKS[i][0]
        if i + 1 < len(RANKS):
            return RANKS[i][1], self.xp - base, RANKS[i + 1][0] - base
        return RANKS[i][1], self.xp - base, None

    def add_xp(self, amount):
        amount = int(amount)
        if amount <= 0:
            return
        before = rank_index(self.xp)
        self.data["xp"] += amount
        after = rank_index(self.xp)
        if after > before:
            self.events.append(("rank", "RANK UP: " + RANKS[after][1].upper(), "{} XP".format(self.xp)))
        self._changed()

    # ----------------------------------------------------------- achievements
    def has(self, aid):
        return aid in self.data["achievements"]

    def unlock(self, aid):
        if aid not in ACHIEVEMENT_INFO or self.has(aid):
            return False
        self.data["achievements"].append(aid)
        _, title, description, xp = ACHIEVEMENT_INFO[aid]
        self.events.append(("achievement", title, description))
        self.add_xp(xp)
        return True

    # --------------------------------------------------------------- campaign
    def level_record(self, key):
        return self.data["campaign"].get(key, {})

    def stars(self, key):
        return int(self.level_record(key).get("stars", 0))

    def total_stars(self):
        return sum(int(r.get("stars", 0)) for r in self.data["campaign"].values())

    def campaign_cleared(self):
        return sum(1 for r in self.data["campaign"].values() if r.get("stars", 0) > 0)

    def level_unlocked(self, index, keys):
        return index == 0 or self.stars(keys[index - 1]) > 0

    def record_level(self, key, stars, seconds, margin):
        """Store a cleared vault.  Returns (stars gained over the old best, first clear?)."""
        record = dict(self.level_record(key))
        old = int(record.get("stars", 0))
        record["stars"] = max(old, stars)
        if seconds is not None:
            record["best_time"] = min(record.get("best_time", seconds), seconds)
        if margin is not None:
            record["best_margin"] = max(record.get("best_margin", margin), margin)
        record["clears"] = record.get("clears", 0) + 1
        self.data["campaign"][key] = record
        self._changed()
        return max(0, stars - old), old == 0

    # ---------------------------------------------------------------- endless
    @property
    def endless_best(self):
        return self.data["endless"]["best"]

    @property
    def endless_best_wave(self):
        return self.data["endless"]["best_wave"]

    def leaderboard(self):
        return list(self.data["endless"]["scores"])

    def qualifies(self, score):
        scores = self.data["endless"]["scores"]
        return score > 0 and (len(scores) < LEADERBOARD_SIZE or score > scores[-1]["score"])

    def add_score(self, name, score, wave, daily=False):
        """Insert into the top 10; returns the 0-based position or None."""
        if not self.qualifies(score):
            return None
        name = (name or "???").upper()[:3]
        self.data["last_name"] = name
        entry = {"name": name, "score": int(score), "wave": int(wave), "date": daily_key(), "daily": bool(daily)}
        scores = self.data["endless"]["scores"]
        position = len(scores)
        for i, other in enumerate(scores):
            if score > other["score"]:
                position = i
                break
        scores.insert(position, entry)
        del scores[LEADERBOARD_SIZE:]
        self._changed()
        return position

    def record_run(self, score, wave):
        endless = self.data["endless"]
        endless["runs"] += 1
        new_best = score > endless["best"]
        endless["best"] = max(endless["best"], int(score))
        endless["best_wave"] = max(endless["best_wave"], int(wave))
        self._changed()
        return new_best

    # ------------------------------------------------------------------ daily
    def daily_record(self, key=None):
        return self.data["daily"].get(key or daily_key())

    def record_daily(self, key, score, waves, finished):
        old = self.data["daily"].get(key)
        better = old is None or score > old.get("score", 0)
        if better:
            self.data["daily"][key] = {"score": int(score), "waves": int(waves), "finished": bool(finished)}
        elif finished and not old.get("finished"):
            old["finished"] = True
        self._changed()
        return better

    # ---------------------------------------------------------------- academy
    @property
    def lessons(self):
        return set(self.data["lessons"])

    def complete_lesson(self, lesson_id):
        if lesson_id in self.data["lessons"]:
            return False
        self.data["lessons"].append(lesson_id)
        self.add_xp(80)
        self.unlock("first_lesson")
        if all(lid in self.data["lessons"] for lid in LESSON_IDS):
            self.unlock("scholar")
        self._changed()
        return True

    def record_quiz(self, correct, total):
        better = correct > self.data["quiz_best"]
        self.data["quiz_best"] = max(self.data["quiz_best"], int(correct))
        self.add_xp(10 * correct)
        if total >= 10 and correct >= total:
            self.unlock("quiz10")
        self._changed()
        return better

    # ------------------------------------------------------------------ skins
    def skin_unlocked(self, name):
        if name == "cyan":
            return True
        if name == "emerald":
            return self.xp >= RANKS[1][0]
        if name == "ruby":
            return self.xp >= RANKS[2][0]
        if name == "violet":
            return all(lid in self.data["lessons"] for lid in LESSON_IDS)
        if name == "gold":
            return self.campaign_cleared() >= CAMPAIGN_SIZE
        if name == "prism":
            return self.xp >= RANKS[-1][0] or self.endless_best >= 25000
        return False

    def unlocked_skins(self):
        return [name for name in SKIN_ORDER if self.skin_unlocked(name)]

    def _check_skins(self):
        for name in self.unlocked_skins():
            if name not in self._skins_known:
                self._skins_known.add(name)
                self.events.append(("skin", "NEW LASER: " + name.upper(), "Equip it in Profile"))

    @property
    def skin(self):
        name = self.settings.get("skin", "cyan")
        return name if self.skin_unlocked(name) else "cyan"

    # ------------------------------------------------------------------ stats
    def bump(self, key, amount=1):
        stats = self.data["stats"]
        stats[key] = stats.get(key, 0) + amount

    def stat(self, key):
        return self.data["stats"].get(key, 0)
