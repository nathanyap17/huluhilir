"""Measure a classifier backend against LABELLED photographs.

This exists because the question "is L1 effectively identifying six classes?"
cannot be answered from production data. Counting which classes have appeared
in output measures **coverage**, not accuracy: a classifier that assigns
labels at random produces all six too. Only ground truth separates them.

Usage
-----
Put photographs into one directory per class:

    eval_set/
      healthy_leaf/     img001.jpg ...
      healthy_collar/   ...
      foliar_yellowing/ ...
      collar_lesion/    ...
      defoliation_wilt/ ...
      unrelated/        ...

Then, from backend/:

    python scripts/eval_classifier.py ../eval_set --backend onnx
    python scripts/eval_classifier.py ../eval_set --backend gemini

Reports per-class precision/recall/F1, macro F1, and a confusion matrix.

Two notes on reading the result honestly:

* **Report the number for the backend you actually deploy.** The CNN's 0.934
  macro F1 belongs to the CNN on the CNN's own test set and says nothing
  about the vision backend, or vice versa.
* **`collar_lesion` recall matters more than macro F1.** A missed collar
  lesion is a vine lost; a false alarm costs one wasted inspection. Read that
  row first and do not let a strong macro average hide a weak one.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.enums import CaptureTarget, DiseaseClass  # noqa: E402

CLASSES = [c.value for c in DiseaseClass if c.value != "unknown"]

# Which capture target a class belongs to, so the mismatch check is exercised
# the way it would be in the field rather than always being told "leaf".
TARGET_FOR = {
    "healthy_leaf": CaptureTarget.leaf,
    "foliar_yellowing": CaptureTarget.leaf,
    "healthy_collar": CaptureTarget.collar,
    "collar_lesion": CaptureTarget.collar,
    "defoliation_wilt": CaptureTarget.leaf,
    "unrelated": CaptureTarget.leaf,
}


async def classify(path: Path, truth: str, backend: str) -> str:
    target = TARGET_FOR.get(truth, CaptureTarget.leaf)
    if backend == "gemini":
        from app.tools.diagnose_gemini import diagnose_leaf_gemini

        result = await diagnose_leaf_gemini("eval", str(path), target)
    else:
        from app.tools.diagnose import diagnose_leaf

        result = diagnose_leaf("eval", str(path), target)
    return result.predicted_class


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_dir", type=Path)
    ap.add_argument("--backend", choices=["onnx", "gemini"], default="onnx")
    args = ap.parse_args()

    items: list[tuple[Path, str]] = []
    for cls in CLASSES:
        d = args.eval_dir / cls
        if not d.is_dir():
            print(f"  (no directory for {cls} -- that class will be unmeasured)")
            continue
        for f in sorted(d.iterdir()):
            if f.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                items.append((f, cls))

    if not items:
        print("No images found. See the module docstring for the layout.")
        return 1

    print(f"Evaluating {len(items)} images with backend={args.backend}\n")

    confusion: dict[str, Counter] = defaultdict(Counter)
    failures: list[str] = []
    for i, (path, truth) in enumerate(items, 1):
        try:
            pred = await classify(path, truth, args.backend)
        except Exception as exc:  # noqa: BLE001 -- one bad file must not end the run
            failures.append(f"{path.name}: {type(exc).__name__}: {exc}")
            continue
        confusion[truth][pred] += 1
        print(f"  [{i}/{len(items)}] {path.name:<28} truth={truth:<18} pred={pred}")

    print("\n" + "=" * 68)
    print(f"{'class':<20}{'prec':>8}{'recall':>9}{'F1':>8}{'support':>9}")
    print("-" * 68)

    f1s = []
    for cls in CLASSES:
        tp = confusion[cls][cls]
        fn = sum(confusion[cls].values()) - tp
        fp = sum(confusion[t][cls] for t in CLASSES if t != cls)
        support = tp + fn
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / support if support else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        # Only classes with examples count toward the macro average -- folding
        # in an unmeasured class as 0.0 would understate the model, and
        # skipping it silently would overstate it, so it is printed either way.
        if support:
            f1s.append(f1)
        flag = "" if support else "   <- NO EXAMPLES, unmeasured"
        print(f"{cls:<20}{prec:>8.3f}{rec:>9.3f}{f1:>8.3f}{support:>9}{flag}")

    print("-" * 68)
    print(f"{'MACRO F1':<20}{'':>8}{'':>9}{(sum(f1s) / len(f1s) if f1s else 0.0):>8.3f}"
          f"{sum(sum(c.values()) for c in confusion.values()):>9}")
    print(f"measured over {len(f1s)}/{len(CLASSES)} classes")

    lesion = confusion["collar_lesion"]
    lesion_support = sum(lesion.values())
    if lesion_support:
        rec = lesion["collar_lesion"] / lesion_support
        print(f"\ncollar_lesion recall: {rec:.3f}  "
              f"({lesion['collar_lesion']}/{lesion_support}) "
              "-- read this before the macro average")
        missed = {k: v for k, v in lesion.items() if k != "collar_lesion"}
        if missed:
            print(f"  missed as: {dict(missed)}")

    print("\nConfusion (rows = truth, columns = predicted)")
    header = "".join(f"{c[:9]:>11}" for c in CLASSES)
    print(f"{'':<20}{header}")
    for truth in CLASSES:
        row = "".join(f"{confusion[truth][p]:>11}" for p in CLASSES)
        print(f"{truth:<20}{row}")

    if failures:
        print(f"\n{len(failures)} image(s) failed to classify:")
        for f in failures[:10]:
            print(f"  {f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
