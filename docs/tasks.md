# Tasks

MolmoAct-2 is a policy, not a planner — it does what its training distribution covers, and
freezes (near-zero motion, "twitches") on anything out of it. Two things must be
in-distribution: the **task string** *and* the **scene**.

## Known-good task
The default, and MolmoAct-2's own zero-shot YAM eval task:

> **"Fold the towel and place it on the side."**

Bimanual, in-distribution. Set up a towel flat in front of the arms.

## The training distribution
The `BimanualYAM` checkpoint was fine-tuned on a bimanual-YAM mixture — table-bussing /
manipulation (the HF sample task is *"Place cups and plate in dishwasher rack, dispose of food
waste, and organize remaining items."*). MolmoAct-2's docs scope out-of-box use to **"simple
tasks within the training task distribution (Pick-and-Place, opening, closing)."**

- Authoritative task list: the `allenai/MolmoAct2-BimanualYAM` dataset annotations.
- Reference eval setup: Cortex's zero-shot YAM eval and `williamtsai726/YAM`.

## Phrasing
- `normalize_language` is on by default server-side (lowercases, strips trailing punctuation).
- Match the *style* of training instructions; novel phrasings drift OOD.
- If the arms only twitch: it's almost always OOD task/scene, not a tuning problem. Change the
  task/scene before touching `control_hz` / clamps.

## Reading whether it's working
Run with logging (see `scripts/` or instrument `execute`): per cycle, watch **latency** (warm
≈ 1–2 s; cold = 30–60 s) and the **action-chunk motion magnitude** (`sum |last_row − first_row|`;
~0 = frozen/OOD; a real number = it's planning actual motion).
