"""
mini-tester —— 一个最小的 LLM 单元测试生成 Agent

它做的事（对应 AgentTester, ICIC 2025 里最核心的那个循环）：

    1. 把被测函数代码交给大模型，让它生成 pytest 测试
    2. 写临时文件，跑一遍 pytest
    3. 如果失败，把「报错信息 + 原代码」回喂给模型，让它修
    4. 最多两轮

为什么做这个：
    读完 AgentTester 之后想亲手跑一遍它的 Validation-Repair 循环，
    看它到底会在哪儿失败 —— 结论写在 README 的「我的观察」一节。

跑法：
    # 只验证链路，不调用模型（30 秒）
    python mini_tester.py --demo

    # 真流程
    pip install -r requirements.txt
    $env:DEEPSEEK_API_KEY = "你的key"      # PowerShell
    python mini_tester.py

换模型：改下面的 MODEL 和 BASE_URL（任何兼容 OpenAI 接口的服务都行）。
"""

import os
import re
import subprocess
import tempfile

from openai import OpenAI

# ---------------------------------------------------------------------------
# 0. 配置
#    - 默认用 DeepSeek，key 从环境变量 DEEPSEEK_API_KEY 读
#    - 想换模型就改 BASE_URL 和 MODEL
# ---------------------------------------------------------------------------
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"

_client = None


def get_client() -> OpenAI:
    """延迟创建客户端：没配 key 时不报错，只有真正调用模型时才报错。"""
    global _client
    if _client is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise SystemExit(
                "没有找到 API key。请先设置环境变量再运行：\n"
                '  PowerShell:  $env:DEEPSEEK_API_KEY = "你的key"\n'
                '  macOS/Linux: export DEEPSEEK_API_KEY="你的key"\n'
                "（DeepSeek key 在 https://platform.deepseek.com 申请，几块钱能用很久）"
            )
        _client = OpenAI(api_key=api_key, base_url=BASE_URL)
    return _client


# ---------------------------------------------------------------------------
# 1. 被测函数：真实项目里这些来自你的代码库，这里手写几个做实验
#    故意留了一个"有 bug"的函数：divide 没处理除零，看模型能不能测出来
# ---------------------------------------------------------------------------
TARGET_CODE = '''
def add(a, b):
    return a + b

def divide(a, b):
    return a / b

def is_even(n):
    return n % 2 == 0

def max_of_three(a, b, c):
    if a >= b and a >= c:
        return a
    if b >= a and b >= c:
        return b
    return c
'''


# ---------------------------------------------------------------------------
# 2. 让模型生成测试
# ---------------------------------------------------------------------------
def generate_tests(code: str, feedback: str = "") -> str:
    """输入被测代码，返回一段 pytest 测试代码。feedback 用于第二轮修复。"""
    prompt = f"""你是一个 Python 测试工程师。请为下面的代码写 pytest 单元测试。

要求：
- 只输出 Python 代码，用 ```python 包裹
- 每个函数至少 2 个测试：一个正常情况，一个边界情况
- 不要导入被测代码以外的任何东西（被测函数已经在测试文件里定义了）
- 测试文件名无关，函数名以 test_ 开头

待测代码：
{code}
"""
    if feedback:
        prompt += f"""
上一轮生成的测试运行失败了，报错如下：
{feedback}

请修复测试代码。注意：**先判断是测试写错了，还是被测代码本身有 bug**。
如果是被测代码的 bug，不要改被测代码，而是写一个能暴露它的测试。
"""

    resp = get_client().chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return resp.choices[0].message.content


# ---------------------------------------------------------------------------
# 3. 从模型回复里抠出代码块
# ---------------------------------------------------------------------------
def extract_code(text: str) -> str:
    match = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


# ---------------------------------------------------------------------------
# 4. 跑测试，返回 (是否通过, 输出)
# ---------------------------------------------------------------------------
def run_pytest(test_code: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test_generated.py")
        # 把被测代码 + 测试拼在一起，避免导入问题
        with open(path, "w", encoding="utf-8") as f:
            f.write(TARGET_CODE + "\n\n" + test_code)

        result = subprocess.run(
            ["pytest", path, "-q", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=tmp,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, output


# ---------------------------------------------------------------------------
# 5. 主循环：生成 → 跑 → 失败则带着报错重生成 → 最多 2 轮
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("mini_tester：LLM 生成单元测试 Agent（最小版）")
    print("=" * 60)

    feedback = ""
    passed = False
    test_code = ""

    for round_no in range(1, 3):
        print(f"\n--- 第 {round_no} 轮：生成测试 ---")
        raw = generate_tests(TARGET_CODE, feedback)
        test_code = extract_code(raw)

        print("生成的测试代码：")
        print(test_code[:600])

        passed, output = run_pytest(test_code)
        print(f"\n结果：{'✅ 全部通过' if passed else '❌ 有失败'}")
        print(output[-800:])

        if passed:
            break
        feedback = output  # 把报错回喂给模型

    print("\n" + "=" * 60)
    print(f"最终结论：{'测试通过' if passed else '两轮后仍有失败'}")
    print("你可以改的东西：")
    print("  1. TARGET_CODE 换成更难/更真实的函数")
    print("  2. 把轮数从 2 改成 3，看会不会收敛")
    print("  3. 把 MODEL 换成别的模型，对比通过率")
    print("=" * 60)


DEMO_TESTS = """\
def test_add():
    assert add(1, 2) == 3
    assert add(-1, 1) == 0

def test_divide():
    assert divide(6, 3) == 2
    assert divide(1, 0) == 0  # ← 故意写错：divide 没处理除零，这个测试会失败

def test_is_even():
    assert is_even(4) is True
    assert is_even(3) is False

def test_max_of_three():
    assert max_of_three(1, 5, 3) == 5
    assert max_of_three(2, 2, 2) == 2
"""


def demo():
    """不调用模型，直接用手写的测试跑一遍 pipeline。
    用途：先验证"跑测试"这一段是通的，再去配 API key。"""
    print("=" * 60)
    print("DEMO 模式：不调用大模型，只验证 pytest 执行链路")
    print("=" * 60)
    passed, output = run_pytest(DEMO_TESTS)
    print(f"结果：{'✅ 全部通过' if passed else '❌ 有失败（这是预期的，看下面）'}")
    print(output)
    print("=" * 60)
    print("这段输出说明了什么：")
    print("  - divide(1,0) 让测试失败了 → 暴露了被测代码的真实 bug")
    print("  - 真实场景里，模型看到这个报错后会被要求'判断是测试错还是代码错'")
    print("  - 这就是 AgentTester 那类论文的核心循环：生成 → 执行 → 反馈 → 修复")
    print("=" * 60)


if __name__ == "__main__":
    import sys

    if "--demo" in sys.argv:
        demo()
    else:
        main()
