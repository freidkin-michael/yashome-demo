"""The demo flat's weather as a day script: each day has its own run of weather (a clear morning, clouds by noon, a shower in
some afternoons, a clear or cloudy night), drawn from the day's number so it is the same for the sim and the forecast, and
the outdoor temperature as a daily curve with the weather's own offset (rain cools it). Pure: no clock of its own."""
import math
import random
import time

MODES = ("clear", "cloudy", "rain", "heatwave")
OFFSET = {"clear": 0.0, "cloudy": -2.5, "rain": -5.0, "heatwave": 9.0}      # degrees against the day's own curve
CODE = {"clear": 1, "cloudy": 3, "rain": 63, "heatwave": 0}                   # WMO: mainly clear, overcast, rain, clear
RAIN_PROB = {"clear": 0, "cloudy": 15, "rain": 85, "heatwave": 0}


def _day(t: float) -> int:
    lt = time.localtime(t)
    return lt.tm_year * 1000 + lt.tm_yday


def plan(day: int, seed: int = 7) -> list:
    """[(from hour, mode)] of one day: at least three kinds of weather, a heatwave only some days."""
    r = random.Random(seed * 100003 + day)
    hot = r.random() < 0.12
    for _ in range(20):
        p = [(0, r.choice(["clear", "cloudy"])), (6, "heatwave" if hot else r.choice(["clear", "clear", "cloudy"])),
             (11, "heatwave" if hot else r.choice(["cloudy", "cloudy", "clear"])),
             (14, "rain" if r.random() < 0.45 else r.choice(["cloudy", "clear"])), (18, r.choice(["clear", "cloudy"])),
             (21, r.choice(["clear", "cloudy", "rain"]))]
        if len({m for _h, m in p}) >= 3:
            return p
    return [(0, "clear"), (6, "clear"), (11, "cloudy"), (14, "rain"), (18, "cloudy"), (21, "clear")]


def mode_at(t: float, seed: int = 7) -> str:
    lt = time.localtime(t)
    h, out = lt.tm_hour + lt.tm_min / 60, "clear"
    for start, m in plan(_day(t), seed):
        if h >= start:
            out = m
    return out


def base(t: float, seed: int = 7) -> float:
    """The day's own curve (no weather): its mean and swing vary a little from day to day; coolest near 05:00, warmest at 15:00."""
    r = random.Random(seed * 7919 + _day(t))
    mean, swing = 19 + r.uniform(-3, 3), 5 + r.uniform(-1, 2)
    lt = time.localtime(t)
    h = lt.tm_hour + lt.tm_min / 60
    return mean + swing * math.cos((h - 15) / 24 * 2 * math.pi)


def target(t: float, mode: str, seed: int = 7) -> float:
    """The outdoor temperature the air moves towards at t in this weather."""
    return base(t, seed) + OFFSET.get(mode, 0.0)
