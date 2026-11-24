import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { readSSEStream } from "./services/stream";
import ChatMessage from "./components/chat/ChatMessage";
import ModelSettings, { type ModelSettingsValue } from "./components/settings/ModelSettings";
import { apiFetch, ensureSession } from "./services/api";
import { Bot, FileText, ShieldCheck, Sparkles, Upload, CheckCircle2, Loader2, AlertCircle, Search, Send, BookOpen, Settings } from "lucide-react";

type KnowledgeDocument = {
  id: string; filename: string; size: number; status: string;
  character_count: number; chunk_count: number; embedded_chunk_count: number;
};
type SearchResult = {
  chunk_id: string; document_id: string; filename: string;
  chunk_index: number; content: string; score: number;
  keyword_rank?: number; vector_rank?: number; rerank_score?: number;
};
type ChatSource = {
  id: number; chunk_id: string; document_id: string; filename: string;
  chunk_index: number; content: string; score?: number; rerank_score?: number;
};
type SearchMode = "keyword" | "vector" | "hybrid";
type ComparisonResult = {
  mode: SearchMode; results: SearchResult[]; error?: string; fallback?: string;
  reranker?: string; rerankerError?: string;
};
const formatSize = (size: number) => size < 1024 * 1024 ? (size / 1024).toFixed(1) + " KB" : (size / 1024 / 1024).toFixed(1) + " MB";
const modeTitle: Record<SearchMode, string> = { keyword: "关键词检索", vector: "向量语义检索", hybrid: "混合检索" };
const modeSubtitle: Record<SearchMode, string> = { keyword: "Keyword Search", vector: "Vector Search", hybrid: "Hybrid · RRF" };

export default function App() {
  const [health, setHealth] = useState<"checking" | "ok" | "error">("checking");
  const [activeSection, setActiveSection] = useState<"chat" | "documents">("chat");
  const [showModelSettings, setShowModelSettings] = useState(false);
  const [modelSettings, setModelSettings] = useState<ModelSettingsValue>({ api_key: "", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-max" });
  const [modelTesting, setModelTesting] = useState(false);
  const [modelStatus, setModelStatus] = useState("");
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  const [searching, setSearching] = useState(false);
  const [rerankEnabled, setRerankEnabled] = useState(false);
  const [query, setQuery] = useState("");
  const [comparison, setComparison] = useState<ComparisonResult[]>([]);
  const [chatAnswer, setChatAnswer] = useState("");
  const [chatSources, setChatSources] = useState<ChatSource[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatStatus, setChatStatus] = useState<"idle" | "connecting" | "streaming" | "completed" | "error" | "cancelled">("idle");
  const [chatError, setChatError] = useState("");
  const [expandedSources, setExpandedSources] = useState<number[]>([]);
  const [highlightedSourceId, setHighlightedSourceId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const chatAbortRef = useRef<AbortController | null>(null);

  const loadDocuments = async () => {
    const response = await apiFetch("/documents");
    if (!response.ok) throw new Error("无法加载文档列表");
    setDocuments(await response.json() as KnowledgeDocument[]);
  };

  useEffect(() => {
    ensureSession().then(() => apiFetch("/health")).then((response) => {
      if (!response.ok) throw new Error("API unavailable");
      setHealth("ok");
      return loadDocuments();
    }).catch(() => setHealth("error"));
    return () => chatAbortRef.current?.abort();
  }, []);

  const handleReindex = async () => {
    setReindexing(true); setMessage(""); setError("");
    try {
      const response = await apiFetch("/documents/reindex", { method: "POST" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "重新生成向量失败");
      await loadDocuments();
      const summary = "向量索引完成：" + result.indexed_documents + "/" + result.total_documents + " 份文档成功";
      const failures = (result.failed || []).map((item: { filename: string; error: string }) => item.filename + "：" + item.error).join("；");
      setMessage(failures ? summary + "；失败：" + failures : summary);
    } catch (reindexError) {
      setError(reindexError instanceof Error ? reindexError.message : "重新生成向量失败，请重试。");
    } finally {
      setReindexing(false);
    }
  };

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true); setMessage(""); setError("");
    const body = new FormData(); body.append("file", file);
    try {
      const response = await apiFetch("/documents", { method: "POST", body });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "上传失败");
      setMessage("已完成解析与分块：" + result.filename + "，共 " + result.chunk_count + " 个文本块；向量状态：" + (result.embedding_status === "indexed" ? "已建立" : "待配置 Embedding API"));
      await loadDocuments();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "上传失败，请重试。");
    } finally { setUploading(false); event.target.value = ""; }
  };

  const handleSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!query.trim()) return;
    setSearching(true); setError(""); setComparison([]);
    const modes: SearchMode[] = ["keyword", "vector", "hybrid"];
    const outcomes = await Promise.all(modes.map(async (mode): Promise<ComparisonResult> => {
      try {
        const response = await apiFetch("/search", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: query.trim(), limit: 5, mode, rerank: mode === "hybrid" && rerankEnabled }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "检索失败");
        return {
          mode, results: result.results as SearchResult[],
          fallback: result.mode === "keyword_fallback" ? result.fallback_reason : undefined,
          reranker: result.reranker, rerankerError: result.reranker_error,
        };
      } catch (searchError) {
        return { mode, results: [], error: searchError instanceof Error ? searchError.message : "检索失败，请重试。" };
      }
    }));
    setComparison(outcomes);
    setSearching(false);
  };

  const handleChat = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const question = query.trim();
    if (!question || chatLoading) return;

    chatAbortRef.current?.abort();
    const controller = new AbortController();
    chatAbortRef.current = controller;
    setChatLoading(true);
    setChatStatus("connecting");
    setChatError("");
    setChatAnswer("");
    setChatSources([]);
    setExpandedSources([]);
    setHighlightedSourceId(null);

    try {
      const response = await apiFetch("/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: question, limit: 5, rerank: rerankEnabled, model_settings: modelSettings.api_key.trim() ? modelSettings : undefined }),
        signal: controller.signal,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "问答请求失败");
      }
      if (!response.body) throw new Error("浏览器不支持流式响应");

      let receivedDone = false;
      for await (const message of readSSEStream(response.body)) {
        if (message.event === "sources") {
          const payload = JSON.parse(message.data);
          setChatSources(payload.sources || []);
          setChatStatus("streaming");
        } else if (message.event === "token") {
          const payload = JSON.parse(message.data);
          setChatAnswer((current) => current + (payload.content || ""));
          setChatStatus("streaming");
        } else if (message.event === "error") {
          const payload = JSON.parse(message.data);
          throw new Error(payload.message || "生成失败");
        } else if (message.event === "done") {
          receivedDone = true;
          setChatStatus("completed");
        }
      }

      if (!receivedDone) throw new Error("流式响应意外结束，请重试。");
    } catch (chatException) {
      if (chatException instanceof Error && chatException.name === "AbortError") {
        setChatStatus("cancelled");
        return;
      }
      setChatStatus("error");
      setChatError(chatException instanceof Error ? chatException.message : "问答失败，请重试。");
    } finally {
      if (chatAbortRef.current === controller) {
        chatAbortRef.current = null;
        setChatLoading(false);
      }
    }
  };

  const handleTestModel = async (config: ModelSettingsValue) => {
    setModelTesting(true); setModelStatus("");
    try {
      const response = await apiFetch("/model/test", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "模型连接失败");
      setModelStatus(result.message || "模型连接成功");
    } catch (testError) {
      setModelStatus(testError instanceof Error ? testError.message : "模型连接失败");
    } finally { setModelTesting(false); }
  };

  const navigateToSection = (section: "chat" | "documents") => {
    setActiveSection(section);
    document.getElementById(section === "chat" ? "chat-section" : "documents-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const toggleSource = (id: number) => setExpandedSources((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);

  const handleCitationClick = (id: number) => {
    if (!chatSources.some((source) => source.id === id)) return;
    setExpandedSources((current) => current.includes(id) ? current : [...current, id]);
    setHighlightedSourceId(id);
    document.getElementById(`source-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  useEffect(() => {
    if (highlightedSourceId === null) return;
    document.getElementById(`source-${highlightedSourceId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightedSourceId, chatSources]);

  const renderResults = (item: ComparisonResult) => <div className="comparison-column" key={item.mode}>
    <div className="comparison-heading"><div><strong>{modeTitle[item.mode]}</strong><span>{modeSubtitle[item.mode]}</span></div><span className="result-count">{item.error ? "不可用" : item.results.length + " 条结果"}</span></div>
    {item.error ? <div className="comparison-error"><AlertCircle size={15} /><span>{item.error}</span></div> : <>
      {item.fallback && <div className="comparison-fallback">{item.fallback}</div>}
      {item.mode === "hybrid" && item.reranker === "applied" && <div className="comparison-success">已启用 Cross-Encoder 重排序</div>}
      {item.mode === "hybrid" && item.reranker === "unavailable" && <div className="comparison-fallback">{item.rerankerError}</div>}
      {item.mode === "hybrid" && item.reranker === "failed_fallback" && <div className="comparison-fallback">重排序服务调用失败，已回退到 RRF 排名：{item.rerankerError}</div>}
      {item.results.length === 0 ? <div className="empty-state compact">没有找到匹配片段</div> :
        <div className="result-list">{item.results.map((result, index) => <article className="result-card" key={result.chunk_id}>
          <div className="result-top"><strong>#{index + 1} · {result.filename}</strong><span>片段 #{result.chunk_index + 1} · {item.mode === "hybrid" ? (item.reranker === "applied" ? "Rerank " : "RRF ") : "分数 "}{(item.mode === "hybrid" && item.reranker === "applied" ? result.rerank_score ?? result.score : result.score).toFixed(4)}</span></div>
          {item.mode === "hybrid" && <div className="rank-meta">关键词排名：{result.keyword_rank ?? "—"} · 向量排名：{result.vector_rank ?? "—"}{item.reranker === "applied" ? " · 已重排序" : ""}</div>}
          <p>{result.content}</p>
        </article>)}</div>}
    </>}
  </div>;

  return <main className="shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><Bot size={21} /></span><span>KnowFlow</span></div>
      <div className="workspace-label">工作空间</div>
      <button className={`nav-item${activeSection === "chat" ? " active" : ""}`} onClick={() => navigateToSection("chat")}><Sparkles size={17} /> 智能问答</button>
      <button className={`nav-item${activeSection === "documents" ? " active" : ""}`} onClick={() => navigateToSection("documents")}><FileText size={17} /> 知识库</button>
      <div className="sidebar-bottom"><div className={"status-dot " + (health === "ok" ? "online" : "")} /><span>API {health === "ok" ? "运行正常" : health === "error" ? "连接失败" : "检查中"}</span></div>
    </aside>
    <section className="main-panel">
      <header className="topbar"><div><span className="eyebrow">ENTERPRISE KNOWLEDGE</span><h1>企业知识助手</h1></div><div className="topbar-actions"><button className="settings-trigger" onClick={() => setShowModelSettings(current => !current)}><Settings size={15} /> 模型设置</button><div className="secure"><ShieldCheck size={16} /> 独立临时知识库</div></div></header>
      {showModelSettings && <ModelSettings value={modelSettings} onSave={(value) => { setModelSettings(value); setModelStatus("配置已保存在当前页面内存中。刷新后需要重新输入 API Key。"); }} onClear={() => { setModelSettings({ api_key: "", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-max" }); setModelStatus("模型配置已清除。"); }} onTest={handleTestModel} testing={modelTesting} status={modelStatus} />}
      <section className="welcome">
        <div className="welcome-icon"><Sparkles size={22} /></div>
        <p className="eyebrow">YOUR KNOWLEDGE, CONNECTED</p>
        <h2>让企业知识，随问随答</h2>
        <p className="subtitle">上传企业文档，系统自动提取文本、切分知识片段，并支持多策略检索与带来源引用的 AI 问答。</p>
        <input ref={inputRef} className="hidden-input" type="file" accept=".pdf,.docx,.txt,.md" onChange={handleUpload} />
        <button className="upload-box" onClick={() => inputRef.current?.click()} disabled={uploading}>
          {uploading ? <Loader2 className="spin" size={20} /> : <Upload size={20} />}
          <span>{uploading ? "正在上传、解析与分块…" : "选择文件，上传到知识库"}</span>
          <small>支持 PDF、DOCX、TXT、Markdown，单个文件最大 10 MB</small>
        </button>
        {message && <div className="notice success"><CheckCircle2 size={16} />{message}</div>}
        {error && <div className="notice error"><AlertCircle size={16} />{error}</div>}
      </section>

      <section id="chat-section" className="chat-section">
        <div className="section-heading"><div><h3><BookOpen size={16} /> 知识库问答</h3><p>Hybrid Retrieval → 可选 Reranker → LLM，答案通过 SSE 实时生成</p></div></div>
        <form className="search-form" onSubmit={handleChat}>
          <Search size={18} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="向知识库提问，例如：员工年假有多少天？" />
          <button type="submit" disabled={chatLoading || !query.trim()}>{chatLoading ? <><Loader2 className="spin" size={14} /> 生成中</> : <><Send size={14} /> 提问</>}</button>
        </form>
        {chatLoading && <div className="chat-streaming">{chatStatus === "connecting" ? "正在连接问答服务…" : "正在检索资料并生成回答…"}</div>}
        {chatError && <div className="comparison-error"><AlertCircle size={15} />{chatError}</div>}
        {chatAnswer && <article className="answer-card"><div className="answer-heading"><Sparkles size={16} /> AI 回答</div><ChatMessage content={chatAnswer} sourceIds={chatSources.map((source) => source.id)} onCitationClick={handleCitationClick} /></article>}
        {chatSources.length > 0 && <div className="source-panel"><strong><BookOpen size={15} /> 参考来源（{chatSources.length}）</strong>
          {chatSources.map((source) => <article id={`source-${source.id}`} className={`source-item${highlightedSourceId === source.id ? " source-item-highlighted" : ""}`} key={source.id}>
            <button type="button" onClick={() => toggleSource(source.id)}><span>[{source.id}] {source.filename} · 片段 #{source.chunk_index + 1}</span><span>{expandedSources.includes(source.id) ? "收起" : "查看依据"}</span></button>
            {expandedSources.includes(source.id) && <p>{source.content}</p>}
          </article>)}
        </div>}
      </section>

      <section className="search-section">
        <div className="section-heading"><div><h3>三种检索策略对比</h3><p>相同问题并行检索：关键词、向量语义，以及 RRF 融合后的混合排名</p></div></div>
        <form className="search-form" onSubmit={handleSearch}>
          <Search size={18} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="例如：出差回来后，多久之内要交票据？" />
          <button type="submit" disabled={searching || !query.trim()}>{searching ? "对比中…" : "同时检索"}</button>
        </form>
        <label className="rerank-toggle"><input type="checkbox" checked={rerankEnabled} onChange={(event) => setRerankEnabled(event.target.checked)} /> 对混合检索结果启用 Reranker（需配置独立 API）</label>
        {comparison.length > 0 && <div className="comparison-grid">{comparison.map(renderResults)}</div>}
        {comparison.length === 0 && <p className="comparison-hint">向量和混合检索需要先配置 Embedding API，并上传已生成向量的文档；否则混合检索会明确降级为关键词检索。</p>}
      </section>

      <section id="documents-section" className="documents-section">
        <div className="section-heading"><div><h3>知识库文档</h3><p>已上传并完成文本提取的资料</p></div><div><span className="count">{documents.length} 个文件</span> <button type="button" onClick={handleReindex} disabled={reindexing || documents.length === 0}>{reindexing ? "正在生成向量…" : "重新生成向量"}</button></div></div>
        {documents.length === 0 ? <div className="empty-state"><FileText size={23} /><span>还没有文档，上传一份资料开始构建知识库</span></div> :
          <div className="document-list">{documents.map((document) => <article className="document-row" key={document.id}>
            <div className="file-icon"><FileText size={19} /></div>
            <div className="file-info"><strong>{document.filename}</strong><span>{formatSize(document.size)} · {document.character_count.toLocaleString()} 字符 · {document.chunk_count} 个片段 · {document.embedded_chunk_count} 个向量</span></div>
            <span className="ready"><CheckCircle2 size={14} /> {document.embedded_chunk_count > 0 ? "向量已索引" : "文本已分块"}</span>
          </article>)}</div>}
      </section>
      <footer className="page-footer"><ShieldCheck size={14} /> 混合检索使用 Reciprocal Rank Fusion；问答答案应以展开的来源片段为依据。</footer>
    </section>
  </main>;
}
