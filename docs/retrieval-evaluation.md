# 检索评估实验

本实验使用固定问题集，对关键词、向量和混合检索做可重复评估。指标基于样例文档中的人工标注短语（gold phrase），不是由 LLM 自动判断。

## 准备

1. 在项目根目录启动后端：`cd backend && uvicorn app.main:app --reload`。
2. 上传 `samples/employee-handbook.md`。
3. 如果要评估 vector/hybrid，请配置 Embedding API 后重新上传样例文档，并确认 embedded chunk count 大于 0。
4. 确保 API 地址可从运行脚本的环境访问。

## 运行

从仓库根目录执行：

```bash
cd backend
python scripts/evaluate_retrieval.py
```

可选参数：

```bash
python scripts/evaluate_retrieval.py --base-url http://localhost:8000 --k 5
python scripts/evaluate_retrieval.py --modes keyword hybrid
python scripts/evaluate_retrieval.py --output evaluation/report.json
```

默认评估 keyword、vector、hybrid 三种模式。若 vector API 不可用，脚本会标记该模式不可评估，不会把关键词回退结果误记为向量结果。

## 指标

- **Recall@5**：每道题只有一个标注相关片段；该片段出现在前 5 条则记为 1，否则为 0。最终取所有问题的平均值。
- **MRR**（Mean Reciprocal Rank）：找到首个标注相关片段的排名倒数，未命中记为 0，再对问题取平均。
- 报告同时保留每道题的有效模式、首个结果和 gold rank，方便定位失败案例。

## 标注边界与局限

- 数据集位于 `backend/evaluation/retrieval_dataset.json`。每道题的 `gold_phrase` 必须真实存在于正确的知识片段中。
- 当前每题只标注一个相关片段，因此 Recall@5 是单相关片段召回率，不代表完整企业语料上的全面召回率。
- 这是一个小型演示集，指标只适合比较本项目当前样例和参数；不能据此宣称生产级准确率。
- 评估前不要改变样例文档或分块参数；如有变化，应重新检查 gold phrase 是否仍落在正确 chunk，并记录数据集版本。
- Reranker 应在固定数据集上比较重排前后的 MRR/Recall@5，而不是只凭主观观感判断效果。
