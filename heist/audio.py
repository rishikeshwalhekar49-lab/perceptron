"""Hyperplane Heist: sound effects and music, synthesized at start-up.

There are no audio files: every sound is built from sine, triangle, square and
noise waves in plain Python, and the music is a small step sequencer that
plays those notes on reserved mixer channels.  Everything stays in the A minor
pentatonic scale, so no two notes clash.

If the mixer cannot start (no audio device), every method is a quiet no-op.
"""
import array
import math
import os
import random
import sys

import pygame

TABLE_SIZE = 2048
MUSIC_VOICES = ("bass", "arp", "lead", "kick", "snare", "hat")
VOICE_LEVEL = {"bass": 0.5, "arp": 0.24, "lead": 0.22, "kick": 0.55, "snare": 0.3, "hat": 0.14}

NOTE = {
    "G1": 49.0, "A1": 55.0, "C2": 65.41, "D2": 73.42, "E2": 82.41, "G2": 98.0, "A2": 110.0,
    "C3": 130.81, "D3": 146.83, "E3": 164.81, "G3": 196.0, "A3": 220.0,
    "C4": 261.63, "D4": 293.66, "E4": 329.63, "G4": 392.0, "A4": 440.0,
    "C5": 523.25, "D5": 587.33, "E5": 659.25, "G5": 783.99, "A5": 880.0,
    "C6": 1046.5, "D6": 1174.66, "E6": 1318.51,
}

SONGS = {
    "menu": {
        "bpm": 92,
        "bass": (0, 6, 8, 14),
        "arp": (0, 2, 4, 6, 8, 10, 12, 14),
        "hat": (4, 12),
        "kick": (), "snare": (),
        "bars": (
            ("A1", ("A3", "C4", "E4", "A4", "C5", "A4", "E4", "C4")),
            ("C2", ("C4", "E4", "G4", "C5", "E5", "C5", "G4", "E4")),
            ("D2", ("D4", "G4", "A4", "D5", "A4", "G4", "D4", "A3")),
            ("E2", ("E4", "G4", "A4", "E5", "D5", "A4", "G4", "E4")),
        ),
        "leads": None,
    },
    "game": {
        "bpm": 116,
        "bass": (0, 3, 6, 8, 10, 14),
        "arp": (0, 2, 4, 6, 8, 10, 12, 14),
        "hat": (2, 6, 10, 14),
        "kick": (0, 8),
        "snare": (4, 12),
        "bars": (
            ("A1", ("A3", "E4", "A4", "C5", "A4", "E4", "C4", "E4")),
            ("A1", ("A3", "E4", "A4", "D5", "C5", "A4", "E4", "C4")),
            ("C2", ("C4", "G4", "C5", "E5", "C5", "G4", "E4", "G4")),
            ("G1", ("G3", "D4", "G4", "A4", "D5", "A4", "G4", "D4")),
        ),
        "leads": (((0, "E5"), (6, "D5"), (10, "C5")), ((0, "A4"), (6, "C5"), (12, "D5")),
                  ((0, "E5"), (6, "G5"), (10, "E5")), ((0, "D5"), (8, "C5"), (12, "A4"))),
    },
    "academy": {
        "bpm": 76,
        "bass": (0, 8),
        "arp": (0, 4, 8, 12),
        "hat": (),
        "kick": (), "snare": (),
        "bars": (
            ("A1", ("A4", "E4", "C5", "E4")),
            ("D2", ("D5", "A4", "G4", "A4")),
            ("C2", ("C5", "G4", "E5", "G4")),
            ("G1", ("G4", "D5", "A4", "D5")),
        ),
        "leads": None,
    },
}


def default_output_name():
    """The name of macOS's current default output device, read from CoreAudio, or None."""
    if sys.platform != "darwin":
        return None
    try:
        import ctypes
        import ctypes.util

        class Address(ctypes.Structure):
            _fields_ = [("selector", ctypes.c_uint32), ("scope", ctypes.c_uint32), ("element", ctypes.c_uint32)]

        def fourcc(code):
            return int.from_bytes(code.encode("ascii"), "big")

        core_audio = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreAudio"))
        foundation = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
        get = core_audio.AudioObjectGetPropertyData
        get.argtypes = [ctypes.c_uint32, ctypes.POINTER(Address), ctypes.c_uint32, ctypes.c_void_p,
                        ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
        get.restype = ctypes.c_int32
        device = ctypes.c_uint32(0)
        size = ctypes.c_uint32(ctypes.sizeof(device))
        system_object = 1
        if get(system_object, ctypes.byref(Address(fourcc("dOut"), fourcc("glob"), 0)), 0, None,
               ctypes.byref(size), ctypes.byref(device)) != 0 or not device.value:
            return None
        name = ctypes.c_void_p()
        size = ctypes.c_uint32(ctypes.sizeof(name))
        if get(device.value, ctypes.byref(Address(fourcc("lnam"), fourcc("glob"), 0)), 0, None,
               ctypes.byref(size), ctypes.byref(name)) != 0 or not name.value:
            return None
        foundation.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
        foundation.CFStringGetCString.restype = ctypes.c_bool
        foundation.CFRelease.argtypes = [ctypes.c_void_p]
        text = ctypes.create_string_buffer(512)
        ok = foundation.CFStringGetCString(name, text, len(text), 0x08000100)     # kCFStringEncodingUTF8
        foundation.CFRelease(name)
        return text.value.decode("utf-8") if ok and text.value else None
    except Exception:
        return None


def open_mixer(frequency=44100, size=-16, channels=2, buffer=512):
    """Open the audio device once, before pygame.init().  Returns True if there is sound.

    On macOS the device is opened BY NAME.  SDL 2.28 (bundled with pygame 2.6.1)
    registers a "default output changed" listener only when a program opens the
    unnamed default device, and that listener can run after the device it points
    to is gone: the game then dies with a segmentation fault when the output
    switches (USB or Bluetooth audio, headphones).  A named device gets SDL's
    unplug listener instead, which is removed properly.  The cost: sound stays on
    the device that was the default when the game started.

    Set HYPERPLANE_HEIST_AUDIO=0 to run without opening any audio device.
    Never raises: the worst case is a silent game."""
    if os.environ.get("HYPERPLANE_HEIST_AUDIO", "1") == "0":
        os.environ["SDL_AUDIODRIVER"] = "dummy"         # so pygame.init() cannot open a real device either
        return False
    try:
        import pygame.mixer  # noqa: F401  (pygame in the browser does not import it on its own)
        if pygame.mixer.get_init():
            return True
        driver = os.environ.get("SDL_AUDIODRIVER", "")
        name = default_output_name() if driver in ("", "coreaudio") else None
        for devicename in ([name] if name else []) + [None]:
            try:
                pygame.mixer.init(frequency, size, channels, buffer, devicename=devicename)
                return True
            except pygame.error:
                continue
    except Exception:
        pass
    return False


class Synth:
    """Builds sample lists (floats in -1..1) at a fixed rate."""

    def __init__(self, rate, seed=7):
        self.rate = rate
        self.rng = random.Random(seed)
        self.table = [math.sin(i * math.tau / TABLE_SIZE) for i in range(TABLE_SIZE)]

    def tone(self, freq, dur, wave="sine", attack=0.004, decay=None, release=0.01, volume=1.0, freq_end=None,
             harmonics=(), vibrato=0.0, vibrato_rate=6.0):
        rate = self.rate
        n = max(2, int(dur * rate))
        out = [0.0] * n
        table = self.table
        mask = TABLE_SIZE - 1
        size = float(TABLE_SIZE)
        a_n = max(1, int(attack * rate))
        r_n = max(1, int(release * rate))
        step = math.exp(-1.0 / (decay * rate)) if decay else 1.0
        ratio = (freq_end / freq) ** (1.0 / n) if freq_end else 1.0
        phase = 0.0
        partial = [0.0] * len(harmonics)
        level = 1.0
        f = freq
        vib_k = vibrato_rate / rate * size
        for i in range(n):
            fi = f * (1.0 + vibrato * table[int(i * vib_k) & mask]) if vibrato else f
            phase += fi / rate
            p = phase - int(phase)
            if wave == "sine":
                v = table[int(p * size) & mask]
            elif wave == "tri":
                v = 4.0 * abs(p - 0.5) - 1.0
            elif wave == "square":
                v = 0.7 if p < 0.5 else -0.7
            else:
                v = 2.0 * p - 1.0
            for k in range(len(harmonics)):
                partial[k] += fi * harmonics[k][0] / rate
                q = partial[k]
                v += harmonics[k][1] * table[int((q - int(q)) * size) & mask]
            env = level
            if i < a_n:
                env *= i / a_n
            if i > n - r_n:
                env *= (n - i) / r_n
            out[i] = v * env * volume
            level *= step
            f *= ratio
        return out

    def noise(self, dur, decay=None, volume=1.0, highpass=False, crackle=False):
        rate = self.rate
        n = max(2, int(dur * rate))
        rnd = self.rng.random
        step = math.exp(-1.0 / (decay * rate)) if decay else 1.0
        level = 1.0
        prev = 0.0
        out = [0.0] * n
        for i in range(n):
            x = rnd() * 2.0 - 1.0
            if highpass:
                x, prev = x - prev, x
                x *= 0.5
            if crackle and rnd() < 0.7:
                x *= 0.12
            out[i] = x * level * volume
            level *= step
        return out

    def arrange(self, parts, length=None):
        """Mix [(start seconds, samples), ...] into one list."""
        rate = self.rate
        end = max(int(start * rate) + len(samples) for start, samples in parts)
        out = [0.0] * max(end, int((length or 0) * rate))
        for start, samples in parts:
            offset = int(start * rate)
            for i, v in enumerate(samples):
                out[offset + i] += v
        return out

    def notes(self, names, gap, dur, **kwargs):
        return self.arrange([(k * gap, self.tone(NOTE[name], dur, **kwargs)) for k, name in enumerate(names)])


class Audio:
    """Sound effects and music.  `settings` is the profile's settings dict
    (keys "music", "sfx", "muted"), read on every play so changes apply at once."""

    def __init__(self, settings, enabled=True):
        self.settings = settings
        self.ok = False
        self.sounds = {}
        self.voices = {}
        self.last = {}
        self.song = None
        self.song_name = None
        self.step = 0
        self.acc = 0.0
        self.intensity = 1
        self.bpm = 100
        self.clock = 0.0
        if not enabled:
            return
        try:
            if not open_mixer():
                return
            rate, size, channels = pygame.mixer.get_init()
            if size not in (-16, 32):
                return
            self.size = size
            self.channels = channels
            self.factor = 2 if rate >= 32000 else 1         # synthesize at half rate, then repeat samples
            self.synth = Synth(rate // self.factor)
            pygame.mixer.set_num_channels(32)
            pygame.mixer.set_reserved(len(MUSIC_VOICES))
            self.music_channels = {name: pygame.mixer.Channel(i) for i, name in enumerate(MUSIC_VOICES)}
            self._build_sfx()
            self._build_music()
            self.ok = True
        except Exception:
            self.ok = False

    # ------------------------------------------------------------- building
    def _to_sound(self, samples, gain=0.9):
        if self.size == 32:
            values = array.array("f", [max(-1.0, min(1.0, v)) * gain for v in samples])
        else:
            peak = 32767 * gain
            values = array.array("h", [int(max(-1.0, min(1.0, v)) * peak) for v in samples])
        k = self.factor * self.channels
        if k > 1:
            spread = array.array(values.typecode, bytes(values.itemsize * len(values) * k))
            for j in range(k):
                spread[j::k] = values
            values = spread
        return pygame.mixer.Sound(buffer=values.tobytes())

    def _build_sfx(self):
        S = self.synth
        T, N, A = S.tone, S.noise, S.arrange
        sfx = {
            "ui_move": T(1320, 0.045, attack=0.002, decay=0.015, volume=0.45),
            "ui_select": A([(0, T(880, 0.06, decay=0.03, volume=0.5)), (0.05, T(1320, 0.1, decay=0.05, volume=0.5))]),
            "ui_back": A([(0, T(990, 0.06, decay=0.03, volume=0.45)), (0.05, T(660, 0.1, decay=0.05, volume=0.45))]),
            "tick": T(2200, 0.02, attack=0.001, decay=0.006, volume=0.3),
            "scan": T(320, 0.8, "tri", attack=0.02, freq_end=1500, release=0.15, volume=0.4),
            "bad": A([(0, T(150, 0.28, "square", decay=0.12, volume=0.32)),
                      (0, T(157, 0.28, "square", decay=0.12, volume=0.32))]),
            "alarm": A([(k * 0.15, T(740 if k % 2 == 0 else 990, 0.15, "tri", attack=0.01, release=0.02,
                                     volume=0.45, vibrato=0.01)) for k in range(6)]),
            "snap": A([(0, T(1400, 0.36, "tri", freq_end=160, decay=0.16, volume=0.55)),
                       (0, N(0.12, decay=0.04, volume=0.35))]),
            "zap": A([(0, N(0.24, decay=0.08, volume=0.6, crackle=True)),
                      (0, T(90, 0.2, "square", decay=0.07, volume=0.25))]),
            "teleport": T(520, 0.26, freq_end=2100, decay=0.12, volume=0.4),
            "wave_clear": S.notes(("A4", "C5", "E5", "A5"), 0.07, 0.3, decay=0.12, volume=0.4,
                                  harmonics=((2, 0.25),)),
            "win": A([(0, S.notes(("A4", "C5", "E5", "A5"), 0.09, 0.3, decay=0.12, volume=0.4,
                                  harmonics=((2, 0.25),))),
                      (0.36, T(NOTE["A4"], 0.9, decay=0.45, volume=0.3, harmonics=((2, 0.3), (3, 0.1)))),
                      (0.36, T(NOTE["E5"], 0.9, decay=0.45, volume=0.25)),
                      (0.36, T(NOTE["A5"], 0.9, decay=0.45, volume=0.22))]),
            "lose": A([(0, S.notes(("E4", "C4", "A3"), 0.2, 0.35, wave="tri", decay=0.18, volume=0.45)),
                       (0.4, T(55, 0.7, "tri", decay=0.3, volume=0.5))]),
            "perk": S.notes(("E5", "A5", "D6", "C6", "E6", "A5"), 0.045, 0.22, decay=0.08, volume=0.35),
            "reveal": A([(k * 0.035, T(220 if k % 2 == 0 else 1320, 0.03, "square", volume=0.3)) for k in range(7)]
                        + [(0, N(0.25, decay=0.08, volume=0.25, crackle=True))]),
            "count": T(1000, 0.07, decay=0.03, volume=0.45),
            "count_last": T(1500, 0.14, decay=0.06, volume=0.5),
            "proof": A([(0, S.notes(("A4", "E5", "A5", "C6"), 0.08, 0.35, decay=0.14, volume=0.4,
                                    harmonics=((2, 0.2),))),
                        (0.34, T(NOTE["A5"], 1.0, decay=0.5, volume=0.3, harmonics=((1.5, 0.25),)))]),
            "wrong": A([(0, T(98, 0.45, "square", decay=0.2, volume=0.35)), (0, T(104, 0.45, "square", decay=0.2,
                                                                                volume=0.35))]),
            "type": T(1600, 0.016, attack=0.001, decay=0.005, volume=0.16),
            "star": T(1568, 0.55, decay=0.18, volume=0.45, harmonics=((2.0, 0.25), (3.01, 0.08))),
            "door": A([(0, T(90, 0.42, freq_end=45, decay=0.15, volume=0.8)), (0, N(0.15, decay=0.05, volume=0.25))]),
            "achievement": A([(0, S.notes(("E5", "A5", "C6", "E6"), 0.06, 0.3, decay=0.12, volume=0.35)),
                              (0.24, T(NOTE["A5"], 0.6, decay=0.3, volume=0.25, harmonics=((2, 0.2),)))]),
            "levelup": S.notes(("A4", "C5", "D5", "E5", "G5", "A5"), 0.05, 0.25, decay=0.1, volume=0.38),
            "flip": A([(0, T(300, 0.09, "tri", freq_end=900, volume=0.35)),
                       (0.09, T(900, 0.1, "tri", freq_end=300, decay=0.06, volume=0.35))]),
            "shield": A([(0, N(0.35, decay=0.1, volume=0.35, highpass=True)), (0, T(2400, 0.3, decay=0.07, volume=0.22)),
                         (0.02, T(1700, 0.3, decay=0.09, volume=0.22))]),
            "power_on": T(120, 0.5, "tri", attack=0.05, freq_end=480, decay=0.3, volume=0.3),
            "coin": A([(0, T(1320, 0.05, decay=0.03, volume=0.35)), (0.045, T(1760, 0.12, decay=0.06, volume=0.35))]),
        }
        for k, name in enumerate(("A4", "C5", "D5", "E5", "G5", "A5", "C6", "D6")):
            sfx["ok%d" % k] = T(NOTE[name], 0.3, attack=0.002, decay=0.11, volume=0.42, harmonics=((2, 0.3), (3, 0.08)))
        self.sounds = {name: self._to_sound(samples) for name, samples in sfx.items()}

    def _build_music(self):
        S = self.synth
        voices = {}
        for name in ("G1", "A1", "C2", "D2", "E2", "G2", "A2"):
            voices[("bass", name)] = S.tone(NOTE[name], 0.34, "tri", attack=0.006, decay=0.2, volume=0.9,
                                            harmonics=((2, 0.3),))
        arp_names = set()
        lead_names = set()
        for song in SONGS.values():
            for _, notes in song["bars"]:
                arp_names.update(notes)
            for bar in song["leads"] or ():
                lead_names.update(note for _, note in bar)
        for name in arp_names:
            voices[("arp", name)] = S.tone(NOTE[name], 0.3, attack=0.003, decay=0.1, volume=0.8,
                                           harmonics=((2, 0.3), (3, 0.1)))
        for name in lead_names:
            voices[("lead", name)] = S.tone(NOTE[name], 0.55, "tri", attack=0.015, decay=0.3, volume=0.8,
                                            vibrato=0.006)
        voices[("kick", "")] = S.tone(150, 0.28, attack=0.001, freq_end=42, decay=0.12, volume=1.0)
        voices[("snare", "")] = S.arrange([(0, S.noise(0.2, decay=0.06, volume=0.8, highpass=True)),
                                           (0, S.tone(185, 0.12, decay=0.04, volume=0.5))])
        voices[("hat", "")] = S.noise(0.06, decay=0.016, volume=0.9, highpass=True)
        self.voices = {key: self._to_sound(samples) for key, samples in voices.items()}

    # ---------------------------------------------------------------- effects
    @property
    def muted(self):
        return bool(self.settings.get("muted"))

    def play(self, name, volume=1.0):
        if not self.ok or self.muted:
            return
        sound = self.sounds.get(name)
        if sound is None:
            return
        now = self.clock
        if now - self.last.get(name, -1.0) < (0.035 if name in ("tick", "type", "ui_move") else 0.02):
            return
        self.last[name] = now
        channel = sound.play()
        if channel is not None:
            channel.set_volume(max(0.0, min(1.0, volume * self.settings.get("sfx", 0.7))))

    def play_ok(self, combo):
        """A success chime that climbs the scale as the combo grows."""
        self.play("ok%d" % min(7, combo % 8 if combo >= 8 else combo))

    # ------------------------------------------------------------------ music
    def set_track(self, name):
        if name == self.song_name:
            return
        self.song_name = name
        self.song = SONGS.get(name)
        self.step = 0
        self.acc = -0.25
        if self.song:
            self.bpm = self.song["bpm"]
        if self.ok:
            for channel in self.music_channels.values():
                channel.fadeout(220)

    def set_intensity(self, level):
        self.intensity = max(0, min(3, int(level)))

    def set_tempo(self, bpm):
        self.bpm = max(60, min(160, bpm))

    def update(self, dt):
        self.clock += dt
        if not self.ok or self.song is None:
            return
        self.acc += dt
        step_time = 60.0 / self.bpm / 4.0
        played = 0
        while self.acc >= step_time:
            self.acc -= step_time
            if played < 4:
                self._play_step()
            played += 1
            self.step = (self.step + 1) % (16 * len(self.song["bars"]))

    def _voice(self, voice, note, level):
        sound = self.voices.get((voice, note))
        if sound is None:
            return
        volume = 0.0 if self.muted else VOICE_LEVEL[voice] * level * self.settings.get("music", 0.5)
        channel = self.music_channels[voice]
        channel.play(sound)
        channel.set_volume(max(0.0, min(1.0, volume)))

    def _play_step(self):
        song = self.song
        bar_index, step = divmod(self.step, 16)
        root, arps = song["bars"][bar_index]
        game = self.song_name == "game"
        intensity = self.intensity if game else 1
        if step in song["bass"]:
            self._voice("bass", root, 1.0)
        if step in song["arp"]:
            self._voice("arp", arps[song["arp"].index(step)], 1.0 if step % 4 == 0 else 0.75)
        if step in song["hat"] and (not game or intensity >= 1):
            self._voice("hat", "", 1.0 if step % 4 == 2 else 0.6)
        if game and intensity >= 3 and step % 2 == 0 and step not in song["hat"]:
            self._voice("hat", "", 0.45)
        if game and intensity >= 2:
            kicks = (0, 4, 8, 12) if intensity >= 3 else song["kick"]
            if step in kicks:
                self._voice("kick", "", 1.0)
            if step in song["snare"]:
                self._voice("snare", "", 1.0)
        if game and intensity >= 3 and song["leads"]:
            for at, note in song["leads"][bar_index]:
                if at == step:
                    self._voice("lead", note, 1.0)

    def stop(self):
        if self.ok:
            pygame.mixer.stop()
