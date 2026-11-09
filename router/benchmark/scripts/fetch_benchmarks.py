"""Download candidate rows from public benchmarks via the Hugging Face datasets-server API."""
import json, random, ssl, sys, time, urllib.parse, urllib.request
import certifi

OUT = sys.argv[1]
CTX = ssl.create_default_context(cafile=certifi.where())
API = "https://datasets-server.huggingface.co"

def get(path, **params):
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "benchmark-fetch"}), timeout=60, context=CTX) as r:
                return json.loads(r.read())
        except Exception as e:
            print("  retry", attempt, e, file=sys.stderr); time.sleep(3 + attempt * 4)
    raise SystemExit(f"failed: {url}")

def rows(ds, config, split, offsets, where=None, length=100):
    out = []
    for off in offsets:
        params = dict(dataset=ds, config=config, split=split, offset=off, length=length)
        if where: params["where"] = where
        d = get("filter" if where else "rows", **params)
        out += [{"row_idx": r["row_idx"], **r["row"]} for r in d["rows"]]
        time.sleep(1.5)
    return out

def total(ds, config, split, where=None):
    params = dict(dataset=ds, config=config, split=split, offset=0, length=1)
    if where: params["where"] = where
    return get("filter" if where else "rows", **params)["num_rows_total"]

rng = random.Random(490)
def spread(n_total, pages=3):
    return sorted(rng.sample(range(0, max(1, n_total - 100), 100), min(pages, max(1, n_total // 100))))

SOURCES = {
  "mbpp": ("google-research-datasets/mbpp", "sanitized", "test", None),
  "humaneval": ("openai/openai_humaneval", "openai_humaneval", "test", None),
  "bigcodebench_hard": ("bigcode/bigcodebench-hard", "default", "v0.1.4", None),
  "gsm8k": ("openai/gsm8k", "main", "test", None),
  "math_mid": ("HuggingFaceH4/MATH-500", "default", "test", '"level" = 2 OR "level" = 3'),
  "math_hard": ("HuggingFaceH4/MATH-500", "default", "test", '"level" = 5'),
  "xsum": ("EdinburghNLP/xsum", "default", "test", None),
  "cnn": ("abisee/cnn_dailymail", "3.0.0", "test", None),
  "squad": ("rajpurkar/squad_v2", "squad_v2", "validation", None),
  "dolly_ie": ("databricks/databricks-dolly-15k", "default", "train", "\"category\" = 'information_extraction'"),
  "drop": ("ucinlp/drop", "default", "validation", None),
  "mtbench": ("HuggingFaceH4/mt_bench_prompts", "default", "train", None),
  "ifeval": ("google/IFEval", "default", "train", None),
  "dolly": ("databricks/databricks-dolly-15k", "default", "train", None),
  "arena_hard": ("lmarena-ai/arena-hard-auto-v0.1", "default", "train", None),
}
only = set(sys.argv[2:])
for name, (ds, config, split, where) in SOURCES.items():
    if only and name not in only: continue
    n = total(ds, config, split, where)
    pages = 1 if n <= 100 else (5 if n <= 600 else (15 if name == 'dolly' else 3))
    offsets = list(range(0, n, 100))[:pages] if n <= 600 else spread(n, pages)
    data = rows(ds, config, split, offsets, where)
    json.dump({"dataset": ds, "config": config, "split": split, "where": where, "num_rows_total": n, "rows": data},
              open(f"{OUT}/{name}.json", "w"))
    print(f"{name}: {len(data)} rows of {n} ({ds} {config}/{split})")
