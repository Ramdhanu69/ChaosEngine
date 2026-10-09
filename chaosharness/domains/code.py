import ast
import random
import json
import re
import time
from typing import Any
from .sandbox import run_in_sandbox
from ..scoring import ItemResult, FailureLabel
from ..generators import stable_seed

class CodeAlgorithm:
    def __init__(self, name: str, task: str, signature: str):
        self.name = name
        self.task = task
        self.signature = signature

    def generate_tests(self, seed: int) -> list[tuple[Any, Any]]:
        raise NotImplementedError

class AlgoKMostFreq(CodeAlgorithm):
    def __init__(self):
        super().__init__(
            "k_most_frequent",
            "Return the k most frequent elements in a list of integers, with ties broken by first appearance.",
            "def k_most_frequent(nums, k):"
        )
    def generate_tests(self, seed: int) -> list[tuple[Any, Any]]:
        rng = random.Random(seed)
        tests = []
        for _ in range(5):
            nums = [rng.randint(1, 6) for _ in range(15)]
            k = rng.randint(1, 3)
            counts = {}
            first = {}
            for i, n in enumerate(nums):
                counts[n] = counts.get(n, 0) + 1
                if n not in first:
                    first[n] = i
            res = sorted(counts.keys(), key=lambda x: (-counts[x], first[x]))[:k]
            tests.append(((nums, k), res))
        return tests

class AlgoRunLength(CodeAlgorithm):
    def __init__(self):
        super().__init__(
            "run_length_encoding",
            "Return run-length encoding as a list of [char, count] pairs.",
            "def run_length_encoding(s):"
        )
    def generate_tests(self, seed: int) -> list[tuple[Any, Any]]:
        rng = random.Random(seed)
        tests = []
        chars = ["A", "B", "C", "D"]
        for _ in range(5):
            s = ""
            for _ in range(rng.randint(2, 6)):
                c = rng.choice(chars)
                s += c * rng.randint(1, 4)
            if not s:
                expected = []
            else:
                expected = []
                cur, cnt = s[0], 1
                for ch in s[1:]:
                    if ch == cur:
                        cnt += 1
                    else:
                        expected.append([cur, cnt])
                        cur, cnt = ch, 1
                expected.append([cur, cnt])
            tests.append(((s,), expected))
        return tests

class AlgoSecondLargest(CodeAlgorithm):
    def __init__(self):
        super().__init__(
            "second_largest",
            "Return the second largest distinct integer from a list, or None if fewer than 2 distinct elements exist.",
            "def second_largest(nums):"
        )
    def generate_tests(self, seed: int) -> list[tuple[Any, Any]]:
        rng = random.Random(seed)
        tests = []
        for _ in range(5):
            nums = [rng.randint(1, 20) for _ in range(rng.randint(3, 10))]
            distinct = sorted(list(set(nums)), reverse=True)
            exp = distinct[1] if len(distinct) >= 2 else None
            tests.append(((nums,), exp))
        return tests

class AlgoBalancedBrackets(CodeAlgorithm):
    def __init__(self):
        super().__init__(
            "balanced_brackets",
            "Return True if brackets '()', '[]', '{}' in string s are balanced, else False.",
            "def balanced_brackets(s):"
        )
    def generate_tests(self, seed: int) -> list[tuple[Any, Any]]:
        rng = random.Random(seed)
        tests = []
        pairs = {')': '(', ']': '[', '}': '{'}
        openers = list(pairs.values())
        closers = list(pairs.keys())
        for i in range(5):
            if i % 2 == 0:
                # generate balanced
                s = ""
                for _ in range(rng.randint(1, 4)):
                    pair = rng.choice([("(", ")"), ("[", "]"), ("{", "}")])
                    s = pair[0] + s + pair[1]
            else:
                # random mix
                s = "".join(rng.choice(openers + closers) for _ in range(rng.randint(2, 6)))
            
            stack = []
            bal = True
            for c in s:
                if c in openers:
                    stack.append(c)
                elif c in pairs:
                    if not stack or stack.pop() != pairs[c]:
                        bal = False
                        break
            if stack:
                bal = False
            tests.append(((s,), bal))
        return tests

class AlgoMergeIntervals(CodeAlgorithm):
    def __init__(self):
        super().__init__(
            "merge_intervals",
            "Merge all overlapping intervals. Intervals are represented as [start, end] pairs.",
            "def merge_intervals(intervals):"
        )
    def generate_tests(self, seed: int) -> list[tuple[Any, Any]]:
        rng = random.Random(seed)
        tests = []
        for _ in range(5):
            intervals = []
            for _ in range(rng.randint(2, 6)):
                st = rng.randint(1, 15)
                en = st + rng.randint(1, 6)
                intervals.append([st, en])
            sorted_int = sorted(intervals, key=lambda x: x[0])
            merged = [sorted_int[0]]
            for cur in sorted_int[1:]:
                prev = merged[-1]
                if cur[0] <= prev[1]:
                    prev[1] = max(prev[1], cur[1])
                else:
                    merged.append(cur)
            tests.append(((intervals,), merged))
        return tests

class AlgoRotateList(CodeAlgorithm):
    def __init__(self):
        super().__init__(
            "rotate_list",
            "Rotate list nums to the right by k steps.",
            "def rotate_list(nums, k):"
        )
    def generate_tests(self, seed: int) -> list[tuple[Any, Any]]:
        rng = random.Random(seed)
        tests = []
        for _ in range(5):
            nums = [rng.randint(1, 10) for _ in range(rng.randint(4, 8))]
            k = rng.randint(0, 10)
            shift = k % len(nums)
            exp = nums[-shift:] + nums[:-shift] if shift != 0 else list(nums)
            tests.append(((nums, k), exp))
        return tests

class AlgoFlatten(CodeAlgorithm):
    def __init__(self):
        super().__init__(
            "flatten_nested",
            "Flatten an arbitrarily nested list of integers into a single flat list.",
            "def flatten_nested(lst):"
        )
    def generate_tests(self, seed: int) -> list[tuple[Any, Any]]:
        rng = random.Random(seed)
        tests = []
        for _ in range(5):
            nested = [
                rng.randint(1, 5),
                [rng.randint(6, 10), [rng.randint(11, 15)]],
                rng.randint(16, 20)
            ]
            flat = []
            def _rec(item):
                if isinstance(item, list):
                    for x in item:
                        _rec(x)
                else:
                    flat.append(item)
            _rec(nested)
            tests.append(((nested,), flat))
        return tests

class AlgoTwoSum(CodeAlgorithm):
    def __init__(self):
        super().__init__(
            "two_sum",
            "Return indices [i, j] of two numbers summing to target, or None if no such pair exists.",
            "def two_sum(nums, target):"
        )
    def generate_tests(self, seed: int) -> list[tuple[Any, Any]]:
        rng = random.Random(seed)
        tests = []
        for _ in range(5):
            nums = [rng.randint(1, 20) for _ in range(8)]
            i, j = rng.sample(range(8), 2)
            target = nums[i] + nums[j]
            seen = {}
            res = None
            for idx, n in enumerate(nums):
                if target - n in seen:
                    res = [seen[target - n], idx]
                    break
                seen[n] = idx
            tests.append(((nums, target), res))
        return tests

class AlgoRomanToInt(CodeAlgorithm):
    def __init__(self):
        super().__init__(
            "roman_to_int",
            "Convert a standard Roman numeral string to an integer.",
            "def roman_to_int(s):"
        )
    def generate_tests(self, seed: int) -> list[tuple[Any, Any]]:
        numerals = [
            ("III", 3),
            ("IV", 4),
            ("IX", 9),
            ("LVIII", 58),
            ("MCMXCIV", 1994)
        ]
        return [(((rom,), val)) for rom, val in numerals]

class AlgoMovingAverage(CodeAlgorithm):
    def __init__(self):
        super().__init__(
            "moving_average",
            "Return moving average of nums with window size w, rounded to 2 decimal places.",
            "def moving_average(nums, w):"
        )
    def generate_tests(self, seed: int) -> list[tuple[Any, Any]]:
        rng = random.Random(seed)
        tests = []
        for _ in range(5):
            nums = [rng.randint(1, 50) for _ in range(8)]
            w = rng.randint(2, 4)
            res = []
            for i in range(len(nums) - w + 1):
                res.append(round(sum(nums[i:i+w]) / w, 2))
            tests.append(((nums, w), res))
        return tests

class AlgoDedupe(CodeAlgorithm):
    def __init__(self):
        super().__init__(
            "deduplicate_preserve_order",
            "Remove duplicates from nums while preserving first appearance order.",
            "def deduplicate_preserve_order(nums):"
        )
    def generate_tests(self, seed: int) -> list[tuple[Any, Any]]:
        rng = random.Random(seed)
        tests = []
        for _ in range(5):
            nums = [rng.randint(1, 6) for _ in range(12)]
            seen = set()
            exp = []
            for x in nums:
                if x not in seen:
                    seen.add(x)
                    exp.append(x)
            tests.append(((nums,), exp))
        return tests

class AlgoGroupAnagrams(CodeAlgorithm):
    def __init__(self):
        super().__init__(
            "group_anagrams",
            "Group anagrams together from a list of lowercase words. Output is list of lists, with groups sorted internally and groups ordered by first word.",
            "def group_anagrams(words):"
        )
    def generate_tests(self, seed: int) -> list[tuple[Any, Any]]:
        tests = [
            ((["eat", "tea", "tan", "ate", "nat", "bat"],), [["ate", "eat", "tea"], ["bat"], ["nat", "tan"]]),
            ((["a"],), [["a"]]),
            (([""],), [[""]]),
            ((["ab", "ba", "abc", "bca", "cab"],), [["ab", "ba"], ["abc", "bca", "cab"]]),
            ((["cat", "dog", "god", "act"],), [["act", "cat"], ["dog", "god"]])
        ]
        return tests

algorithms: list[CodeAlgorithm] = [
    AlgoKMostFreq(),
    AlgoRunLength(),
    AlgoSecondLargest(),
    AlgoBalancedBrackets(),
    AlgoMergeIntervals(),
    AlgoRotateList(),
    AlgoFlatten(),
    AlgoTwoSum(),
    AlgoRomanToInt(),
    AlgoMovingAverage(),
    AlgoDedupe(),
    AlgoGroupAnagrams()
]

def extract_code(text: str) -> str:
    parts = text.split("```python")
    if len(parts) > 1:
        return parts[1].split("```")[0].strip()
    parts = text.split("```")
    if len(parts) > 1:
        return parts[1].strip()
    return text.strip()

def run_code_item(algo: CodeAlgorithm, seed: int, item_id: str, client, hint=None) -> ItemResult:
    prompt = f"Implement the following algorithm in Python:\nTask: {algo.task}\nSignature: {algo.signature}\nProvide only the Python function code."
    start = time.perf_counter()
    resp = client.chat([{"role": "user", "content": prompt}], hint={"domain": "code", "item_id": item_id})
    lat = time.perf_counter() - start
    
    if getattr(resp, "truncated", False):
        return ItemResult("code_generation", item_id, 0.0, False, FailureLabel.BAD_FORMAT.value, "truncated at max_tokens", lat)
    
    code = extract_code(resp.text)
    
    try:
        ast.parse(code)
    except SyntaxError:
        return ItemResult("code_generation", item_id, 0.0, False, FailureLabel.SYNTAX_FAIL.value, "Syntax Error", lat)
        
    tests = algo.generate_tests(seed)
    test_calls = []
    for i, (args, expected) in enumerate(tests):
        if isinstance(args, tuple):
            args_repr = ", ".join(repr(a) for a in args)
        else:
            args_repr = repr(args)
        test_calls.append(f"    res_{i} = {algo.name}({args_repr})")
    
    res_list = ", ".join(f"res_{i}" for i in range(len(tests)))
    
    full_code = f"""
import json

{code}

def run_tests():
{chr(10).join(test_calls)}
    print(json.dumps([{res_list}]))

if __name__ == '__main__':
    run_tests()
"""
    sandbox_res = run_in_sandbox(full_code)
    if "error" in sandbox_res:
        label = FailureLabel.SANDBOX_TIMEOUT.value if sandbox_res["error"] == "timeout" else FailureLabel.CLIENT_ERROR.value
        return ItemResult("code_generation", item_id, 0.0, False, label, sandbox_res["error"], lat)
        
    results = sandbox_res.get("result", [])
    correct = 0
    for i, (_, expected) in enumerate(tests):
        if i < len(results) and results[i] == expected:
            correct += 1
            
    score = correct / len(tests) if tests else 1.0
    passed = (score == 1.0)
    label = None if passed else "INCORRECT_RESULT"
    return ItemResult("code_generation", item_id, score, passed, label, f"Passed {correct}/{len(tests)}", lat)

def run_domain_code(client, seed: int, items_count: int) -> list[ItemResult]:
    results = []
    for i in range(items_count):
        algo = algorithms[i % len(algorithms)]
        item_seed = stable_seed(seed, "code", i)
        results.append(run_code_item(algo, item_seed, f"C-{i}", client))
    return results
