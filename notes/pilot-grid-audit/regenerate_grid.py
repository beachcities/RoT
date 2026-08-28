# -*- coding: utf-8 -*-
"""パイロット記録のテキスト格子を、正本 JSON から機械再現する。

    python regenerate_grid.py <benchmark ディレクトリ> <run_at>

例：

    python regenerate_grid.py C:/Users/masay/RoT/benchmark 20260826T132218Z

**正本 JSON を読むだけで、何も書き換えない。** 4bbbd47 で消えた14行が
結果 JSON から一意に再現できることを示すためのもの。
"""

import importlib.util
import json
import pathlib
import sys


def load(bench, name):
    spec = importlib.util.spec_from_file_location(name, bench / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(bench))
    spec.loader.exec_module(mod)
    return mod


def main(bench, run_at):
    bench = pathlib.Path(bench).resolve()
    v4_grid = load(bench, "v4_grid")
    run = json.load(open(bench / "results" / "reference" / f"run_{run_at}.json",
                        encoding="utf-8"))
    cells = v4_grid.collect(run)
    print("## 格子（テキスト版）")
    print()
    print(f"同じ内容の一枚 HTML は `{run_at}_grid.html`。"
          "**HTML が開けない場所のために併存させている。**")
    print()
    print("```")
    print(v4_grid.text_grid(cells))
    print("```")


if __name__ == "__main__":
    main(*sys.argv[1:3])
