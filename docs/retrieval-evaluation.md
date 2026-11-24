# 检索评估实验

本实验使用员工手册样例文档和固定标注问题集，对关键词、向量、混合检索做可重复评估。当前数据集包含 35 道问题，覆盖精确政策问法、同义改写和口语表达。每道题标注一个人工确认的 gold phrase 与问题类别。

## 准备

1. 在项目根目录启动后端：`cd backend && uvicorn app.main:app --reload`。
2. 上传仓库中的 `samples/employee-handbook.md`。
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
python scripts/evaluate_retrieval.py --compare-reranker --output evaluation/report.json
```

脚本会先调用 `POST /session` 创建专用评估 Session，再使用返回的 `X-Session-Token` 调用受保护的 `POST /search`。不会读取其他 Session 的文档。Session 按服务端现有 TTL 过期清理；当前没有单独删除 Session 的公开接口。

默认评估 keyword、vector、hybrid 三种模式。若 vector 或 hybrid 不可用，报告会明确标记为 unavailable，不会把关键词回退结果误记为向量/混合检索结果。

使用 `--compare-reranker` 时，会在同一问题集上额外运行一次启用 reranker 的 hybrid 检索，并与未重排结果比较。需要配置 `RERANK_API_KEY`；未实际应用 reranker 时不会生成虚假的前后对比。

## 指标

- **Recall@1 / Recall@3 / Recall@5**：每道题只有一个标注相关片段；该片段出现在对应前 K 条则记为 1，否则为 0。最终取所有问题的平均值。
- **MRR**（Mean Reciprocal Rank）：找到首个标注相关片段的排名倒数，未命中记为 0，再对问题取平均。
- 报告保留每道题的问题类别、有效模式、首个结果和 gold rank，方便定位失败案例。

## 标注边界与局限

- 数据集位于 `backend/evaluation/retrieval_dataset.json`。每道题的 `gold_phrase` 必须真实存在于正确的知识片段中；本数据集的标注短语来自 `samples/employee-handbook.md`。
- 当前每题只标注一个相关片段，因此 Recall@K 是单相关片段召回率，不代表完整企业语料上的全面召回率。
- 35 道题均围绕一个演示员工手册的 7 个事实点展开，适合回归比较，不代表跨行业或真实企业语料的总体检索准确率。
- 这是固定演示集，指标只适合比较本项目当前样例和参数；不能据此宣称生产级准确率。
- 评估前不要改变样例文档或分块参数；如有变化，应重新检查 gold phrase 是否仍落在正确 chunk，并记录数据集版本。
