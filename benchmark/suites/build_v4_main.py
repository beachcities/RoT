# -*- coding: utf-8 -*-
"""本測定用の組を作る——**パイロットと同一設計、seed 帯だけが違う**。

第二凍結（`paper/notes/instrument-v2-freeze2.md`）第3節：

    本測定 n=400 ＝ パイロットと同一の200標本設計を、別の master seed 帯で2回反復。

**凍結済みの生成器 `build_v4.py` には手を触れない。** この場から
`build_v4.MASTER_SEEDS` を差し替えて同じ `main()` を呼ぶので、V・H・γ・N_TABLE・
変種の作り方・完全交差・入れ子の先頭取りは**文字どおり同じコード**が決める。
違うのは seed 帯だけであることが、実装上保証される。

    python suites/build_v4_main.py
"""

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("build_v4", HERE / "build_v4.py")
build_v4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_v4)

# 本測定の master seed 帯。**既存（スモーク 20260820〜29、パイロット 20260901〜12）
# とも、相互とも重ならない。**
BANDS = {
    "v4_distribution_m1": [20261001 + i for i in range(12)],   # 反復1
    "v4_distribution_m2": [20261101 + i for i in range(12)],   # 反復2
}


def main():
    for name, seeds in BANDS.items():
        build_v4.MASTER_SEEDS = seeds          # design_for が参照するのはこの大域
        sys.argv = ["build_v4", "--out", str(HERE / name)]
        print(f"=== {name} ===")
        build_v4.main()
        print()


if __name__ == "__main__":
    main()
