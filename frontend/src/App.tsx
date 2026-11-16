import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { Bot, FileText, ShieldCheck, Sparkles, Upload, CheckCircle2, Loader2, AlertCircle, Search } from "lucide-react";

type KnowledgeDocument = {
  id: string; filename: string; size: number; status: string;
  character_count: number; chunk_count: number; embedded_chunk_count: number;
};
type SearchResult = {
  chunk_id: string; document_id: string; filename: string;
  chunk_index: number; content: string; score: number;
  keyword_rank?: number; vector_rank?: number;
};
type SearchMode = "keyword" | "vector" | "hybrid";
type ComparisonResult = {
  mode: SearchMode; results: SearchResult[]; error?: string; fallback?: string;
};
const formatSize = (size: number) => size < 1024 * 1024 ? (size / 1024).toFixed(1) + " KB" : (size / 1024 / 1024).toFixed(1) + " MB";
const modeTitle: Record<SearchMode, string> = {
  keyword: "关键词检索", vector: "向量语义检索", hybrid: "混合检索",
};
const modeSubtitle: Record<SearchMode, string> = {
  keyword: "Keyword Search", vector: "Vector Search", hybrid: "Hybrid · RRF",
};

export default function App() {
  const [health, setHealth] = useState<"checking" | "ok" | "error">("checking");
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [query, setQuery] = useState("");
  const [comparison, setComparison] = useState<ComparisonResult[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const loadDocuments = async () => {
    const response = await fetch("/api/documents");
    if (!response.ok) throw new Error("无法加载文档列表");
    setDocuments(await response.json() as KnowledgeDocument[]);
  };

  useEffect(() => {
    fetch("/api/health").then((response) => {
      if (!response.ok) throw new Error("API unavailable");
      setHealth("ok");
      return loadDocuments();
    }).catch(() => setHealth("error"));
  }, []);

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true); setMessage(""); setError("");
    const body = new FormData(); body.append("file", file);
    try {
      const response = await fetch("/api/documents", { method: "POST", body });
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
        const response = await fetch("/api/search", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: query.trim(), limit: 5, mode }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "检索失败");
        return {
          mode, results: result.results as SearchResult[],
          fallback: result.mode === "keyword_fallback" ? result.fallback_reason : undefined,
        };
      } catch (searchError) {
        return { mode, results: [], error: searchError instanceof Error ? searchError.message : "检索失败，请重试。" };
      }
    }));
    setComparison(outcomes);
    setSearching(false);
  };

  const renderResults = (item: ComparisonResult) => <div className="comparison-column" key={item.mode}>
    <div className="comparison-heading">
      <div><strong>{modeTitle[item.mode]}</strong><span>{modeSubtitle[item.mode]}</span></div>
      <span className="result-count">{item.error ? "不可用" : item.results.length + " 条结果"}</span>
    </div>
    {item.error ? <div className="comparison-error"><AlertCircle size={15} /><span>{item.error}</span></div> :
      <>
        {item.fallback && <div className="comparison-fallback">{item.fallback}</div>}
        {item.results.length === 0 ? <div className="empty-state compact">没有找到匹配片段</div> :
          <div className="result-list">{item.results.map((result, index) => <article className="result-card" key={result.chunk_id}>
            <div className="result-top"><strong>#{index + 1} · {result.filename}</strong><span>片段 #{result.chunk_index + 1} · {item.mode === "hybrid" ? "RRF " : "分数 "}{result.score.toFixed(4)}</span></div>
            {item.mode === "hybrid" && <div className="rank-meta">关键词排名：{result.keyword_rank ?? "—"} · 向量排名：{result.vector_rank ?? "—"}</div>}
            <p>{result.content}</p>
          </article>)}</div>}
      </>}
  </div>;

  return <main className="shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><Bot size={21} /></span><span>KnowFlow</span></div>
      <div className="workspace-label">工作空间</div>
      <button className="nav-item active"><Sparkles size={17} /> 智能问答</button>
      <button className="nav-item"><FileText size={17} /> 知识库</button>
      <div className="sidebar-bottom"><div className={"status-dot " + (health === "ok" ? "online" : "")} /><span>API {health === "ok" ? "运行正常" : health === "error" ? "连接失败" : "检查中"}</span></div>
    </aside>
    <section className="main-panel">
      <header className="topbar"><div><span className="eyebrow">ENTERPRISE KNOWLEDGE</span><h1>企业知识助手</h1></div><div className="secure"><ShieldCheck size={16} /> 企业知识安全空间</div></header>
      <section className="welcome">
        <div className="welcome-icon"><Sparkles size={22} /></div>
        <p className="eyebrow">YOUR KNOWLEDGE, CONNECTED</p>
        <h2>让企业知识，随问随答</h2>
        <p className="subtitle">上传企业文档，系统自动提取文本、切分知识片段，并支持多策略知识检索。</p>
        <input ref={inputRef} className="hidden-input" type="file" accept=".pdf,.docx,.txt,.md" onChange={handleUpload} />
        <button className="upload-box" onClick={() => inputRef.current?.click()} disabled={uploading}>
          {uploading ? <Loader2 className="spin" size={20} /> : <Upload size={20} />}
          <span>{uploading ? "正在上传、解析与分块…" : "选择文件，上传到知识库"}</span>
          <small>支持 PDF、DOCX、TXT、Markdown，单个文件最大 10 MB</small>
        </button>
        {message && <div className="notice success"><CheckCircle2 size={16} />{message}</div>}
        {error && <div className="notice error"><AlertCircle size={16} />{error}</div>}
      </section>
      <section className="search-section">
        <div className="section-heading"><div><h3>三种检索策略对比</h3><p>相同问题并行检索：关键词、向量语义，以及 RRF 融合后的混合排名</p></div></div>
        <form className="search-form" onSubmit={handleSearch}>
          <Search size={18} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="例如：出差回来后，多久之内要交票据？" />
          <button type="submit" disabled={searching || !query.trim()}>{searching ? "对比中…" : "同时检索"}</button>
        </form>
        {comparison.length > 0 && <div className="comparison-grid">{comparison.map(renderResults)}</div>}
        {comparison.length === 0 && <p className="comparison-hint">向量和混合检索需要先配置 Embedding API，并上传已生成向量的文档；否则混合检索会明确降级为关键词检索。</p>}
      </section>
      <section className="documents-section">
        <div className="section-heading"><div><h3>知识库文档</h3><p>已上传并完成文本提取的资料</p></div><span className="count">{documents.length} 个文件</span></div>
        {documents.length === 0 ? <div className="empty-state"><FileText size={23} /><span>还没有文档，上传一份资料开始构建知识库</span></div> :
          <div className="document-list">{documents.map((document) => <article className="document-row" key={document.id}>
            <div className="file-icon"><FileText size={19} /></div>
            <div className="file-info"><strong>{document.filename}</strong><span>{formatSize(document.size)} · {document.character_count.toLocaleString()} 字符 · {document.chunk_count} 个片段 · {document.embedded_chunk_count} 个向量</span></div>
            <span className="ready"><CheckCircle2 size={14} /> {document.embedded_chunk_count > 0 ? "向量已索引" : "文本已分块"}</span>
          </article>)}</div>}
      </section>
      <footer className="page-footer"><ShieldCheck size={14} /> 混合检索使用 Reciprocal Rank Fusion 融合关键词与向量的独立排名。</footer>
    </section>
  </main>;
}
