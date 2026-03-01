import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
import pygame


# Display

WIDTH, HEIGHT = 900, 600
FPS = 120

BG = (18, 18, 22)
TEXT = (230, 230, 235)
SUBTEXT = (160, 160, 170)
TARGET_OUTLINE = (255, 255, 255)
TARGET_FILL = (0, 0, 0)
CROSSHAIR = (230, 230, 235)


# Files

SCORES_FILE = Path("aim_scores.json")
SETTINGS_FILE = Path("aim_settings.json")


# Modes

MODE_FLICK = "flick"
MODE_TRACK = "tracking"


# Difficulty

DIFF_PRESETS = {
    "Easy":   {"r_start": 55, "r_end": 24, "interval_start": 1.35, "interval_end": 0.65, "track_speed_start": 140, "track_speed_end": 260},
    "Medium": {"r_start": 50, "r_end": 18, "interval_start": 1.20, "interval_end": 0.45, "track_speed_start": 160, "track_speed_end": 320},
    "Hard":   {"r_start": 44, "r_end": 14, "interval_start": 1.00, "interval_end": 0.35, "track_speed_start": 190, "track_speed_end": 380},
}

TIME_OPTIONS = [30, 60, 90, 120]


@dataclass
class Target:
    x: float
    y: float
    r: int
    spawn_time: float
    vx: float = 0.0
    vy: float = 0.0


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def dist2(ax, ay, bx, by) -> float:
    dx = ax - bx
    dy = ay - by
    return dx * dx + dy * dy


def load_settings() -> dict:
    # Default
    defaults = {
        "mode": MODE_FLICK,
        "difficulty": "Medium",
        "duration": 60,
    }
    if not SETTINGS_FILE.exists():
        return defaults
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        mode = data.get("mode", defaults["mode"])
        difficulty = data.get("difficulty", defaults["difficulty"])
        duration = int(data.get("duration", defaults["duration"]))

        if mode not in (MODE_FLICK, MODE_TRACK):
            mode = defaults["mode"]
        if difficulty not in DIFF_PRESETS:
            difficulty = defaults["difficulty"]
        if duration not in TIME_OPTIONS:
            duration = defaults["duration"]

        return {"mode": mode, "difficulty": difficulty, "duration": duration}
    except Exception:
        return defaults


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def load_scores() -> dict:
    # scores keyed by a "profile key" e.g. "flick|Medium|60"
    if not SCORES_FILE.exists():
        return {}
    try:
        return json.loads(SCORES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_scores(scores: dict) -> None:
    payload = {"best_score": scores, "updated_at": int(time.time())}
    SCORES_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def profile_key(mode: str, difficulty: str, duration: int) -> str:
    return f"{mode}|{difficulty}|{duration}"


def get_best(scores: dict, mode: str, difficulty: str, duration: int) -> int:
    key = profile_key(mode, difficulty, duration)
    best_map = scores.get("best_score", {}) if isinstance(scores, dict) else {}
    return int(best_map.get(key, 0))


def set_best(scores: dict, mode: str, difficulty: str, duration: int, value: int) -> None:
    if "best_score" not in scores or not isinstance(scores["best_score"], dict):
        scores["best_score"] = {}
    key = profile_key(mode, difficulty, duration)
    scores["best_score"][key] = int(value)


def difficulty_at(elapsed: float, duration: int, preset_name: str):

    preset = DIFF_PRESETS[preset_name]
    t = clamp(elapsed / max(1, duration), 0.0, 1.0)

    radius = int(round(preset["r_start"] - (preset["r_start"] - preset["r_end"]) * t))
    interval = preset["interval_start"] - (preset["interval_start"] - preset["interval_end"]) * t
    track_speed = preset["track_speed_start"] + (preset["track_speed_end"] - preset["track_speed_start"]) * t

    return radius, interval, track_speed


def spawn_target(r: int) -> Target:
    pad = r + 10
    x = random.randint(pad, WIDTH - pad)
    y = random.randint(pad, HEIGHT - pad)
    return Target(x=float(x), y=float(y), r=r, spawn_time=time.time())


def spawn_tracking_target(r: int, speed: float) -> Target:
    t = spawn_target(r)

    t.vx = random.choice([-1, 1]) * random.uniform(0.7, 1.0) * speed
    t.vy = random.choice([-1, 1]) * random.uniform(0.7, 1.0) * speed
    return t


def draw_target(screen, target: Target):
    pygame.draw.circle(screen, TARGET_OUTLINE, (int(target.x), int(target.y)), target.r, width=3)
    pygame.draw.circle(screen, TARGET_FILL, (int(target.x), int(target.y)), max(1, target.r - 6))


def draw_crosshair(screen, mx, my):
    pygame.draw.line(screen, CROSSHAIR, (mx - 10, my), (mx + 10, my), width=1)
    pygame.draw.line(screen, CROSSHAIR, (mx, my - 10), (mx, my + 10), width=1)
    pygame.draw.circle(screen, CROSSHAIR, (mx, my), 2, width=1)


def fmt_mode(m: str) -> str:
    return "Flick" if m == MODE_FLICK else "Tracking"


def main():
    pygame.init()
    pygame.display.set_caption("Aim Trainer (Settings + Modes)")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    font_big = pygame.font.SysFont("consolas", 38)
    font = pygame.font.SysFont("consolas", 22)
    font_small = pygame.font.SysFont("consolas", 18)

    settings = load_settings()
    scores = load_scores()

    # UI selections
    mode = settings["mode"]
    difficulty = settings["difficulty"]
    duration = settings["duration"]

    # Game state
    state = "settings"  # settings | playing | gameover

    score = 0
    hits = 0
    misses = 0
    reaction_samples = []

    # tracking
    track_time_inside = 0.0
    track_tick_ms = 0

    start_time = 0.0
    target = None

    def start_game():
        nonlocal state, score, hits, misses, reaction_samples, track_time_inside, track_tick_ms
        nonlocal start_time, target

        state = "playing"
        score = 0
        hits = 0
        misses = 0
        reaction_samples = []
        track_time_inside = 0.0
        track_tick_ms = 0

        start_time = time.time()
        r, _, spd = difficulty_at(0.0, duration, difficulty)
        target = spawn_tracking_target(r, spd) if mode == MODE_TRACK else spawn_target(r)

        save_settings({"mode": mode, "difficulty": difficulty, "duration": duration})

    def end_game():
        nonlocal state, scores
        state = "gameover"
        best = get_best(scores, mode, difficulty, duration)
        if score > best:
            set_best(scores, mode, difficulty, duration, score)
            save_scores(scores)

    def tracking_update(dt: float, mx: int, my: int):
        nonlocal target, score, track_time_inside, track_tick_ms
        if target is None:
            return


        target.x += target.vx * dt
        target.y += target.vy * dt

        pad = target.r + 10
        if target.x < pad:
            target.x = pad
            target.vx *= -1
        elif target.x > WIDTH - pad:
            target.x = WIDTH - pad
            target.vx *= -1

        if target.y < pad:
            target.y = pad
            target.vy *= -1
        elif target.y > HEIGHT - pad:
            target.y = HEIGHT - pad
            target.vy *= -1

        inside = dist2(mx, my, target.x, target.y) <= target.r * target.r

        if inside:
            track_time_inside += dt

            track_tick_ms += int(dt * 1000)
            while track_tick_ms >= 100:
                track_tick_ms -= 100
                score += 1

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        mx, my = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if state == "playing":
                        state = "settings"
                    else:
                        running = False

                if state == "settings":

                    if event.key == pygame.K_m:
                        mode = MODE_TRACK if mode == MODE_FLICK else MODE_FLICK


                    if event.key == pygame.K_d:
                        names = list(DIFF_PRESETS.keys())
                        idx = names.index(difficulty)
                        difficulty = names[(idx + 1) % len(names)]


                    if event.key == pygame.K_t:
                        idx = TIME_OPTIONS.index(duration)
                        duration = TIME_OPTIONS[(idx + 1) % len(TIME_OPTIONS)]


                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        start_game()

                elif state == "gameover":
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        start_game()
                    if event.key == pygame.K_s:
                        state = "settings"

                elif state == "playing":
                    if event.key == pygame.K_r:
                        start_game()

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if state == "settings":
                    start_game()

                elif state == "gameover":
                    start_game()

                elif state == "playing" and mode == MODE_FLICK and target is not None:
                    inside = dist2(mx, my, target.x, target.y) <= target.r * target.r
                    if inside:
                        hits += 1
                        score += 1
                        reaction_samples.append(time.time() - target.spawn_time)

                        elapsed = time.time() - start_time
                        r, _, _ = difficulty_at(elapsed, duration, difficulty)
                        target = spawn_target(r)
                    else:
                        misses += 1
                        score = max(0, score - 1)

        screen.fill(BG)

        if state == "settings":
            title = font_big.render("AIM TRAINER", True, TEXT)
            subtitle = font.render("SETTINGS", True, SUBTEXT)

            best_here = get_best(scores, mode, difficulty, duration)
            line1 = font.render(f"Mode: {fmt_mode(mode)}   (Press M to toggle)", True, TEXT)
            line2 = font.render(f"Difficulty: {difficulty}   (Press D to cycle)", True, TEXT)
            line3 = font.render(f"Duration: {duration}s   (Press T to cycle)", True, TEXT)
            line4 = font.render(f"Best (this setup): {best_here}", True, SUBTEXT)

            hint = font_small.render("ENTER/SPACE or Click to start | ESC quit", True, SUBTEXT)

            screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 140))
            screen.blit(subtitle, (WIDTH // 2 - subtitle.get_width() // 2, 200))
            screen.blit(line1, (WIDTH // 2 - line1.get_width() // 2, 260))
            screen.blit(line2, (WIDTH // 2 - line2.get_width() // 2, 295))
            screen.blit(line3, (WIDTH // 2 - line3.get_width() // 2, 330))
            screen.blit(line4, (WIDTH // 2 - line4.get_width() // 2, 370))
            screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, 420))

        elif state == "playing":
            now = time.time()
            elapsed = now - start_time
            left = duration - elapsed

            r, interval, spd = difficulty_at(elapsed, duration, difficulty)

            if left <= 0:
                end_game()
            else:
                if target is None:
                    target = spawn_tracking_target(r, spd) if mode == MODE_TRACK else spawn_target(r)
                else:
                    target.r = r

                    if mode == MODE_FLICK:

                        if now - target.spawn_time >= interval:
                            misses += 1
                            target = spawn_target(r)
                    else:

                        target.vx = (1 if target.vx >= 0 else -1) * spd * 0.85
                        target.vy = (1 if target.vy >= 0 else -1) * spd * 0.85
                        tracking_update(dt, mx, my)

                draw_target(screen, target)


                if mode == MODE_FLICK:
                    attempts = hits + misses
                    acc = (hits / attempts * 100.0) if attempts > 0 else 0.0
                    avg_react = (sum(reaction_samples) / len(reaction_samples)) if reaction_samples else 0.0

                    hud1 = font.render(
                        f"Mode: FLICK | Diff: {difficulty} | Score: {score} | Hits: {hits} Misses: {misses} Acc: {acc:0.1f}%",
                        True, TEXT
                    )
                    hud2 = font_small.render(
                        f"Time: {left:0.1f}s | r={r}px | Avg reaction: {avg_react:0.3f}s | R restart | ESC settings",
                        True, SUBTEXT
                    )
                else:
                    hud1 = font.render(
                        f"Mode: TRACKING | Diff: {difficulty} | Score: {score} | Time-on-target: {track_time_inside:0.2f}s",
                        True, TEXT
                    )
                    hud2 = font_small.render(
                        f"Time: {left:0.1f}s | r={r}px | speed≈{int(spd)}px/s | R restart | ESC settings",
                        True, SUBTEXT
                    )

                screen.blit(hud1, (20, 15))
                screen.blit(hud2, (20, 45))

        elif state == "gameover":
            best_here = get_best(scores, mode, difficulty, duration)

            title = font_big.render("TIME!", True, TEXT)
            stats = font.render(
                f"{fmt_mode(mode)} | {difficulty} | {duration}s  —  Score: {score}  Best: {best_here}",
                True, SUBTEXT
            )

            if mode == MODE_FLICK:
                attempts = hits + misses
                acc = (hits / attempts * 100.0) if attempts > 0 else 0.0
                avg_react = (sum(reaction_samples) / len(reaction_samples)) if reaction_samples else 0.0
                more = font.render(
                    f"Hits: {hits}  Misses: {misses}  Acc: {acc:0.1f}%  Avg reaction: {avg_react:0.3f}s",
                    True, SUBTEXT
                )
            else:
                more = font.render(f"Time-on-target: {track_time_inside:0.2f}s", True, SUBTEXT)

            hint = font.render("SPACE/ENTER or Click to play again | S settings | ESC quit", True, SUBTEXT)

            screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 185))
            screen.blit(stats, (WIDTH // 2 - stats.get_width() // 2, 245))
            screen.blit(more, (WIDTH // 2 - more.get_width() // 2, 285))
            screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, 345))

        draw_crosshair(screen, mx, my)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()