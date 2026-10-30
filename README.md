# mini-tester

一个最小的 **LLM 单元测试生成 Agent**：让大模型为 Python 函数生成 [pytest](https://docs.pytest.org/) 测试，跑一遍，把失败信息回喂给模型让它修，最多两轮。

> 这是我在读 **AgentTester**（ICIC 2025）之后做的学习项目。用一个约 180 行的最小实现，
> 复现它最核心的那个循环：**生成 → 执行 → 读报错 → 再生成 / 修复**。

---

## 为什么要做这个

AgentTester 有三个组件：AutoPrompting、Prompt Distillation、Validation-Repair。

其中真正让我想动手试的是第三个 —— **Validation-Repair**。它本质上就是一个 Agent 循环：

> 模型写测试 → 编译 → 跑 → 把报错喂回去 → 模型改 → 再跑

论文只给了结论（行覆盖率超过 EvoSuite，编译率和正确性超过 AthenaTest / ChatTester），
**但我想自己跑一遍，看它到底会在哪里失败。**

---

## 它做什么

```
              ┌──────────────────┐
              │    被测函数代码    │
              └────────┬─────────┘
                       ▼
         ┌─────────────────────────────┐
         │ 1. 生成测试（调用大模型）      │
         │    输入：代码 + 生成要求       │
         └──────────────┬──────────────┘
                        ▼
         ┌─────────────────────────────┐
         │ 2. 写临时文件，跑 pytest      │
         └───────┬─────────────┬───────┘
            通过  │             │ 失败
                 ▼             ▼
              ┌──────┐   ┌──────────────────────┐
              │ 结束  │   │ 3. 把报错回喂给模型    │
              └──────┘   │    （带上原代码）      │
                         └──────────┬───────────┘
                                    │
                                    └──▶ 回到 1（最多 2 轮）
```

---

## 怎么跑

### 方式一：Demo 模式（**不需要 API key**，30 秒）

```bash
python mini_tester.py --demo
```

它不调用任何模型，只验证「拼代码 → 跑 pytest → 读结果」这条链路是通的。
用的是内置的一份**故意写错的测试**，所以你会看到一个**预期内**的失败：

```
============================================================
DEMO 模式：不调用大模型，只验证 pytest 执行链路
============================================================
结果：❌ 有失败（这是预期的，看下面）
.F..                                                                     [100%]
================================== FAILURES ===================================
_________________________________ test_divide _________________________________
test_generated.py:25: in test_divide
    assert divide(1, 0) == 0
           ^^^^^^^^^^^^
test_generated.py:6: in divide
    return a / b
E   ZeroDivisionError: division by zero
=========================== short test summary info ============================
FAILED test_generated.py::test_divide - ZeroDivisionError: division by zero
1 failed, 3 passed in 0.12s
```

> 完整输出见 [`results/demo-output.txt`](results/demo-output.txt)。

### 方式二：真流程（需要 API key）

```bash
pip install -r requirements.txt
```

PowerShell：

```powershell
$env:DEEPSEEK_API_KEY = "sk-你的key"
python mini_tester.py
```

macOS / Linux：

```bash
export DEEPSEEK_API_KEY="sk-你的key"
python mini_tester.py
```

默认用 DeepSeek（`https://api.deepseek.com`，模型 `deepseek-chat`）。
换别的模型，改 `mini_tester.py` 顶部的 `MODEL` 和 `BASE_URL` 即可（任何兼容 OpenAI 接口的服务都行）。

---

## 我的观察

跑完之后最直接的一个感受是：

> **模型分不清「测试写错了」还是「被测代码有 bug」。**

上面 demo 里那个失败就是典型的例子：

- 可能是**测试写错了** —— `divide` 本来就该在除零时抛异常，我却断言它等于 0
- 也可能是**代码有 bug** —— `divide` 根本没处理除零，这本身就该修

真实跑真流程的时候（把报错回喂给模型），我看到的是：**模型更愿意改测试让它通过，而不是暴露代码的真实缺陷。**

这正好对上 TOSEM 2025 那篇系统综述（105 篇论文）指出的核心挑战：

> *"A crucial challenge lies in the issue of false positives, i.e., determining whether a failing test case is caused by its assertion error or by an actual bug in the program."*

同一篇综述里还有个数字挺说明问题的：**只有 8 / 105 篇论文真正去测了「生成的测试能不能发现真实缺陷」**，绝大多数只测覆盖率、通过率、编译率。

所以我现在的判断是：**这类工作里，「怎么判断测试失败的原因」比「怎么生成测试」更关键。**

---

## 局限（说清楚，别夸大）

- 只跑 **2 轮** 修复，没有调参、没有多温度采样
- 只支持 **Python**，被测函数只有 4 个（内置在 `TARGET_CODE` 里）
- **没有统计覆盖率**（没接 `coverage.py` / `pytest-cov`）
- **没有和其他工具做基线对比**（没有 EvoSuite / ChatTester 那种对比）
- 不是 AgentTester 的复现 —— 只是把它最核心的循环抽出来做了个最小版

---

## 下一步想做的

- [ ] 换成 10 个**带已知 bug** 的函数，统计「测试失败中有多少是真 bug、多少是测试自己写错」
- [ ] 接 `pytest-cov`，看每一轮的覆盖率变化（轮次 → 覆盖率曲线）
- [ ] 对比不同模型的生成质量

---

## 关于这个项目

代码是在和 AI 协作下完成的。我负责的部分是：**设计实验、跑通链路、记录观察并得出结论** ——
所以这份 README 里最有价值的不是代码，是上面「我的观察」那一节。

如果是想找「180 行手写代码」的证据，这个仓库不合适；如果是想看「怎么把一篇论文的核心机制拆成一个能跑的最小实验」，那它大概对了。

---

## 参考

- **AgentTester: An LLM-Based Tool for Unit Test Generation with Automatically Generated Prompts** — Honghui Chen, Kaiqing Chen, Fanlong Zhang, Tao Wang, Lianglun Cheng. ICIC 2025, CCIS vol.2574, pp.114-126. [DOI](https://doi.org/10.1007/978-981-95-0011-6_10)
- **Large Language Models for Unit Testing: A Systematic Literature Review** — arXiv:[2506.15227](https://arxiv.org/abs/2506.15227)
- [AwesomeLLM4UT](https://github.com/iSEngLab/AwesomeLLM4UT) — 这个方向的论文合集

---

## License

[MIT](LICENSE)
